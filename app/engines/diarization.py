"""Speaker diarization shared by the built-in engines (whisper, parakeet).

The engine owns the recognition model; this mixin owns everything about
speakers: the long-lived pyannote worker process, the request/response over
its pipes, and turning the worker's speaker turns into labeled segments.

Why a separate process: pyannote's torch 2.8 needs cuDNN 9.10.x while the
custom CTranslate2 wheel whisper uses loads the system cuDNN 9.5.x, and the
two are ABI-incompatible in one address space. And once the engine's own
model holds a CUDA context, this process can no longer spawn a child cleanly
(fork segfaults, posix_spawn/vfork deadlocks against the driver's threads), so
engines MUST call ``_ensure_diar_worker()`` before loading their model.

An engine using the mixin provides these attributes: ``diarization``,
``diarization_model``, ``hf_token``, ``device``, ``num_speakers``,
``min_speakers``, ``max_speakers``, optionally ``diarization_device`` (None =
follow ``device``) and initializes ``_diar_proc = None``.
"""

import logging
from pathlib import Path

from .base import EngineError, Segment

log = logging.getLogger("plaud-bridge.engine.diarization")


def probe_duration(audio_path: Path) -> float | None:
    """Container-header duration probe (cheap; no decode). Lets an engine reject
    over-limit files BEFORE decoding the whole stream."""
    try:
        import av

        with av.open(str(audio_path)) as container:
            if container.duration:
                return container.duration / 1_000_000
    except Exception:
        pass
    return None


# Process-wide: has ANY engine (whisper, parakeet, Qwen3, a consensus helper)
# initialized CUDA in this process? From then on the pyannote worker cannot be
# respawned (see the module docstring), whatever an individual engine did.
_CUDA_USED = False


def mark_cuda_used() -> None:
    global _CUDA_USED
    _CUDA_USED = True


def cuda_used() -> bool:
    return _CUDA_USED


class DiarizationMixin:
    diarization: bool
    diarization_model: str
    hf_token: str | None
    device: str
    num_speakers: int | None
    min_speakers: int | None
    max_speakers: int | None
    diarization_device: str | None = None
    _diar_proc = None

    def _diar_device(self) -> str:
        """Device pyannote runs on: the explicit diarization device when set,
        else the engine's own (cpu => the worker stays off the GPU too)."""
        return (getattr(self, "diarization_device", None) or self.device or "auto")

    # -- worker process -----------------------------------------------------

    def _ensure_diar_worker(self):
        """Start the long-lived pyannote worker if diarization is on and it is
        not already running. MUST be called before the engine's model takes a
        CUDA context (see module docstring). Idempotent; degrades to no-op on
        spawn failure."""
        if not self.diarization or self._diar_proc is not None:
            return
        import glob
        import os
        import subprocess
        import sys
        import sysconfig

        purelib = sysconfig.get_paths()["purelib"]
        nvidia_libs = sorted(glob.glob(os.path.join(purelib, "nvidia", "*", "lib")))
        env = dict(os.environ)
        # torch's bundled CUDA/cuDNN first so the child uses 9.10.x, not the
        # system 9.5.x the parent's CTranslate2 pulled in.
        env["LD_LIBRARY_PATH"] = ":".join([*nvidia_libs, env.get("LD_LIBRARY_PATH", "")])
        env["PB_STT_HF_TOKEN"] = self.hf_token or ""
        env["PB_STT_DEVICE"] = self._diar_device()
        # Speaker-count hints for the pipeline (empty = automatic).
        env["PB_STT_NUM_SPEAKERS"] = str(self.num_speakers) if self.num_speakers else ""
        env["PB_STT_MIN_SPEAKERS"] = str(self.min_speakers) if self.min_speakers else ""
        env["PB_STT_MAX_SPEAKERS"] = str(self.max_speakers) if self.max_speakers else ""
        # The worker imports `app.engines.diarize_worker`; make sure our package
        # root is importable regardless of the child's cwd.
        pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env["PYTHONPATH"] = os.pathsep.join([pkg_root, env.get("PYTHONPATH", "")])

        log.info("starting diarization worker (pyannote): %s on %s",
                 self.diarization_model, self._diar_device())
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "app.engines.diarize_worker",
             "--serve", self.diarization_model],
            env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, bufsize=1,
        )
        # Block until the model is loaded and the worker signals READY, so the
        # first real request doesn't race model loading. Give it generous time.
        ready = proc.stdout.readline().strip()
        if ready != "READY":
            log.warning("diarization worker failed to become ready (got %r); "
                        "diarization disabled for this process", ready)
            try:
                proc.kill()
            except OSError:
                pass
            self._diar_proc = None
            return
        self._diar_proc = proc
        log.info("diarization worker ready")

    def _run_diarizer(self, audio_path: Path) -> list[tuple[float, float, str]]:
        """Send one audio path to the persistent pyannote worker and return its
        speaker turns as (start, end, label) tuples."""
        import json

        proc = self._diar_proc
        if proc is None or proc.poll() is not None:
            raise EngineError("diarization worker is not running")
        try:
            proc.stdin.write(str(audio_path) + "\n")
            proc.stdin.flush()
            line = proc.stdout.readline()
        except (BrokenPipeError, OSError) as exc:
            raise EngineError(f"diarization worker pipe broke: {exc}") from exc
        if not line:
            raise EngineError("diarization worker exited unexpectedly")
        result = json.loads(line)
        if isinstance(result, dict) and "error" in result:
            raise EngineError("diarization worker error: %s" % result["error"])
        return [(float(s), float(e), str(label)) for s, e, label in result]

    def close(self):
        """Shut the diarization worker down cleanly (closing stdin ends its
        serve loop). Safe to call more than once."""
        proc = getattr(self, "_diar_proc", None)
        if proc is None:
            return
        self._diar_proc = None
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass

    # -- speaker assignment -------------------------------------------------

    @staticmethod
    def _assign_speaker(start: float, end: float,
                        turns: list[tuple[float, float, str]]) -> str | None:
        """Speaker whose turns cover the most of [start, end] (cumulative
        overlap; a speaker's turns may be split around the span). Falls back to
        the turn containing the midpoint for zero-duration spans."""
        totals: dict[str, float] = {}
        for t_start, t_end, speaker in turns:
            overlap = min(end, t_end) - max(start, t_start)
            if overlap > 0:
                totals[speaker] = totals.get(speaker, 0.0) + overlap
        if totals:
            return max(totals, key=totals.get)
        mid = (start + end) / 2
        for t_start, t_end, speaker in turns:
            if t_start <= mid <= t_end:
                return speaker
        return None

    def _apply_diarization(self, audio_path: Path, segments: list[Segment],
                           words: list[tuple[float, float, str, int]]) -> None:
        """Label ``segments`` with speakers. ``words`` are (start, end, text,
        index of the segment they came from); when present, speakers are
        assigned per word and the segments rebuilt at speaker changes."""
        raw_turns = self._run_diarizer(audio_path)
        turns = [(start, end, str(label)) for start, end, label in raw_turns]
        if not turns:
            return

        # Word-level path: recognizer segments are coarse and often span a
        # speaker change, so assign each WORD a speaker and regroup consecutive
        # same-speaker words into segments. This preserves short interjections a
        # segment-level assignment would drop (the dominant speaker wins the
        # whole segment otherwise). Regrouping also breaks at the recognizer's
        # own segment boundaries: a speaker who talks for five minutes would
        # otherwise become one 300 s segment with a single timestamp, which is
        # useless for seeking. Rendering joins consecutive same-speaker segments
        # into one turn, so the extra splits never show up as repeated labels.
        if words:
            labels = [self._assign_speaker(w_start, w_end, turns) for w_start, w_end, _, _ in words]
            # Words outside every diarization turn (a lead-in syllable before the
            # first turn, a word in a gap) would otherwise become their own
            # "unknown speaker" turn. Inherit the nearest labeled neighbour
            # instead: the following word first (the speaker is about to start),
            # else the previous one.
            for i, label in enumerate(labels):
                if label is not None:
                    continue
                nxt = next((l for l in labels[i + 1:] if l is not None), None)
                prv = next((l for l in reversed(labels[:i]) if l is not None), None)
                labels[i] = nxt if nxt is not None else prv
            new_segments: list[Segment] = []
            cur_label: str | None = object()  # sentinel != any real label
            cur_idx = -1
            for (w_start, w_end, text, idx), label in zip(words, labels):
                if label != cur_label or idx != cur_idx or not new_segments:
                    new_segments.append(
                        Segment(start=round(w_start, 2), end=round(w_end, 2),
                                text=text.strip(), speaker=label)
                    )
                    cur_label = label
                    cur_idx = idx
                else:
                    seg = new_segments[-1]
                    seg.end = round(w_end, 2)
                    seg.text = (seg.text + text).strip()
            segments[:] = new_segments
        else:
            # No word timestamps: fall back to per-segment assignment.
            for seg in segments:
                if seg.start is None or seg.end is None:
                    continue
                seg.speaker = self._assign_speaker(seg.start, seg.end, turns)

        # Normalize labels to appearance order: Speaker 1, Speaker 2, ...
        mapping: dict[str, str] = {}
        for seg in segments:
            if seg.speaker and seg.speaker not in mapping:
                mapping[seg.speaker] = f"Speaker {len(mapping) + 1}"
        for seg in segments:
            if seg.speaker:
                seg.speaker = mapping[seg.speaker]
