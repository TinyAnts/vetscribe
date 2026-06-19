"""
VetScribe — veterinary consultation transcription research prototype.

Research artifact only (not a commercial product). Pipeline:
  Record/Upload -> Whisper transcribe -> GPT turn inference (diarize) ->
  SOAP -> Owner summary -> Entities -> Research flags -> Export.

OpenAI-only build. Diarization is a text heuristic (study limitation).
Public demo is rate-limited and budget-capped; it is a SHOWCASE, not the
time-to-document study instrument.
"""

from __future__ import annotations

import html
import json
import os

import gradio as gr

import pipeline
import rate_limit as rl
from instrumentation import SessionLog, LOG_DIR

# ---------------------------------------------------------------------------
# Theme / CSS (teal accent per design spec; light/dark via CSS variables)
# ---------------------------------------------------------------------------
ACCENT = "#1D9E75"
ACCENT_DARK = "#0F6E56"
ACCENT_LIGHT = "#E1F5EE"
ACCENT_MID = "#9FE1CB"
FLAG_FILL = "#FAEEDA"
FLAG_TEXT = "#412402"

CSS = f"""
:root {{
  --vs-accent: {ACCENT};
}}
/* centered, comfortable width (not stranded on ultrawide, not full-bleed) */
.gradio-container {{ max-width: 1120px !important; margin: 0 auto !important;
  padding-bottom: 64px !important; }}
footer {{ display: none !important; }}

.vs-header {{ display: flex; align-items: center; gap: 12px; padding: 6px 0 2px; }}
.vs-title {{ font-size: 20px; font-weight: 700; color: var(--vs-accent); }}
.vs-badge {{ font-size: 10px; font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase; padding: 3px 8px; border-radius: 999px;
  background: var(--vs-accent); color: #fff; }}
.vs-timer {{ margin-left: auto; font-variant-numeric: tabular-nums;
  color: var(--vs-accent); font-weight: 600; }}

/* small section captions */
.vs-section {{ font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .06em; color: var(--vs-accent); margin: 14px 0 2px; }}

/* progress stepper — clearly a status strip, NOT clickable tabs */
.vs-steps {{ display: flex; padding: 6px 4px 2px; }}
.vs-step {{ flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 5px; position: relative; }}
.vs-step .ln {{ position: absolute; top: 11px; left: 50%; width: 100%;
  height: 2px; background: rgba(127,127,127,.25); z-index: 0; }}
.vs-step .dot {{ width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center; font-size: 11px;
  font-weight: 600; background: rgba(127,127,127,.18); color: #8a8a8a; z-index: 1; }}
.vs-step .lbl {{ font-size: 11px; color: #8a8a8a; }}
.vs-step.done .dot {{ background: var(--vs-accent); color: #fff; }}
.vs-step.done .ln {{ background: var(--vs-accent); }}
.vs-step.done .lbl {{ color: var(--vs-accent); }}
.vs-step.active .dot {{ background: transparent; color: var(--vs-accent);
  border: 2px solid var(--vs-accent); }}
.vs-step.active .lbl {{ color: var(--vs-accent); font-weight: 600; }}

/* outputs — tinted fills + inherited (mode-adaptive) text so nothing washes out */
.vs-soap-sec {{ margin-bottom: 12px; }}
.vs-soap-label {{ font-weight: 700; color: var(--vs-accent);
  text-transform: uppercase; font-size: 11px; letter-spacing: .05em; margin-bottom: 2px; }}
.vs-disclaimer {{ font-size: 12px; color: inherit;
  background: rgba(186,117,23,.16); border-left: 3px solid #BA7517;
  padding: 8px 11px; border-radius: 6px; margin-top: 8px; }}
.vs-owner-banner {{ background: rgba(29,158,117,.14);
  border-left: 3px solid var(--vs-accent); padding: 10px 12px;
  border-radius: 6px; margin-bottom: 10px; color: inherit; }}
.vs-chip {{ display: inline-block; padding: 4px 11px; margin: 3px 3px 0 0;
  border-radius: 999px; font-size: 12px; color: inherit;
  background: rgba(127,127,127,.15); border: 0.5px solid rgba(127,127,127,.25); }}
.vs-chip.finding {{ background: rgba(29,158,117,.18); }}
.vs-chip.differential {{ background: rgba(186,117,23,.20); }}
.vs-chip.procedure {{ background: rgba(127,127,127,.18); }}
.vs-chip.drug {{ background: rgba(83,74,183,.22); }}
.vs-chip.follow_up {{ background: rgba(29,158,117,.30); }}
.vs-metric {{ display: inline-block; min-width: 120px; margin: 4px;
  padding: 11px 14px; border-radius: 10px; background: rgba(127,127,127,.10);
  border: 0.5px solid rgba(127,127,127,.22); text-align: left; }}
.vs-metric .v {{ font-size: 22px; font-weight: 700; color: var(--vs-accent); }}
.vs-metric .l {{ font-size: 11px; text-transform: uppercase;
  letter-spacing: .04em; opacity: .65; }}
.vs-subhead {{ font-size: 12px; font-weight: 600; opacity: .8; margin: 16px 0 6px; }}
.vs-flag {{ background: rgba(186,117,23,.14); border-left: 3px solid #BA7517;
  color: inherit; padding: 9px 11px; border-radius: 6px; margin: 6px 0; }}
.vs-turn {{ margin: 6px 0; }}
.vs-turn .spk-vet {{ color: var(--vs-accent); font-weight: 700; }}
.vs-turn .spk-owner {{ color: #8a8a8a; font-weight: 700; }}

/* big, prominent process button */
.vs-process button {{ font-size: 16px !important; font-weight: 600 !important;
  padding: 14px !important; }}

/* recorder card (native gr.Audio, scoped) — playback stays intact */
.vs-recorder {{ background: transparent; border: 1px solid rgba(127,127,127,.25);
  border-radius: 14px; padding: 10px; }}
.vs-recorder button[aria-label="Record"], .vs-recorder button[title="Record"],
.vs-recorder button.record-button, .vs-recorder .record-button, .vs-recorder .record {{
  background: var(--vs-accent) !important; color: #fff !important;
  border: none !important; border-radius: 10px !important; }}
.vs-recorder button[aria-label="Stop recording"], .vs-recorder button[aria-label="Stop"],
.vs-recorder button[title="Stop"], .vs-recorder .stop-button, .vs-recorder .stop {{
  background: #A32D2D !important; color: #fff !important; border: none !important; }}

/* loading / thinking animations */
@keyframes vs-spin {{ to {{ transform: rotate(360deg); }} }}
@keyframes vs-pulse {{
  0% {{ box-shadow: 0 0 0 0 rgba(29,158,117,.45); }}
  70% {{ box-shadow: 0 0 0 9px rgba(29,158,117,0); }}
  100% {{ box-shadow: 0 0 0 0 rgba(29,158,117,0); }} }}
@keyframes vs-blink {{ 0%,20% {{ opacity: .2; }} 50% {{ opacity: 1; }} 100% {{ opacity: .2; }} }}
.vs-step.active .dot {{ animation: vs-pulse 1.4s infinite; }}
.vs-working {{ display: flex; align-items: center; gap: 12px;
  padding: 18px 4px; font-size: 14px; color: inherit; }}
.vs-spinner {{ width: 22px; height: 22px; border-radius: 50%;
  border: 3px solid rgba(29,158,117,.25); border-top-color: var(--vs-accent);
  animation: vs-spin .8s linear infinite; flex: 0 0 auto; }}
.vs-dots span {{ animation: vs-blink 1.4s infinite; }}
.vs-dots span:nth-child(2) {{ animation-delay: .2s; }}
.vs-dots span:nth-child(3) {{ animation-delay: .4s; }}

/* full-screen processing overlay (greys out the page until done) */
.vs-overlay {{ position: fixed; inset: 0; z-index: 9999;
  background: rgba(8,12,16,.72); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center; }}
.vs-overlay-box {{ display: flex; flex-direction: column; align-items: center;
  gap: 16px; color: #fff; font-size: 16px; font-weight: 500; text-align: center; }}
.vs-overlay .vs-spinner {{ width: 46px; height: 46px; border-width: 4px;
  border-color: rgba(255,255,255,.25); border-top-color: var(--vs-accent); }}
"""

STEPS = ["Record", "Transcribe", "Diarize", "Generate", "Export"]


def pipeline_html(active_idx: int) -> str:
    """Render the 5-step progress bar. active_idx steps before it are done."""
    cells = []
    n = len(STEPS)
    for i, name in enumerate(STEPS):
        if i < active_idx:
            cls, dot = "done", "✓"
        elif i == active_idx:
            cls, dot = "active", str(i + 1)
        else:
            cls, dot = "", str(i + 1)
        line = "" if i == n - 1 else '<div class="ln"></div>'
        cells.append(
            f'<div class="vs-step {cls}">{line}'
            f'<div class="dot">{dot}</div><span class="lbl">{name}</span></div>'
        )
    return f'<div class="vs-steps">{"".join(cells)}</div>'


def header_html(timer: str = "00:00") -> str:
    return (
        '<div class="vs-header">'
        '<span class="vs-title">VetScribe</span>'
        '<span class="vs-badge">research prototype</span>'
        f'<span class="vs-timer">⏱ {timer}</span>'
        "</div>"
    )


def working_html(label: str) -> str:
    """Animated spinner + label shown in a panel while a stage runs."""
    return (
        '<div class="vs-working"><span class="vs-spinner"></span>'
        f"<span>{html.escape(label)}"
        '<span class="vs-dots"><span>.</span><span>.</span><span>.</span></span>'
        "</span></div>"
    )


OVERLAY_HTML = (
    '<div class="vs-overlay"><div class="vs-overlay-box">'
    '<span class="vs-spinner"></span>'
    "<div>Processing consultation…</div>"
    '<div style="font-size:13px;opacity:.8">Transcribing, separating speakers '
    "and writing the notes. This can take a moment.</div>"
    "</div></div>"
)


def show_overlay():
    return gr.update(value=OVERLAY_HTML, visible=True)


def hide_overlay():
    return gr.update(value="", visible=False)


def _make_pdf(session_id):
    """Build a PDF from a saved session's results.json; reveal the download."""
    if not session_id:
        return gr.update(visible=False)
    try:
        with open(os.path.join(LOG_DIR, session_id, "results.json"),
                  encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return gr.update(visible=False)
    try:
        import pdf_export  # lazy: a missing reportlab won't break app startup

        safe = "".join(
            c for c in (d.get("patient_label") or "case")
            if c.isalnum() or c in " -_"
        ).strip()[:40] or "case"
        out = os.path.join(LOG_DIR, session_id, f"VetScribe_{safe}.pdf")
        pdf_export.build_pdf(d, out)
        return gr.update(value=out, visible=True)
    except Exception:  # noqa: BLE001 - never crash the UI on export failure
        return gr.update(visible=False)


def export_pdf(log):
    """Export the CURRENT session (from Review)."""
    return _make_pdf(getattr(log, "session_id", None))


def export_case_pdf(session_id):
    """Export a PAST case selected in the history dropdown."""
    return _make_pdf(session_id)


# ---------------------------------------------------------------------------
# Rendering helpers for outputs
# ---------------------------------------------------------------------------
def render_transcript(turns: list[dict]) -> str:
    if not turns:
        return '<span style="opacity:.55">No transcript yet.</span>'
    rows = []
    for t in turns:
        spk = t.get("speaker", "?")
        cls = "spk-vet" if spk.lower().startswith("vet") else "spk-owner"
        start = t.get("start")
        ts = f' <small>[{int(start)//60:02d}:{int(start)%60:02d}]</small>' if isinstance(start, (int, float)) else ""
        rows.append(
            f'<div class="vs-turn"><span class="{cls}">{html.escape(spk)}</span>'
            f'{ts}: {html.escape(t.get("text",""))}</div>'
        )
    return "".join(rows)


def render_soap(soap: dict) -> str:
    if not soap:
        return '<span style="opacity:.55">SOAP note will appear here after processing.</span>'
    sec = []
    for key, label in [
        ("subjective", "Subjective"),
        ("objective", "Objective"),
        ("assessment", "Assessment"),
        ("plan", "Plan"),
    ]:
        val = html.escape(str(soap.get(key, "Not documented in consultation.")))
        sec.append(
            f'<div class="vs-soap-sec"><div class="vs-soap-label">{label}</div>'
            f"<div>{val}</div></div>"
        )
    doses = soap.get("drug_dose_mentions") or []
    if doses:
        items = "".join(f"<li>{html.escape(str(d))}</li>" for d in doses)
        sec.append(
            f'<div class="vs-disclaimer"><b>Dosing mentions flagged for review:</b>'
            f"<ul>{items}</ul></div>"
        )
    sec.append(
        '<div class="vs-disclaimer">AI-generated · a clinician must verify '
        "before signing.</div>"
    )
    return "".join(sec)


def render_owner(owner: dict) -> str:
    if not owner:
        return '<span style="opacity:.55">Owner summary will appear here after processing.</span>'
    body = html.escape(str(owner.get("summary", "")))
    follow = html.escape(str(owner.get("follow_up", "")))
    return (
        '<div class="vs-owner-banner">A plain-language summary for the pet '
        "owner.</div>"
        f"<div>{body}</div>"
        + (f'<div class="vs-disclaimer"><b>Follow-up:</b> {follow}</div>' if follow else "")
    )


def render_insights(metrics: dict, entities: list[dict], flags: list[dict]) -> str:
    cards = ""
    for label, val in [
        ("Consult duration", metrics.get("duration", "—")),
        ("Est. time saved", metrics.get("time_saved", "—")),
        ("Vet talk ratio", metrics.get("vet_ratio", "—")),
        ("Entities", metrics.get("entity_count", "—")),
    ]:
        cards += f'<div class="vs-metric"><div class="v">{html.escape(str(val))}</div><div class="l">{label}</div></div>'

    chips = "".join(
        f'<span class="vs-chip {html.escape(e.get("type","procedure"))}">{html.escape(e.get("text",""))}</span>'
        for e in entities
    ) or "<i>No entities extracted.</i>"

    if flags:
        flag_html = "".join(
            f'<div class="vs-flag"><b>{html.escape(f.get("item",""))}</b><br>'
            f'<small>Evidence: “{html.escape(f.get("evidence",""))}” — '
            f'{html.escape(f.get("why",""))}</small></div>'
            for f in flags
        )
    else:
        flag_html = "<i>No research flags raised.</i>"

    return (
        f'<div>{cards}</div>'
        '<div class="vs-subhead">Clinical entities</div>'
        f"<div>{chips}</div>"
        '<div class="vs-subhead" style="opacity:.6">Research flags · human–AI gap</div>'
        f"{flag_html}"
    )


# ---------------------------------------------------------------------------
# Case persistence + history (TEXT ONLY — never the audio, to save space)
# ---------------------------------------------------------------------------
def save_case(log, patient, model, turns, soap, owner, entities, flags, metrics):
    """Persist a processed consult's text results for later review. No audio."""
    data = {
        "session_id": log.session_id,
        "created_utc": log.created_utc,
        "patient_label": log.patient_label or patient,
        "patient": patient,
        "model": model,
        "turns": turns,
        "soap": soap,
        "owner": owner,
        "entities": entities,
        "flags": flags,
        "metrics": metrics,
    }
    try:
        with open(os.path.join(log.folder(), "results.json"), "w",
                  encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
    except OSError:
        pass


def list_cases():
    """Dropdown choices [(label, session_id)] for saved cases, newest first."""
    cases = []
    try:
        entries = os.listdir(LOG_DIR)
    except FileNotFoundError:
        return []
    for sid in entries:
        path = os.path.join(LOG_DIR, sid, "results.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        when = (d.get("created_utc") or "")[:16].replace("T", " ")
        label = (f"{when} · {d.get('patient_label', '?')} · "
                 f"{len(d.get('entities', []))} entities")
        cases.append((label, sid, d.get("created_utc", "")))
    cases.sort(key=lambda c: c[2], reverse=True)
    return [(lbl, sid) for lbl, sid, _ in cases]


def refresh_cases():
    return gr.update(choices=list_cases())


def render_case(session_id):
    """Render a saved case's transcript + SOAP + owner + insights in one view."""
    if not session_id:
        return '<span style="opacity:.55">Select a past case to review it.</span>'
    try:
        with open(os.path.join(LOG_DIR, session_id, "results.json"),
                  encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return '<span style="opacity:.55">Could not load that case.</span>'
    return (
        f'<div class="vs-section" style="margin-top:0">'
        f'{html.escape(str(d.get("patient", "")))} · '
        f'{html.escape(str(d.get("model", "")))}</div>'
        '<div class="vs-subhead">Transcript</div>'
        f'{render_transcript(d.get("turns", []))}'
        '<div class="vs-subhead">SOAP note</div>'
        f'{render_soap(d.get("soap", {}))}'
        '<div class="vs-subhead">Owner summary</div>'
        f'{render_owner(d.get("owner", {}))}'
        '<div class="vs-subhead">Insights</div>'
        f'{render_insights(d.get("metrics", {}), d.get("entities", []), d.get("flags", []))}'
    )


# ---------------------------------------------------------------------------
# Core processing callback
# ---------------------------------------------------------------------------
def new_session(patient_name, species, age, study_mode, participant_id):
    """Create a fresh session + patient folder."""
    log = SessionLog(
        study_mode=bool(study_mode),
        participant_id=participant_id or None,
        patient_label=(patient_name or "demo")[:40],
    )
    log.folder()
    usage = rl.SessionUsage()
    banner = (
        f"New session **{log.session_id}** created for patient "
        f"**{html.escape(patient_name or 'Unnamed')}**. "
        "Record or upload the consultation, then press *Process consultation*."
    )
    empty_tx = '<span style="opacity:.55">No transcript yet.</span>'
    empty_soap = '<span style="opacity:.55">SOAP note will appear here after processing.</span>'
    empty_owner = '<span style="opacity:.55">Owner summary will appear here after processing.</span>'
    empty_ins = '<span style="opacity:.55">Insights will appear here after processing.</span>'
    return (
        log,                                       # log_state
        usage,                                     # usage_state
        banner,                                    # session_banner
        header_html("00:00"),                      # header
        pipeline_html(0),                          # pipeline_bar
        gr.update(value=None, visible=True),       # audio (cleared, recorder shown)
        gr.update(value=None, visible=False),      # playback (hidden)
        gr.update(visible=False),                  # rerecord_btn (hidden)
        empty_tx,                                  # transcript_html
        empty_soap,                                # soap_html
        empty_owner,                               # owner_html
        empty_ins,                                 # insights_html
        gr.update(choices=list_cases()),           # history_dd (refreshed)
    )


_ALT_MODEL = {"gpt-5.4": "gpt-5.5", "gpt-5.5": "gpt-5.4", "gpt-5.4-mini": "gpt-5.4"}


def _soap_compare_html(soap_a, model_a, soap_b, model_b):
    """Side-by-side SOAP for two models so the user can A/B quality vs cost."""
    col = (
        '<div style="flex:1;min-width:0">'
        '<div style="font-weight:700;color:{c};margin-bottom:6px">{m}</div>{body}</div>'
    )
    left = col.format(c=ACCENT_DARK, m=html.escape(model_a), body=render_soap(soap_a))
    right = col.format(c=ACCENT_DARK, m=html.escape(model_b), body=render_soap(soap_b))
    return (
        '<div style="display:flex;gap:14px">'
        f"{left}"
        '<div style="width:1px;background:var(--vs-accent-mid)"></div>'
        f"{right}</div>"
    )


def process_consultation(
    audio_path, patient_name, species, age, model, compare, api_key, log, usage
):
    """Run the full pipeline. Yields progressive UI updates. `api_key` is the
    visitor-supplied key (BYOK); empty falls back to env/.env for local use."""
    api_key = (api_key or "").strip() or None
    if log is None or usage is None:
        log = SessionLog()
        usage = rl.SessionUsage()

    patient = f"{patient_name or 'Unnamed'} — {species or '?'}, {age or '?'}"

    try:
        if not audio_path:
            raise rl.RateLimitError("No audio. Record or upload a clip first.")

        log.start_pipeline()
        log.consult_seconds = pipeline.audio_duration_seconds(audio_path)

        # Stage 2: transcribe
        yield (pipeline_html(1),
               gr.update(value=working_html("Transcribing the audio")),
               gr.update(value=working_html("Waiting for transcript")),
               gr.update(), gr.update(), log, usage)
        transcript = pipeline.transcribe(audio_path, usage, api_key=api_key)

        # Stage 3: diarize
        yield (pipeline_html(2),
               gr.update(value=working_html("Separating speakers")),
               gr.update(), gr.update(), gr.update(), log, usage)
        turns = pipeline.diarize(transcript, usage, api_key=api_key)

        # Stage 4: generate
        yield (pipeline_html(3),
               gr.update(value=render_transcript(turns)),
               gr.update(value=working_html("Writing the SOAP note")),
               gr.update(value=working_html("Writing the owner summary")),
               gr.update(value=working_html("Computing insights")),
               log, usage)
        model = model or pipeline.MODEL_SOAP
        soap = pipeline.generate_soap(patient, turns, usage, model=model, api_key=api_key)
        owner = pipeline.generate_owner_summary(patient, soap, usage, api_key=api_key)
        entities = pipeline.extract_entities(transcript, usage, api_key=api_key)
        flags = pipeline.research_flags(turns, soap, usage, model=model, api_key=api_key)

        # Optional A/B: regenerate SOAP+flags with the alternate model. Counts
        # as extra generations (gated by the same per-session/budget guards).
        soap_html_value = render_soap(soap)
        if compare:
            alt = _ALT_MODEL.get(model, "gpt-5.5")
            soap_alt = pipeline.generate_soap(patient, turns, usage, model=alt, api_key=api_key)
            flags_alt = pipeline.research_flags(turns, soap_alt, usage, model=alt, api_key=api_key)
            soap_html_value = _soap_compare_html(soap, model, soap_alt, alt)
            # Surface the flag-count delta — a model-quality signal for the paper.
            metrics_note = (
                f"Flags: {model}={len(flags)} vs {alt}={len(flags_alt)}"
            )
        else:
            metrics_note = ""

        log.stop_pipeline()

        # Metrics
        vet_words = sum(len(t.get("text", "").split()) for t in turns
                        if t.get("speaker", "").lower().startswith("vet"))
        total_words = sum(len(t.get("text", "").split()) for t in turns) or 1
        dur = log.consult_seconds
        metrics = {
            "duration": f"{int(dur)//60}m {int(dur)%60}s" if dur else "—",
            # ILLUSTRATIVE ONLY — fixed 6-min manual baseline placeholder. The
            # real time-delta comes from instrumentation.py study runs, not this.
            "time_saved": f"~{max(0, 6 - log.pipeline_seconds/60):.1f} min*",
            "vet_ratio": f"{100*vet_words/total_words:.0f}%",
            "entity_count": str(len(entities)),
        }
        log.save()
        save_case(log, patient, model, turns, soap, owner, entities, flags, metrics)

        insights_value = render_insights(metrics, entities, flags)
        if metrics_note:
            insights_value += (
                f'<div class="vs-disclaimer">{html.escape(metrics_note)}</div>'
            )

        yield (pipeline_html(4),
               gr.update(value=render_transcript(turns)),
               gr.update(value=soap_html_value),
               gr.update(value=render_owner(owner)),
               gr.update(value=insights_value),
               log, usage)

    except rl.RateLimitError as e:
        yield (pipeline_html(0),
               gr.update(),
               gr.update(value=f'<div class="vs-flag">⚠ {html.escape(str(e))}</div>'),
               gr.update(), gr.update(), log, usage)
    except Exception as e:  # noqa: BLE001 - surface any backend error safely
        yield (pipeline_html(0),
               gr.update(),
               gr.update(value=f'<div class="vs-flag">Error: {html.escape(str(e))}</div>'),
               gr.update(), gr.update(), log, usage)


# ---------------------------------------------------------------------------
# UI assembly
# ---------------------------------------------------------------------------
def build_app() -> gr.Blocks:
    with gr.Blocks(css=CSS, title="VetScribe", theme=gr.themes.Soft()) as demo:
        log_state = gr.State(None)
        usage_state = gr.State(None)

        # full-screen processing overlay (hidden until a consult is running)
        overlay = gr.HTML("", visible=False)

        header = gr.HTML(header_html("00:00"))
        gr.HTML(
            '<div class="vs-disclaimer">Research prototype — do not upload real, '
            "identifiable recordings to the public demo. Synthetic or "
            "pre-consented audio only.</div>"
        )

        # ---- 1 · Patient & model (top, before recording) ----
        gr.HTML('<div class="vs-section">1 · Patient &amp; model</div>')
        with gr.Row():
            patient_name = gr.Textbox(label="Patient", value="Max", scale=2)
            species = gr.Textbox(
                label="Species / breed", value="Canine — Golden Retriever", scale=3
            )
            age = gr.Textbox(label="Age", value="4y MN", scale=1)
        with gr.Row():
            model_dd = gr.Dropdown(
                choices=["gpt-5.4", "gpt-5.5", "gpt-5.4-mini"],
                value="gpt-5.4",
                label="Model (SOAP & flags)",
                scale=2,
            )
            compare_chk = gr.Checkbox(
                label="Compare vs alternate", value=False, scale=1
            )
        api_key_box = gr.Textbox(
            label="Your OpenAI API key",
            type="password",
            placeholder="sk-...  — used only for this session, never stored. "
            "Leave blank if running locally with a .env file.",
        )
        with gr.Accordion("Study mode (excluded from demo stats)", open=False):
            study_mode = gr.Checkbox(label="This is a study session", value=False)
            participant_id = gr.Textbox(label="Participant ID", value="")
        with gr.Row():
            new_btn = gr.Button("New patient / session", variant="secondary")
        session_banner = gr.Markdown("_No active session._")

        # ---- 2 · Record ----
        gr.HTML('<div class="vs-section">2 · Record consultation</div>')
        audio = gr.Audio(
            sources=["microphone", "upload"],
            type="filepath",
            label="Record (pause/stop supported) or upload — play it back before processing",
            elem_classes=["vs-recorder"],
        )
        # Dedicated playback player. Gradio's INPUT audio widget has a known bug
        # where recorded mic audio uploads but won't play back inline
        # (gradio-app/gradio#5575); the same file plays fine in an OUTPUT
        # component, so we mirror it here for review before processing.
        playback = gr.Audio(
            label="▶ Review your recording",
            interactive=False,
            visible=False,
            elem_classes=["vs-recorder"],
        )
        rerecord_btn = gr.Button(
            "↻ Record again", variant="secondary", visible=False
        )
        process_btn = gr.Button(
            "Process consultation", variant="primary", elem_classes=["vs-process"]
        )

        # progress stepper (status only)
        pipeline_bar = gr.HTML(pipeline_html(0))

        # ---- 3 · Review (transcript first, then AI outputs) ----
        gr.HTML('<div class="vs-section">3 · Review</div>')
        with gr.Tabs():
            with gr.Tab("Transcript"):
                transcript_html = gr.HTML(
                    '<span style="opacity:.55">No transcript yet.</span>'
                )
            with gr.Tab("SOAP note"):
                soap_html = gr.HTML(
                    '<span style="opacity:.55">SOAP note will appear here after processing.</span>'
                )
            with gr.Tab("Owner summary"):
                owner_html = gr.HTML(
                    '<span style="opacity:.55">Owner summary will appear here after processing.</span>'
                )
            with gr.Tab("Insights"):
                insights_html = gr.HTML(
                    '<span style="opacity:.55">Insights will appear here after processing.</span>'
                )

        # ---- Export (the 5th pipeline step) ----
        export_btn = gr.Button(
            "⬇ Export this consultation as PDF", elem_classes=["vs-process"]
        )
        pdf_file = gr.File(label="Your PDF (click to download)", visible=False,
                           interactive=False)

        # ---- 4 · Past cases (saved transcripts/insights only — no audio) ----
        gr.HTML('<div class="vs-section">4 · Past cases</div>')
        with gr.Row():
            history_dd = gr.Dropdown(
                choices=list_cases(),
                label="Saved cases (newest first)",
                value=None,
                scale=3,
            )
            refresh_btn = gr.Button("↻ Refresh", scale=1)
        history_view = gr.HTML(
            '<span style="opacity:.55">Select a past case to review its '
            "transcript, SOAP and insights.</span>"
        )
        export_case_btn = gr.Button(
            "⬇ Export selected case as PDF", elem_classes=["vs-process"]
        )
        case_pdf_file = gr.File(label="Past-case PDF (click to download)",
                                visible=False, interactive=False)

        # Show recorder OR playback, never both. On capture, collapse the
        # recorder and reveal the working review player + a "record again" button.
        def _on_audio_change(p):
            has = bool(p)
            return (
                gr.update(visible=not has),       # recorder
                gr.update(value=p, visible=has),  # playback
                gr.update(visible=has),           # record-again button
            )

        audio.change(
            _on_audio_change, inputs=audio, outputs=[audio, playback, rerecord_btn]
        )

        def _record_again():
            return (
                gr.update(value=None, visible=True),
                gr.update(visible=False),
                gr.update(visible=False),
            )

        rerecord_btn.click(
            _record_again, outputs=[audio, playback, rerecord_btn]
        )

        new_btn.click(
            new_session,
            inputs=[patient_name, species, age, study_mode, participant_id],
            outputs=[
                log_state, usage_state, session_banner, header, pipeline_bar,
                audio, playback, rerecord_btn,
                transcript_html, soap_html, owner_html, insights_html,
                history_dd,
            ],
        )

        # show overlay -> run pipeline -> hide overlay -> refresh history.
        # Chaining keeps the grey-out visible for the whole run without
        # touching process_consultation's yields.
        (
            process_btn.click(show_overlay, outputs=overlay)
            .then(
                process_consultation,
                inputs=[audio, patient_name, species, age, model_dd, compare_chk,
                        api_key_box, log_state, usage_state],
                outputs=[
                    pipeline_bar, transcript_html, soap_html, owner_html,
                    insights_html, log_state, usage_state,
                ],
            )
            .then(hide_overlay, outputs=overlay)
            .then(refresh_cases, outputs=history_dd)
        )

        export_btn.click(export_pdf, inputs=[log_state], outputs=[pdf_file])
        history_dd.change(render_case, inputs=history_dd, outputs=history_view)
        refresh_btn.click(refresh_cases, outputs=history_dd)
        export_case_btn.click(
            export_case_pdf, inputs=[history_dd], outputs=[case_pdf_file]
        )

    return demo


if __name__ == "__main__":
    build_app().queue(max_size=20).launch()
