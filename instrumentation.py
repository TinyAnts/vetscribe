"""
instrumentation.py — Per-session timing log for the time-to-document study.

The PRIMARY evaluation metric is time-to-document delta. This module writes a
structured JSON record per session so the study can compute, per consult:

  - consult_seconds        : recording duration (proxy for consult length)
  - pipeline_seconds       : wall-clock from 'stop' to SOAP ready (AI cost)
  - review_seconds         : clinician time spent reviewing/editing the SOAP
                             (captured when they press 'Mark reviewed')
  - manual_baseline_seconds: time the clinician took to write the SOAP by hand
                             in the control condition (entered separately)

delta = manual_baseline_seconds - (pipeline_seconds + review_seconds)

IMPORTANT (study integrity): the public HuggingFace demo is a SHOWCASE, not the
study instrument. Only sessions explicitly tagged study_mode=True with a
participant_id should be included in the results table. Demo traffic is logged
but excluded from analysis.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

LOG_DIR = os.getenv("VS_LOG_DIR", "sessions")


@dataclass
class SessionLog:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    created_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    study_mode: bool = False
    participant_id: str | None = None
    patient_label: str | None = None  # non-PHI label only

    consult_seconds: float = 0.0
    pipeline_seconds: float = 0.0
    review_seconds: float = 0.0
    manual_baseline_seconds: float | None = None

    # internal stopwatches (not for export math directly)
    _pipeline_start: float | None = None
    _review_start: float | None = None

    def folder(self) -> str:
        path = os.path.join(LOG_DIR, self.session_id)
        os.makedirs(path, exist_ok=True)
        return path

    # --- stopwatch helpers ---------------------------------------------------
    def start_pipeline(self) -> None:
        self._pipeline_start = time.time()

    def stop_pipeline(self) -> None:
        if self._pipeline_start is not None:
            self.pipeline_seconds = round(time.time() - self._pipeline_start, 2)
            self._pipeline_start = None

    def start_review(self) -> None:
        self._review_start = time.time()

    def stop_review(self) -> None:
        if self._review_start is not None:
            self.review_seconds = round(time.time() - self._review_start, 2)
            self._review_start = None

    def delta_seconds(self) -> float | None:
        if self.manual_baseline_seconds is None:
            return None
        return round(
            self.manual_baseline_seconds
            - (self.pipeline_seconds + self.review_seconds),
            2,
        )

    # --- persistence ---------------------------------------------------------
    def export_dict(self) -> dict:
        d = {k: v for k, v in asdict(self).items() if not k.startswith("_")}
        d["delta_seconds"] = self.delta_seconds()
        return d

    def save(self) -> str:
        path = os.path.join(self.folder(), "session.json")
        try:
            with open(path, "w") as fh:
                json.dump(self.export_dict(), fh, indent=2)
        except OSError:
            pass  # ephemeral disk; non-fatal for the demo
        return path
