# VetScribe — sharing the demo & protecting your API key

This guide answers: where to host it, how people try it, where they put their
key, and how to make sure **other people's usage never burns your tokens**.

---

## TL;DR

- **Code → GitHub** (open source, reproducibility for the paper).
- **Live demo → Hugging Face Spaces** (free, runs the Gradio app in a browser).
- **Keys → Bring-Your-Own-Key (BYOK).** Each visitor pastes *their own* OpenAI
  key into the app. It is used only for their session and never stored. **Your
  key is never on the public demo, so your token exposure is zero.**
- If you ever *do* want a frictionless demo on your own key, the app has a hard
  **daily-budget kill-switch** + per-session caps so your worst-case loss is a
  number you set.

---

## 1. Put the code on GitHub

1. Create a public repo, e.g. `vetscribe`.
2. Upload everything **except secrets**. The included `.gitignore` already
   excludes `.env`, `sessions/`, and `__pycache__/`. The upload folder ships with
   a `.env.example` (a placeholder) — never a real `.env`.
3. This is the citable artifact for the paper. (Optionally mint a DOI by
   connecting the repo to Zenodo.)

> If you ever upload a real `.env` by accident, treat the key as compromised:
> rotate it in the OpenAI dashboard immediately.

---

## 2. Deploy the live demo on Hugging Face Spaces

1. Create a free account at huggingface.co.
2. **New Space** → SDK: **Gradio** → choose the free CPU tier.
3. Upload the project files (or connect the GitHub repo). The Space auto-installs
   `requirements.txt` and runs `app.py`.
4. The Space gives you a public URL like
   `https://huggingface.co/spaces/<you>/vetscribe`. Anyone can open it.

That's the whole "how do people play with it" answer: they open the URL.

---

## 3. Where people put their key (BYOK) — the safe default

The app has a **"Your OpenAI API key"** field (password-masked). On the public
Space you **do not set any key as a secret.** Each visitor:

1. Gets their own key from `platform.openai.com/api-keys`.
2. Pastes it into the **"Your OpenAI API key"** field in the app.
3. Records/uploads a consult and presses **Process consultation**.

Their key is used only to make their own API calls, is never written to disk,
and disappears when they close the tab. **You pay nothing; you are never
exposed.** This is also exactly what you tell reviewers: *"To run the live
demo, provide your own OpenAI API key in the key field."*

---

## 4. If you want a no-key demo on YOUR key (optional, riskier)

Sometimes you want people to try it without needing a key. Then you put your
key on the Space **and rely on the built-in guardrails.** Understand the
trade-off first: anyone can spend your tokens up to the cap you set.

**Set the key as a Space secret (never in code):**
Space → Settings → *Variables and secrets* → New secret → name
`OPENAI_API_KEY`, value = your key.

**Then set hard limits** (same screen, as plain variables):

| Variable | What it does | Suggested |
|---|---|---|
| `VS_DAILY_BUDGET_USD` | Global kill-switch: refuses all paid calls once the day's estimated spend exceeds this. **Your worst-case daily loss.** | `5` |
| `VS_MAX_AUDIO_SECONDS` | Max audio length per clip (transcription is the cost driver) | `300` |
| `VS_MAX_GENS` | Max generations per session | `5` |
| `VS_MAX_TRANSCRIBE` | Max transcriptions per session | `8` |

How the protection works (in `rate_limit.py`):
- Every paid call is estimated and added to a daily running total.
- Once the total crosses `VS_DAILY_BUDGET_USD`, **all paid calls are refused
  until 00:00 UTC**, for everyone. So your maximum exposure for the day is
  roughly that budget.
- Per-session caps stop a single visitor from looping calls.

**Honest limitation:** per-session caps are session-scoped, so a determined
user can reload for a fresh session, or script requests. The *daily budget
kill-switch is the only hard guarantee* — set it to a number you're comfortable
losing in the worst case. For a public, unauthenticated demo, **BYOK (Section 3)
is still the safest choice.** A good middle ground: BYOK as the default, plus a
small `VS_DAILY_BUDGET_USD` (e.g. $5) so casual visitors without a key still get
a few free tries before the daily cap stops them.

**Extra hardening if you stay on your own key:**
- Make the Space **private**, or add a simple password gate, to limit who can
  reach it.
- Monitor spend with a hard monthly limit in your OpenAI billing settings
  (Settings → Limits) as a backstop independent of the app.

---

## 5. Privacy — do not skip this

- The disclaimer in the app already says so: **never upload real, identifiable
  patient/client recordings to a public demo.** Use synthetic or pre-consented
  audio only.
- The local **case history and PDF export write clinical text to disk**
  (`sessions/`). That's fine for your local machine but is a privacy problem on
  a shared/public Space. Before any public deployment, disable the local case
  store or scope it to in-memory-per-session, and keep export download-only.
- Rotate your key periodically, and immediately if it ever appears anywhere
  public (a commit, a screenshot, or a log).

---

## 6. Quick decision guide

| You want… | Do this |
|---|---|
| Reproducible code for the paper | GitHub (Section 1) |
| A live demo reviewers can run | HF Space + **BYOK** (Sections 2–3) |
| People to try it with no key | HF Space on your key + low `VS_DAILY_BUDGET_USD` (Section 4) |
| Zero token risk to you | BYOK only; never put your key on the Space |
