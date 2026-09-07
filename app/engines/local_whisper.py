"""Built-in transcription: faster-whisper (CTranslate2) with optional
pyannote speaker diarization. Runs fully locally on GPU (CUDA) or CPU.

Design notes:
- Models load lazily on first use and stay warm; a lock serializes access
  (one transcription at a time — these models saturate the device anyway).
- faster-whisper streams audio decode via PyAV and yields segments as it
  goes, so multi-hour recordings (Plaud hardware caps around 5 h) do not
  require the whole waveform in memory at once. VAD filtering skips
  silence, which matters a lot for long lecture/meeting recordings.
- Diarization (pyannote) is optional: it needs the heavier torch stack and
  a Hugging Face token for the gated pipeline. When enabled, whisper
  segments are assigned the speaker with the greatest temporal overlap.
"""

import asyncio
import logging
import time
from pathlib import Path

from .base import EngineError, EngineResult, Segment, render_text

log = logging.getLogger("plaud-bridge.engine.local")


class LocalWhisperEngine:
    name = "local"

    def __init__(
        self,
        model: str = "base",
        device: str = "auto",
        compute_type: str = "auto",
        language: str | None = None,
        vad_filter: bool = True,
        max_duration_s: int = 5 * 3600,
        diarization: bool = False,
        diarization_model: str = "pyannote/speaker-diarization-community-1",
        hf_token: str | None = None,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
        beam_size: int = 5,
        cpu_threads: int = 0,
    ):
        self.model_name = model
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self.max_duration_s = max_duration_s
        self.diarization = diarization
        self.diarization_model = diarization_model
        self.hf_token = hf_token
        self.num_speakers = num_speakers
        self.min_speakers = min_speakers
        self.max_speakers = max_speakers
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads
        self._model = None
        self._diar_proc = None
        self._lock = asyncio.Lock()
        self.load_seconds: float | None = None

    # -- model loading ------------------------------------------------------

    def _load_model(self):
        if self._model is not None:
            return self._model
        # Spawn the diarization worker BEFORE whisper initializes a CUDA context
        # in this process. Once whisper has a live context, this process can no
        # longer spawn a child cleanly (fork segfaults, posix_spawn/vfork
        # deadlocks against the driver's threads), so the child must be forked
        # off while we are still CUDA-free, then kept alive.
        self._ensure_diar_worker()
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise EngineError(
                "faster-whisper is not installed — install requirements-stt.txt "
                "or use the CUDA/CPU docker image"
            ) from exc
        t0 = time.monotonic()
        log.info("loading whisper model %r (device=%s, compute=%s)",
                 self.model_name, self.device, self.compute_type)
        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        self.load_seconds = time.monotonic() - t0
        log.info("model loaded in %.1fs", self.load_seconds)
        return self._model

    def _ensure_diar_worker(self):
        """Start the long-lived pyannote worker if diarization is on and it is
        not already running. MUST be called before whisper takes a CUDA context
        (see _load_model). Idempotent; degrades to no-op on spawn failure."""
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
        # Speaker-count hints for the pipeline (empty = automatic).
        env["PB_STT_NUM_SPEAKERS"] = str(self.num_speakers) if self.num_speakers else ""
        env["PB_STT_MIN_SPEAKERS"] = str(self.min_speakers) if self.min_speakers else ""
        env["PB_STT_MAX_SPEAKERS"] = str(self.max_speakers) if self.max_speakers else ""
        # The worker imports `app.engines.diarize_worker`; make sure our package
        # root is importable regardless of the child's cwd.
        pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        env["PYTHONPATH"] = os.pathsep.join([pkg_root, env.get("PYTHONPATH", "")])

        log.info("starting diarization worker (pyannote): %s", self.diarization_model)
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
        speaker turns as (start, end, label) tuples. The worker runs pyannote on
        the GPU in its own process: whisper's custom CTranslate2 wheel loads the
        system cuDNN 9.5.x and pyannote's torch 2.8 needs cuDNN 9.10.x, and the
        two are ABI-incompatible in a single address space."""
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

    # -- transcription ------------------------------------------------------

    async def transcribe(self, audio_path: Path) -> EngineResult:
        async with self._lock:
            return await asyncio.to_thread(self._transcribe_sync, audio_path)

    def _probe_duration(self, audio_path: Path) -> float | None:
        """Container-header duration probe (cheap; no decode). Used to reject
        over-limit files BEFORE whisper decodes the whole stream."""
        try:
            import av

            with av.open(str(audio_path)) as container:
                if container.duration:
                    return container.duration / 1_000_000
        except Exception:
            pass
        return None

    def _transcribe_sync(self, audio_path: Path) -> EngineResult:
        probed = self._probe_duration(audio_path)
        if probed and probed > self.max_duration_s:
            raise EngineError(
                f"audio is {probed / 3600:.1f} h, over the "
                f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
            )

        model = self._load_model()
        t0 = time.monotonic()
        try:
            seg_iter, info = model.transcribe(
                str(audio_path),
                language=self.language,
                beam_size=self.beam_size,
                vad_filter=self.vad_filter,
                # Word timestamps let diarization split a whisper segment that
                # spans a speaker change at the actual word boundary, instead of
                # collapsing the whole segment to the dominant speaker.
                word_timestamps=self.diarization,
            )
            # Backstop for streams whose header lied or lacked a duration.
            if info.duration and info.duration > self.max_duration_s:
                raise EngineError(
                    f"audio is {info.duration / 3600:.1f} h, over the "
                    f"{self.max_duration_s / 3600:.1f} h limit (PB_STT_MAX_DURATION_S)"
                )
            segments = []
            # (start, end, word, index of the whisper segment it came from)
            words: list[tuple[float, float, str, int]] = []
            for idx, s in enumerate(seg_iter):  # generator: inference happens during this loop
                segments.append(
                    Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip())
                )
                for w in (getattr(s, "words", None) or []):
                    if w.start is not None and w.end is not None:
                        words.append((w.start, w.end, w.word, idx))
        except EngineError:
            raise
        except Exception as exc:
            raise EngineError(f"whisper transcription failed: {exc}") from exc
        transcribe_s = time.monotonic() - t0

        diarize_s = 0.0
        if self.diarization and segments:
            t1 = time.monotonic()
            try:
                self._apply_diarization(audio_path, segments, words)
            except Exception as exc:
                # A transcript without speaker labels beats losing it entirely.
                log.warning("diarization failed, returning unlabeled transcript: %s", exc)
            diarize_s = time.monotonic() - t1

        plain = " ".join(s.text for s in segments if s.text)
        stats = {
            "engine": self.name,
            "model": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "transcribe_seconds": round(transcribe_s, 2),
            "diarize_seconds": round(diarize_s, 2) or None,
            "rtf": round(transcribe_s / info.duration, 3) if info.duration else None,
        }
        return EngineResult(
            text=render_text(segments, fallback=plain),
            segments=segments,
            language=info.language,
            duration=round(info.duration, 2) if info.duration else None,
            model=self.model_name,
            stats={k: v for k, v in stats.items() if v is not None},
        )

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
        raw_turns = self._run_diarizer(audio_path)
        turns = [(start, end, str(label)) for start, end, label in raw_turns]
        if not turns:
            return

        # Word-level path: whisper segments are coarse and often span a speaker
        # change, so assign each WORD a speaker and regroup consecutive
        # same-speaker words into segments. This preserves short interjections a
        # segment-level assignment would drop (the dominant speaker wins the
        # whole segment otherwise). Regrouping also breaks at whisper's own
        # segment boundaries: a speaker who talks for five minutes would
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
