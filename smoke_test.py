"""
smoke_test.py — end-to-end pipeline check against the LIVE OpenAI API.

This is the one thing that cannot be verified without a real key. Run it on
your machine to confirm the whole chain holds together and to see real
per-stage output, token counts, and cost.

Usage:
    export OPENAI_API_KEY=sk-...
    # Full pipeline from an audio file:
    python smoke_test.py --audio sample_max.wav
    # LLM-only (skip transcription) from a transcript string/file:
    python smoke_test.py --text sample_transcript.txt

Cost guard: this exercises real paid calls. A 10-min consult is ~$0.10.
The rate_limit budget kill-switch still applies.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import pipeline
import rate_limit as rl

PATIENT = "Max — Canine Golden Retriever, 4y MN"

SAMPLE_TRANSCRIPT = (
    "Hi, so what's been going on with Max the last few days? "
    "He's just been really lethargic since the weekend, and barely touching "
    "his food. Any change in his drinking? Actually yeah, he's been drinking "
    "way more water than usual. You mentioned you'd been out hiking? Twice "
    "last weekend, in the woods. His temperature's 102.8, a little elevated, "
    "and I'm feeling some mildly enlarged lymph nodes under the jaw. Given the "
    "tick exposure I want to run a CBC and a tick-borne disease panel."
)


def _hr(label: str) -> None:
    print("\n" + "=" * 8 + f" {label} " + "=" * 8)


def run(transcript: str | None, audio: str | None) -> int:
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: set OPENAI_API_KEY first.", file=sys.stderr)
        return 2

    usage = rl.SessionUsage()

    if audio:
        _hr("TRANSCRIBE")
        transcript = pipeline.transcribe(audio, usage)
        print(transcript)
    assert transcript, "no transcript"

    _hr("DIARIZE (index-labeled, no echo)")
    turns = pipeline.diarize(transcript, usage)
    for t in turns:
        print(f"  {t['speaker']}: {t['text']}")

    _hr("SOAP")
    soap = pipeline.generate_soap(PATIENT, turns, usage)
    print(json.dumps(soap, indent=2))

    _hr("OWNER SUMMARY")
    print(json.dumps(pipeline.generate_owner_summary(PATIENT, soap, usage), indent=2))

    _hr("ENTITIES")
    print(json.dumps(pipeline.extract_entities(transcript, usage), indent=2))

    _hr("RESEARCH FLAGS")
    print(json.dumps(pipeline.research_flags(turns, soap, usage), indent=2))

    _hr("COST")
    print(f"  transcriptions: {usage.transcriptions}")
    print(f"  generations:    {usage.generations}")
    print(f"  est. cost USD:  ${usage.est_cost_usd:.4f}")
    print(f"  models: STT={pipeline.TRANSCRIBE_MODEL} SOAP={pipeline.MODEL_SOAP} "
          f"diarize={pipeline.MODEL_DIARIZE} flags={pipeline.MODEL_FLAGS}")

    # sanity: diarization must NOT have altered the words. Every sentence's
    # text should still appear in the joined turns.
    joined = " ".join(t["text"] for t in turns)
    sents = pipeline.split_sentences(transcript)
    missing = [s for s in sents if s.rstrip(".!?") not in joined]
    if missing:
        print(f"\nWARNING: {len(missing)} sentence(s) altered/dropped by diarize:")
        for m in missing:
            print(f"  - {m}")
    else:
        print("\nVERBATIM CHECK: OK — diarization preserved all sentence text.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", help="path to a WAV/MP3 consultation clip")
    ap.add_argument("--text", help="path to a transcript .txt (skips transcription)")
    args = ap.parse_args()

    transcript = None
    if args.text:
        with open(args.text) as fh:
            transcript = fh.read()
    elif not args.audio:
        print("No --audio or --text given; using built-in sample transcript.")
        transcript = SAMPLE_TRANSCRIPT

    return run(transcript, args.audio)


if __name__ == "__main__":
    raise SystemExit(main())
