"""Benchmark transcription models on this machine's hardware.

Usage (inside the container or a venv with requirements-stt.txt):

    python -m app.benchmark audio.mp3 --models tiny,base,small,distil-large-v3
    python -m app.benchmark audio.mp3 --models base --device cpu --compute int8
    python -m app.benchmark audio.mp3 --models base --reference ref.txt --json out.json
    docker compose exec plaud-bridge python -m app.benchmark /data/recordings/....mp3 --models base,small

For each model it reports load time, transcription time, real-time factor
(RTF — how many seconds of audio are processed per wall-clock second; higher
is better), detected language, and — when a reference transcript is given —
word error rate (WER). Results print as a table and optionally save as JSON.
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path


def normalize_words(text: str) -> list[str]:
    text = text.replace("’", "'")  # curly apostrophe -> straight
    return re.sub(r"[^\w\s']", " ", text.lower()).split()


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Standard WER via word-level Levenshtein distance (0.0 = perfect)."""
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rw in enumerate(ref, 1):
        cur = [i] + [0] * len(hyp)
        for j, hw in enumerate(hyp, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rw != hw))
        prev = cur
    return prev[-1] / len(ref)


async def bench_model(audio: Path, model: str, device: str, compute: str,
                      diarize: bool, hf_token: str | None) -> dict:
    from .engines.local_whisper import LocalWhisperEngine

    engine = LocalWhisperEngine(
        model=model, device=device, compute_type=compute,
        diarization=diarize, hf_token=hf_token,
    )
    row: dict = {"model": model, "device": device, "compute": compute}
    try:
        result = await engine.transcribe(audio)
        row.update(
            status="ok",
            load_s=round(engine.load_seconds or 0, 2),
            transcribe_s=result.stats.get("transcribe_seconds"),
            diarize_s=result.stats.get("diarize_seconds"),
            audio_s=result.duration,
            # speedup over realtime: audio seconds per wall second
            speed=round(result.duration / result.stats["transcribe_seconds"], 1)
            if result.duration and result.stats.get("transcribe_seconds") else None,
            language=result.language,
            text=result.text,
        )
    except Exception as exc:
        row.update(status="fail", error=str(exc)[:300])
    return row


def print_table(rows: list[dict], has_wer: bool) -> None:
    cols = ["model", "device", "status", "load_s", "transcribe_s", "speed", "language"]
    if has_wer:
        cols.append("wer")
    if any(r.get("diarize_s") for r in rows):
        cols.insert(6, "diarize_s")
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = "  ".join(c.ljust(widths[c]) for c in cols)
    print("\n" + header)
    print("-" * len(header))
    for r in rows:
        print("  ".join(str(r.get(c, "") if r.get(c) is not None else "-").ljust(widths[c]) for c in cols))
    print("\nspeed = audio seconds transcribed per wall-clock second (higher is better)")
    for r in rows:
        if r.get("status") == "fail":
            print(f"  {r['model']}: FAILED — {r['error']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", type=Path, help="audio file to transcribe (mp3/wav/...)")
    p.add_argument("--models", default="tiny,base,small",
                   help="comma-separated faster-whisper model names "
                        "(tiny, base, small, medium, large-v3, distil-large-v3, "
                        "or any CTranslate2 model repo id)")
    p.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    p.add_argument("--compute", default="auto",
                   help="compute type: auto, int8, int8_float16, float16, float32")
    p.add_argument("--diarize", action="store_true", help="also benchmark speaker diarization")
    p.add_argument("--hf-token", default=os.environ.get("PB_STT_HF_TOKEN"),
                   help="Hugging Face token for diarization (default: $PB_STT_HF_TOKEN)")
    p.add_argument("--reference", type=Path, default=None,
                   help="reference transcript .txt for WER scoring")
    p.add_argument("--json", type=Path, default=None, help="also write results to this JSON file")
    args = p.parse_args(argv)

    if not args.audio.exists():
        print(f"audio file not found: {args.audio}", file=sys.stderr)
        return 2
    reference = args.reference.read_text() if args.reference else None

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    if not models:
        print("no models given (--models)", file=sys.stderr)
        return 2

    rows = []
    for model in models:
        print(f"benchmarking {model} on {args.device} ...", file=sys.stderr)
        row = asyncio.run(bench_model(
            args.audio, model, args.device, args.compute, args.diarize, args.hf_token
        ))
        if reference and row.get("status") == "ok":
            row["wer"] = round(word_error_rate(reference, row["text"]), 3)
        rows.append(row)

    print_table(rows, has_wer=reference is not None)
    if args.json:
        args.json.write_text(json.dumps(
            {"benchmarked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "results": rows},
            indent=2,
        ))
        print(f"\nresults written to {args.json}")
    return 0 if any(r.get("status") == "ok" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
