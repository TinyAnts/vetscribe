"""
rate_limit.py — Token-burn and abuse guard for the public VetScribe demo.

Design constraints (do NOT relax without a budget review):
  - Audio length is the dominant cost lever (Whisper is $/min, unbounded).
    Hard-cap per-clip duration BEFORE any API call.
  - A single malicious user can loop generations; cap generations/session.
  - A global daily $ kill-switch is the backstop. If the estimated spend for
    the UTC day exceeds DAILY_BUDGET_USD, every paid call is refused for all
    users until UTC midnight.

State is persisted to a small JSON file so the kill-switch survives a Space
restart within the same day. This is best-effort (HF Spaces ephemeral disk);
the per-session caps are the primary defense, the budget file is the backstop.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ----------------------------------------------------------------------------
# Tunable limits (override via environment in the HF Space settings)
# ----------------------------------------------------------------------------
MAX_AUDIO_SECONDS = int(os.getenv("VS_MAX_AUDIO_SECONDS", "300"))      # 5 min/clip
MAX_GENERATIONS_PER_SESSION = int(os.getenv("VS_MAX_GENS", "5"))
MAX_TRANSCRIBE_PER_SESSION = int(os.getenv("VS_MAX_TRANSCRIBE", "8"))
DAILY_BUDGET_USD = float(os.getenv("VS_DAILY_BUDGET_USD", "20.0"))

# Cost model (USD per 1K tokens), keyed by chat model. Verified against the
# OpenAI API pricing page (Standard tier, 2026-06). Update if pricing changes —
# these drive the budget kill-switch, so keep them current.
PRICING_PER_1K = {
    "gpt-5.5":      (0.005, 0.030),
    "gpt-5.4":      (0.0025, 0.015),
    "gpt-5.4-mini": (0.00075, 0.0045),
    "gpt-5.4-nano": (0.00020, 0.00125),
    # legacy fallback so an unknown model is still costed conservatively
    "gpt-4o":       (0.0025, 0.010),
}
# Unknown models fall back to the most expensive non-pro rate (fail safe = over-
# estimate, so the kill-switch trips earlier rather than later).
_FALLBACK_PER_1K = (0.005, 0.030)

# Transcription $/minute by model.
TRANSCRIBE_USD_PER_MIN = {
    "gpt-4o-transcribe": 0.006,
    "gpt-4o-mini-transcribe": 0.003,
    "whisper-1": 0.006,
}
_FALLBACK_TRANSCRIBE_PER_MIN = 0.006

_BUDGET_FILE = os.getenv("VS_BUDGET_FILE", "/tmp/vetscribe_budget.json")
_lock = threading.Lock()


class RateLimitError(Exception):
    """Raised when a request is refused. Message is user-safe."""


@dataclass
class SessionUsage:
    """Per-session counters. Lives in Gradio session state (not global)."""

    generations: int = 0
    transcriptions: int = 0
    est_cost_usd: float = 0.0
    started_at: float = field(default_factory=time.time)


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _read_budget() -> dict:
    try:
        with open(_BUDGET_FILE, "r") as fh:
            data = json.load(fh)
        if data.get("day") != _today_key():
            return {"day": _today_key(), "spent": 0.0}
        return data
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return {"day": _today_key(), "spent": 0.0}


def _write_budget(data: dict) -> None:
    try:
        with open(_BUDGET_FILE, "w") as fh:
            json.dump(data, fh)
    except OSError:
        # Ephemeral disk may be read-only; per-session caps still apply.
        pass


def global_spent_today() -> float:
    with _lock:
        return _read_budget()["spent"]


def _add_global_spend(amount: float) -> None:
    with _lock:
        data = _read_budget()
        data["spent"] = round(data.get("spent", 0.0) + amount, 6)
        _write_budget(data)


def estimate_transcription_cost(audio_seconds: float, model: str) -> float:
    rate = TRANSCRIBE_USD_PER_MIN.get(model, _FALLBACK_TRANSCRIBE_PER_MIN)
    return (audio_seconds / 60.0) * rate


def estimate_gpt_cost(in_tokens: int, out_tokens: int, model: str) -> float:
    in_rate, out_rate = PRICING_PER_1K.get(model, _FALLBACK_PER_1K)
    return (in_tokens / 1000.0) * in_rate + (out_tokens / 1000.0) * out_rate


def check_global_budget() -> None:
    """Backstop kill-switch. Call before any paid API request."""
    if global_spent_today() >= DAILY_BUDGET_USD:
        raise RateLimitError(
            "The shared daily demo budget has been reached. The live demo "
            "resets at 00:00 UTC. (This protects the project's API key from "
            "runaway cost.)"
        )


def guard_transcription(usage: SessionUsage, audio_seconds: float) -> None:
    """Validate a transcription request. Raises RateLimitError if refused."""
    if audio_seconds <= 0:
        raise RateLimitError("No audio detected. Record or upload a clip first.")
    if audio_seconds > MAX_AUDIO_SECONDS:
        raise RateLimitError(
            f"Clip is {audio_seconds/60:.1f} min; the demo cap is "
            f"{MAX_AUDIO_SECONDS//60} min per recording. Trim and retry."
        )
    if usage.transcriptions >= MAX_TRANSCRIBE_PER_SESSION:
        raise RateLimitError(
            f"Session transcription limit reached "
            f"({MAX_TRANSCRIBE_PER_SESSION}). Reload to start a new session."
        )
    check_global_budget()


def guard_generation(usage: SessionUsage) -> None:
    """Validate an LLM generation request. Raises RateLimitError if refused."""
    if usage.generations >= MAX_GENERATIONS_PER_SESSION:
        raise RateLimitError(
            f"Session generation limit reached "
            f"({MAX_GENERATIONS_PER_SESSION}). Reload to start a new session."
        )
    check_global_budget()


def record_transcription(
    usage: SessionUsage, audio_seconds: float, model: str
) -> None:
    cost = estimate_transcription_cost(audio_seconds, model)
    usage.transcriptions += 1
    usage.est_cost_usd += cost
    _add_global_spend(cost)


def record_generation(
    usage: SessionUsage, in_tokens: int, out_tokens: int, model: str
) -> None:
    cost = estimate_gpt_cost(in_tokens, out_tokens, model)
    usage.generations += 1
    usage.est_cost_usd += cost
    _add_global_spend(cost)
