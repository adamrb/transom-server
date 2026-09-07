"""Isolated pyannote speaker-diarization worker.

Two modes:

* one-shot: ``python -m app.engines.diarize_worker <audio_path> <model>`` —
  prints one JSON array of ``[start, end, label]`` turns and exits (handy for
  manual testing).
* serve:    ``python -m app.engines.diarize_worker --serve <model>`` — loads the
  pipeline once, then reads one audio path per line on stdin and writes one
  JSON line per request on stdout (a bare array on success, or
  ``{"error": "..."}`` on failure). This is how ``LocalWhisperEngine`` drives
  it: a long-lived child spawned while the parent is still CUDA-free.

Why a separate process at all: torch's bundled cuDNN (9.10.x) collides with the
system cuDNN (9.5.x) that the parent's custom-built CTranslate2 whisper wheel
loads — the two are ABI-incompatible in one address space (segfault). And the
parent can't fork once whisper has a live CUDA context (fork segfaults, vfork/
posix_spawn deadlocks against the driver's threads), so the engine spawns this
worker BEFORE loading whisper and keeps it alive. The caller sets
``LD_LIBRARY_PATH`` to torch's bundled CUDA stack and passes ``PB_STT_HF_TOKEN``.

Audio is decoded here with PyAV into an in-memory waveform rather than letting
pyannote.audio 4.x decode the file through torchcodec, whose prebuilt wheels are
ABI-tied to a specific torch and fail to load against our pinned torch 2.8
(``undefined symbol: torch_list_size``).
"""

from __future__ import annotations

import json
import os
import sys


def _decode_waveform(audio_path: str):
    """Decode an audio file to a mono 16 kHz float32 waveform via PyAV."""
    import av
    import numpy as np
    import torch

    resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
    chunks: list = []
    with av.open(audio_path) as container:
        for frame in container.decode(audio=0):
            for rframe in resampler.resample(frame):
                chunks.append(rframe.to_ndarray())
        for rframe in resampler.resample(None):  # flush buffered samples
            chunks.append(rframe.to_ndarray())
    if not chunks:
        raise RuntimeError(f"no audio decoded from {audio_path}")
    wav = np.concatenate(chunks, axis=1).astype("float32")  # (1, T)
    return torch.from_numpy(wav), 16000


def _load_pipeline(model: str | None):
    token = os.environ.get("PB_STT_HF_TOKEN") or None
    import torch
    from pyannote.audio import Pipeline

    # pyannote.audio 4.x renamed the auth kwarg to `token`; 3.x used
    # `use_auth_token`. Try the new name, fall back for older installs.
    try:
        pipeline = Pipeline.from_pretrained(model, token=token)
    except TypeError:
        pipeline = Pipeline.from_pretrained(model, use_auth_token=token)
    if pipeline is None:
        raise RuntimeError(
            f"could not load {model} — set PB_STT_HF_TOKEN to a Hugging Face "
            "token that has accepted the model's terms"
        )
    if torch.cuda.is_available():
        pipeline.to(torch.device("cuda"))
    return pipeline


def _speaker_hints() -> dict:
    """Optional speaker-count kwargs for the pipeline, from the environment.
    community-1's clustering under-counts on short or acoustically-similar
    audio, so a known count (or a lower bound) can be pinned. num_speakers wins
    over min/max when set."""
    hints: dict = {}
    num = os.environ.get("PB_STT_NUM_SPEAKERS")
    if num:
        return {"num_speakers": int(num)}
    lo = os.environ.get("PB_STT_MIN_SPEAKERS")
    hi = os.environ.get("PB_STT_MAX_SPEAKERS")
    if lo:
        hints["min_speakers"] = int(lo)
    if hi:
        hints["max_speakers"] = int(hi)
    return hints


def _diarize(pipeline, audio_path: str) -> list:
    waveform, sample_rate = _decode_waveform(audio_path)
    output = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **_speaker_hints())
    # pyannote.audio 4.x pipelines (e.g. community-1) return a DiarizeOutput
    # dataclass with two annotations: `speaker_diarization` keeps overlapping
    # speech (concurrent turns), while `exclusive_speaker_diarization` resolves
    # every instant to a single speaker. We assign whisper words to one speaker,
    # so the exclusive view is what we want — otherwise a long dominant turn
    # engulfs a brief interjecting turn and every word goes to the dominant
    # speaker. Older 3.x pipelines return the Annotation directly.
    annotation = getattr(output, "exclusive_speaker_diarization", None)
    if annotation is None:
        annotation = getattr(output, "speaker_diarization", output)
    return [
        [float(turn.start), float(turn.end), str(label)]
        for turn, _, label in annotation.itertracks(yield_label=True)
    ]


def _serve(model: str | None) -> int:
    """Load once, then one audio path per stdin line -> one JSON line out."""
    pipeline = _load_pipeline(model)
    # Signal readiness so the parent can wait for model load before use.
    sys.stdout.write("READY\n")
    sys.stdout.flush()
    for line in sys.stdin:
        audio_path = line.strip()
        if not audio_path:
            continue
        try:
            result: object = _diarize(pipeline, audio_path)
        except Exception as exc:  # keep serving; report per-request failure
            result = {"error": str(exc)}
        sys.stdout.write(json.dumps(result) + "\n")
        sys.stdout.flush()
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[1] == "--serve":
        model = argv[2] if len(argv) > 2 else os.environ.get("PB_STT_DIARIZE_MODEL")
        return _serve(model)

    if len(argv) < 2:
        print("usage: diarize_worker [--serve] <audio_path|model> [model]", file=sys.stderr)
        return 2
    audio_path = argv[1]
    model = argv[2] if len(argv) > 2 else os.environ.get("PB_STT_DIARIZE_MODEL")
    try:
        pipeline = _load_pipeline(model)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 3
    json.dump(_diarize(pipeline, audio_path), sys.stdout)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
