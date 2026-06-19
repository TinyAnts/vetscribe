"""
pipeline.py — OpenAI-backed transcription + clinical generation.

Stages: transcribe (Whisper) -> diarize (GPT turn inference) ->
SOAP -> owner summary -> entities -> research flags.

Every paid call is gated by rate_limit guards passed in from the caller.
The OpenAI client is created lazily so the module imports cleanly with no key
(needed for CI / syntax checks / building the UI without secrets).
"""

from __future__ import annotations

import json
import os
import re
import wave
import contextlib
from typing import Any

import prompts
import rate_limit as rl


def _load_dotenv() -> None:
    """Load KEY=VALUE pairs from a local .env file (same folder) into the
    environment if not already set. No external dependency. This lets you paste
    your key into a file instead of fiddling with shell environment variables."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, ".env")
    try:
        with open(path) as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except FileNotFoundError:
        pass


_load_dotenv()

# --- Per-stage model selection (override any single stage via env) ----------
# Rationale (see README): transcription is the un-recoverable foundation, so it
# does NOT get the cheapest model. The two reasoning-heavy, quality-critical
# stages (SOAP, research flags) use the workhorse gpt-5.4. Mechanical stages
# (diarize, owner summary, NER) use gpt-5.4-mini. Bump any stage to gpt-5.5 by
# setting its env var if rater scores lag.
TRANSCRIBE_MODEL = os.getenv("VS_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
MODEL_DIARIZE = os.getenv("VS_MODEL_DIARIZE", "gpt-5.4-mini")
MODEL_SOAP = os.getenv("VS_MODEL_SOAP", "gpt-5.4")
MODEL_OWNER = os.getenv("VS_MODEL_OWNER", "gpt-5.4-mini")
MODEL_NER = os.getenv("VS_MODEL_NER", "gpt-5.4-mini")
MODEL_FLAGS = os.getenv("VS_MODEL_FLAGS", "gpt-5.4")

# gpt-4o-transcribe / -mini-transcribe return plain json (no verbose_json
# segments or duration). We measure duration from the WAV ourselves, so this is
# fine and we lose nothing the LLM-based diarizer wasn't already ignoring.
_TRANSCRIBE_RESPONSE_FORMAT = (
    "verbose_json" if TRANSCRIBE_MODEL == "whisper-1" else "json"
)

def get_client(api_key: str | None = None):
    """OpenAI client. Uses a caller-supplied key (Bring-Your-Own-Key) if given,
    otherwise falls back to the OPENAI_API_KEY environment / .env value (local
    use). A fresh client is created per call so visitor keys are never retained
    in a module-level singleton."""
    key = (api_key or "").strip() or (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        raise RuntimeError(
            "No OpenAI API key. Paste your key in the app's “Your OpenAI API "
            "key” field, or set OPENAI_API_KEY (or .env) for local use."
        )
    from openai import OpenAI  # imported lazily so module loads without SDK

    return OpenAI(api_key=key)


def audio_duration_seconds(path: str) -> float:
    """Best-effort duration. WAV is read natively; other formats fall back to
    a size-based estimate only if needed (Gradio mic output is WAV)."""
    if not path or not os.path.exists(path):
        return 0.0
    try:
        with contextlib.closing(wave.open(path, "rb")) as wf:
            return wf.getnframes() / float(wf.getframerate())
    except (wave.Error, EOFError, OSError):
        # Non-WAV container: let the model handle it; report unknown as 0 so the
        # caller can decide. We avoid guessing duration from bytes (unreliable).
        return 0.0


def _chat_json(system, user, model, api_key=None):
    """Call the chat model with JSON mode. Returns (parsed, in_tok, out_tok)."""
    client = get_client(api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = resp.choices[0].message.content or "{}"
    usage = resp.usage
    in_tok = getattr(usage, "prompt_tokens", 0) if usage else 0
    out_tok = getattr(usage, "completion_tokens", 0) if usage else 0
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        parsed = {}
    return parsed, in_tok, out_tok


# ---------------------------------------------------------------------------
# Stage 1: transcription
# ---------------------------------------------------------------------------
def transcribe(audio_path: str, usage: rl.SessionUsage, api_key=None) -> str:
    seconds = audio_duration_seconds(audio_path)
    # If duration is unknown (non-WAV), enforce a conservative file-size guard
    # before the call so an attacker can't bypass the length cap.
    if seconds == 0.0 and audio_path and os.path.exists(audio_path):
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        if size_mb > 25:  # OpenAI's own 25MB upload ceiling
            raise rl.RateLimitError("Audio file exceeds the 25 MB demo limit.")
    rl.guard_transcription(usage, seconds if seconds > 0 else 1.0)

    client = get_client(api_key)
    with open(audio_path, "rb") as fh:
        result = client.audio.transcriptions.create(
            model=TRANSCRIBE_MODEL,
            file=fh,
            response_format=_TRANSCRIBE_RESPONSE_FORMAT,
        )
    # whisper-1 reports duration; gpt-4o-transcribe does not, so we fall back to
    # the WAV-measured duration for billing.
    reported = float(getattr(result, "duration", 0.0) or 0.0)
    rl.record_transcription(usage, max(seconds, reported, 1.0), TRANSCRIBE_MODEL)
    return getattr(result, "text", "") or ""


# ---------------------------------------------------------------------------
# Stage 2: diarization substitute (index-labeling, no transcript echo)
# ---------------------------------------------------------------------------
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(transcript: str) -> list[str]:
    """Deterministic local sentence split. Keeps the verbatim text on our side
    so the model only ever returns indices, never re-typed words."""
    parts = [s.strip() for s in _SENT_SPLIT.split(transcript.strip()) if s.strip()]
    return parts


def _labels_to_turns(
    sentences: list[str], labels: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Map {i, speaker} labels onto local sentences and merge consecutive
    same-speaker sentences into turns. Unlabeled indices inherit the previous
    speaker (fallback 'Owner' for index 0)."""
    by_index = {}
    for lab in labels:
        try:
            idx = int(lab.get("i"))
        except (TypeError, ValueError):
            continue
        spk = lab.get("speaker", "")
        by_index[idx] = "Vet" if str(spk).lower().startswith("vet") else "Owner"

    turns: list[dict[str, Any]] = []
    last = "Owner"
    for idx, text in enumerate(sentences):
        spk = by_index.get(idx, last)
        last = spk
        if turns and turns[-1]["speaker"] == spk:
            turns[-1]["text"] += " " + text
        else:
            turns.append({"speaker": spk, "start": None, "text": text})
    return turns


def diarize(transcript: str, usage: rl.SessionUsage, api_key=None) -> list[dict[str, Any]]:
    sentences = split_sentences(transcript)
    if not sentences:
        return []
    rl.guard_generation(usage)
    numbered = "\n".join(f"{i}\t{s}" for i, s in enumerate(sentences))
    parsed, i, o = _chat_json(
        prompts.DIARIZE_SYSTEM,
        prompts.DIARIZE_USER_TEMPLATE.format(sentences=numbered),
        MODEL_DIARIZE,
        api_key,
    )
    rl.record_generation(usage, i, o, MODEL_DIARIZE)
    labels = parsed.get("labels", [])
    if not isinstance(labels, list):
        labels = []
    return _labels_to_turns(sentences, labels)


def _format_diarized(turns: list[dict[str, Any]]) -> str:
    lines = []
    for t in turns:
        spk = t.get("speaker", "?")
        txt = t.get("text", "")
        lines.append(f"{spk}: {txt}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Stages 3-6: clinical generation
# ---------------------------------------------------------------------------
def generate_soap(
    patient: str,
    turns: list[dict[str, Any]],
    usage: rl.SessionUsage,
    model: str | None = None,
    api_key=None,
) -> dict[str, Any]:
    model = model or MODEL_SOAP
    rl.guard_generation(usage)
    parsed, i, o = _chat_json(
        prompts.SOAP_SYSTEM,
        prompts.SOAP_USER_TEMPLATE.format(
            patient=patient, diarized=_format_diarized(turns)
        ),
        model,
        api_key,
    )
    rl.record_generation(usage, i, o, model)
    return parsed


def generate_owner_summary(
    patient: str, soap: dict[str, Any], usage: rl.SessionUsage, api_key=None
) -> dict[str, Any]:
    rl.guard_generation(usage)
    parsed, i, o = _chat_json(
        prompts.OWNER_SYSTEM,
        prompts.OWNER_USER_TEMPLATE.format(
            patient=patient, soap=json.dumps(soap)
        ),
        MODEL_OWNER,
        api_key,
    )
    rl.record_generation(usage, i, o, MODEL_OWNER)
    return parsed


def extract_entities(
    transcript: str, usage: rl.SessionUsage, api_key=None
) -> list[dict[str, Any]]:
    rl.guard_generation(usage)
    parsed, i, o = _chat_json(
        prompts.NER_SYSTEM,
        prompts.NER_USER_TEMPLATE.format(transcript=transcript),
        MODEL_NER,
        api_key,
    )
    rl.record_generation(usage, i, o, MODEL_NER)
    ents = parsed.get("entities", [])
    return ents if isinstance(ents, list) else []


def research_flags(
    turns: list[dict[str, Any]],
    soap: dict[str, Any],
    usage: rl.SessionUsage,
    model: str | None = None,
    api_key=None,
) -> list[dict[str, Any]]:
    model = model or MODEL_FLAGS
    rl.guard_generation(usage)
    parsed, i, o = _chat_json(
        prompts.RESEARCH_FLAG_SYSTEM,
        prompts.RESEARCH_FLAG_USER_TEMPLATE.format(
            diarized=_format_diarized(turns), soap=json.dumps(soap)
        ),
        model,
        api_key,
    )
    rl.record_generation(usage, i, o, model)
    flags = parsed.get("flags", [])
    return flags if isinstance(flags, list) else []
# end of pipeline stages
