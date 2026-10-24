"""Explanations for Shifting Grounds (task 8).

Two pieces, both deliberately kept small and testable:

1. **SHAP temperature response** -- ``temperature_response(model, sample)`` builds a
   matplotlib figure showing how a species' predicted habitat suitability responds across
   bottom temperature (BOTTEMP), holding the model fixed. One figure per species, shown
   in the app's "Temperature response" tab.

2. **DeepSeek brief** -- ``brief(row)`` turns the already-computed numbers for one
   (lease, species, warming scenario) plus the fixed suggestion text into 2-3 plain
   sentences, via DeepSeek's OpenAI-compatible API. It NEVER crashes or hangs the app:
   the call is wrapped with a timeout and a broad try/except, and ANY failure (no key,
   network error, timeout, bad response) falls back to a deterministic template sentence
   built only from the numbers.

Guardrails (.kiro/steering/workflow.md), enforced here:
- Only computed numbers and the fixed suggestion text are ever sent to the LLM. The
  prompt instructs the model to rephrase/summarize ONLY those -- no new facts, no causes,
  no advice of its own. ``build_brief_prompt`` is a pure function so a test can assert
  exactly what is sent.
- The brief stays in "change in fishing overlap / planning signal" framing. It must never
  describe results as harm to fish, nor as a build / don't-build verdict. The prompt says
  so explicitly and the template fallback is worded the same way.
- The API key is read from ``DEEPSEEK_API_KEY`` in .env (via python-dotenv); it is never
  hard-coded, printed or logged.

Model / endpoint (design.md "## Explanations", D-012):
- base_url = https://api.deepseek.com (DeepSeek's OpenAI-compatible endpoint)
- model    = ``DEEPSEEK_MODEL`` env var, DEFAULTING to "deepseek-chat". Older notes said
  the default was "deepseek-flash", but the human chose deepseek-chat and the live .env
  uses it, so the code default is deepseek-chat (logged as D-027).
- timeout  = BRIEF_TIMEOUT seconds, with no automatic retries, so a slow or dead endpoint
  cannot stall the app -- it falls back to the template.
"""

from __future__ import annotations

import os
from typing import Any, Mapping

from dotenv import load_dotenv

# Load .env once at import so DEEPSEEK_API_KEY / DEEPSEEK_MODEL are available. .env is
# gitignored; we read values, never print them.
load_dotenv()

# --- DeepSeek endpoint config ----------------------------------------------

# DeepSeek's API is OpenAI-compatible (design.md "## Implementation notes").
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
# D-027 / D-012: default to deepseek-chat (the human's choice, and the live .env value)
# when DEEPSEEK_MODEL is unset, overriding the older "deepseek-flash" note in design.md.
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
# Keep the call short so the app never hangs; a slow endpoint falls back to the template.
BRIEF_TIMEOUT = 20.0  # seconds
# One shot, no SDK-internal retries -- a dead endpoint must fail fast to the template.
BRIEF_MAX_RETRIES = 0

# The two model features, for the SHAP sample frame.
FEATURES = ["BOTTEMP", "AVGDEPTH"]


# ---------------------------------------------------------------------------
# Formatting helpers (shared by the prompt and the template so both read the
# SAME numbers the same way)
# ---------------------------------------------------------------------------


def _fmt_suitability(value: Any) -> str:
    """A suitability (0-1 probability) as a 3-dp string, or 'n/a' when missing."""
    try:
        if value is None:
            return "n/a"
        f = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if f != f:  # NaN
        return "n/a"
    return f"{f:.3f}"


def _fmt_change(value: Any) -> str:
    """A percent change (stored as a fraction) as a signed percent, or 'n/a'."""
    try:
        if value is None:
            return "n/a"
        f = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if f != f:  # NaN
        return "n/a"
    return f"{f:+.1%}"


def _fmt_auc(value: Any) -> str:
    """Model test AUC as a 2-dp string, or 'n/a' when missing."""
    try:
        if value is None:
            return "n/a"
        f = float(value)
    except (TypeError, ValueError):
        return "n/a"
    if f != f:  # NaN
        return "n/a"
    return f"{f:.2f}"


def _fmt_value(value: Any) -> str:
    """The NOAA 5-year average fishing value as '$N/yr', or the literal 'no data'.

    The lease_signals ``avg_value`` cell is either a float-like string (a real average) or
    the "no data" sentinel (D-021); a missing value is never shown as $0.
    """
    if value is None:
        return "no data"
    text = str(value).strip()
    if text == "" or text.lower() == "no data":
        return "no data"
    try:
        return f"${float(text):,.0f}/yr"
    except (TypeError, ValueError):
        return "no data"


def _species_label(species: Any) -> str:
    """Human-readable species name from the processed key (e.g. 'atlantic_cod')."""
    if species is None:
        return "this species"
    return str(species).replace("_", " ").strip() or "this species"


def extract_context(row: Mapping[str, Any]) -> dict:
    """Pull ONLY the computed numbers + fixed suggestion text out of a lease_signals row.

    This is the single gate between the pipeline's data and the LLM: nothing that is not
    returned here can reach the prompt. Everything here is either a number computed by the
    offline pipeline or the fixed suggestion string from src/overlap.py -- no free text
    the model could treat as new facts.

    Returns a dict of display-ready strings/values:
      species, lease, delta, baseline, scenario, change, signal, auc, value, suggestion
    """
    delta = row.get("delta")
    try:
        delta_str = f"{int(delta)}" if delta is not None else "n/a"
    except (TypeError, ValueError):
        delta_str = "n/a"

    return {
        "species": _species_label(row.get("species")),
        "lease": str(row.get("lease_name") or row.get("lease_id") or "this lease area"),
        "delta": delta_str,
        "baseline": _fmt_suitability(row.get("baseline")),
        "scenario": _fmt_suitability(row.get("scenario")),
        "change": _fmt_change(row.get("change")),
        "signal": str(row.get("signal") or "Uncertain"),
        "auc": _fmt_auc(row.get("auc")),
        "value": _fmt_value(row.get("avg_value")),
        "suggestion": str(row.get("suggestion") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Prompt construction (pure, testable -- no network)
# ---------------------------------------------------------------------------

# The system instruction nails the two hard guardrails: use ONLY the supplied
# numbers/suggestion (no invented facts, causes or advice), and keep the overlap framing
# (never harm to fish, never a build / don't-build verdict).
BRIEF_SYSTEM_PROMPT = (
    "You write a short planning note about one offshore wind lease area and one fish "
    "species. Use ONLY the numbers and the suggestion provided. Do not add facts, "
    "causes or advice of your own. Do not speculate about why the numbers change. "
    "This shows change in fishing overlap, not harm to fish; never describe it as harm "
    "to fish, and never give a build or do-not-build verdict. Write 2-3 plain sentences "
    "for fishermen and planners."
)


def build_brief_prompt(context: Mapping[str, Any]) -> list[dict]:
    """Build the chat ``messages`` for the DeepSeek brief from a context dict.

    Pure function: no network, no SDK. ``context`` is the output of ``extract_context``
    (only computed numbers + the fixed suggestion text). The returned messages contain
    NOTHING the model could mistake for a new fact -- just the labelled numbers and the
    suggestion -- plus the explicit instruction to rephrase ONLY those. A unit test asserts
    that only these values appear.
    """
    c = dict(context)
    user = (
        f"Species: {c['species']}\n"
        f"Lease area: {c['lease']}\n"
        f"Warming scenario: +{c['delta']} \u00b0C bottom temperature\n"
        f"Habitat suitability inside the area: now {c['baseline']}, "
        f"scenario {c['scenario']} ({c['change']})\n"
        f"Signal: {c['signal']}\n"
        f"Model test AUC: {c['auc']}\n"
        f"Average annual fishing value from this area for this species "
        f"(NOAA, last 5 years): {c['value']}\n"
        f"Suggestion: {c['suggestion']}\n\n"
        "Write 2-3 plain sentences for fishermen and planners, using only the numbers "
        "and the suggestion above. Say that this shows change in fishing overlap, not "
        "harm to fish. Do not add any other facts, causes, advice or verdicts."
    )
    return [
        {"role": "system", "content": BRIEF_SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]


# ---------------------------------------------------------------------------
# Deterministic fallback template (pure, no network)
# ---------------------------------------------------------------------------


def template_brief(context: Mapping[str, Any]) -> str:
    """The deterministic fallback sentence, built only from the computed numbers.

    Matches design.md's fallback template, keeping the overlap framing (never harm to
    fish, never a verdict). Shown verbatim whenever the DeepSeek call fails for ANY
    reason. ``context`` is the output of ``extract_context``.
    """
    c = dict(context)
    sentence = (
        f"{c['species'].capitalize()} habitat inside {c['lease']} changes by "
        f"{c['change']} at +{c['delta']}\u00b0C bottom temperature "
        f"({c['signal']}). This shows change in fishing overlap, not harm to fish."
    )
    suggestion = c.get("suggestion", "")
    if suggestion:
        sentence = f"{sentence} {suggestion}"
    return sentence


# ---------------------------------------------------------------------------
# DeepSeek brief (the only function that touches the network)
# ---------------------------------------------------------------------------


def _deepseek_model() -> str:
    """The DeepSeek model name from the env, defaulting to deepseek-chat (D-027)."""
    return os.environ.get("DEEPSEEK_MODEL") or DEFAULT_DEEPSEEK_MODEL


def _make_client(api_key: str):
    """Construct the OpenAI-compatible client pointed at DeepSeek. Imported lazily so the
    pure helpers (and the tests of them) don't need the SDK."""
    from openai import OpenAI

    return OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_BASE_URL,
        timeout=BRIEF_TIMEOUT,
        max_retries=BRIEF_MAX_RETRIES,
    )


def brief(row: Mapping[str, Any], client: Any = None) -> str:
    """Return a 2-3 sentence plain-English brief for one lease_signals row.

    Calls DeepSeek with a prompt built ONLY from the computed numbers + the fixed
    suggestion text. On ANY failure -- missing key, network error, timeout, empty/odd
    response -- returns the deterministic ``template_brief`` instead, so the app never
    crashes or hangs because of the LLM.

    ``client`` is injectable for testing (pass a stub); when None a real DeepSeek client
    is built from DEEPSEEK_API_KEY. A test monkeypatches this to assert the fallback path.
    """
    context = extract_context(row)

    # No key -> straight to the template (no network attempt, nothing to leak).
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if client is None and not api_key:
        return template_brief(context)

    try:
        if client is None:
            client = _make_client(api_key)
        messages = build_brief_prompt(context)
        response = client.chat.completions.create(
            model=_deepseek_model(),
            messages=messages,
            temperature=0.3,
            max_tokens=220,
            timeout=BRIEF_TIMEOUT,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return template_brief(context)
        return text
    except Exception:
        # Any failure at all (auth, network, timeout, malformed response) -> template.
        return template_brief(context)


# ---------------------------------------------------------------------------
# SHAP temperature response (matplotlib figure, no network)
# ---------------------------------------------------------------------------


def temperature_response(model: Any, sample, n_grid: int = 60):
    """Build a bottom-temperature response figure for one trained species model.

    Shows how the model's predicted habitat suitability (probability of presence) responds
    across bottom temperature. We vary BOTTEMP across its observed range in ``sample``
    while holding AVGDEPTH at the sample median, and also overlay the per-row SHAP
    contribution of BOTTEMP (a SHAP dependence view) so the plot reads as "how bottom
    temperature drives suitability".

    ``model`` is a fitted HistGradientBoostingClassifier on FEATURES = [BOTTEMP, AVGDEPTH].
    ``sample`` is a DataFrame with those two columns (sampled upstream for speed). Returns
    a matplotlib Figure (Agg-safe); matplotlib and shap are imported lazily.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    import shap

    sample = sample[FEATURES].dropna().copy()
    # Keep it fast: cap the background the explainer sees.
    if len(sample) > 500:
        sample = sample.sample(500, random_state=42)

    bt = sample["BOTTEMP"].astype(float)
    depth_median = float(sample["AVGDEPTH"].astype(float).median())

    # 1) Mean response curve: sweep BOTTEMP, hold AVGDEPTH at the median.
    bt_lo, bt_hi = float(bt.min()), float(bt.max())
    grid_bt = np.linspace(bt_lo, bt_hi, n_grid)
    grid = pd.DataFrame({"BOTTEMP": grid_bt, "AVGDEPTH": depth_median})
    proba = model.predict_proba(grid[FEATURES])[:, 1]

    # 2) SHAP dependence: per-row SHAP value for BOTTEMP across the sample.
    #    TreeExplainer handles HistGradientBoosting; fall back gracefully if it can't.
    shap_bt = None
    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(sample[FEATURES])
        # Binary classifiers may return a list (one array per class) or a single array.
        if isinstance(shap_values, list):
            shap_values = shap_values[-1]
        shap_values = np.asarray(shap_values)
        if shap_values.ndim == 3:  # (n, features, classes)
            shap_values = shap_values[:, :, -1]
        shap_bt = shap_values[:, FEATURES.index("BOTTEMP")]
    except Exception:
        shap_bt = None

    fig, ax1 = plt.subplots(figsize=(5.6, 4.2))

    ax1.plot(
        grid_bt, proba, color="#d7301f", linewidth=2.2, zorder=3,
        label=f"Predicted suitability (depth held at {depth_median:.0f} m)",
    )
    ax1.set_xlabel("Bottom temperature (\u00b0C)")
    ax1.set_ylabel("Predicted habitat suitability", color="#d7301f")
    ax1.tick_params(axis="y", labelcolor="#d7301f")
    ax1.set_ylim(0, 1)

    if shap_bt is not None:
        ax2 = ax1.twinx()
        ax2.scatter(
            bt, shap_bt, s=12, alpha=0.35, color="#2171b5", zorder=2,
            label="SHAP contribution of bottom temp",
        )
        ax2.axhline(0, color="#bbbbbb", linewidth=0.8, zorder=1)
        ax2.set_ylabel("SHAP value (bottom temp)", color="#2171b5")
        ax2.tick_params(axis="y", labelcolor="#2171b5")
        # Merge legends from both axes.
        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", fontsize=8,
                   frameon=False)
    else:
        ax1.legend(loc="upper left", fontsize=8, frameon=False)

    ax1.set_title("Temperature response")
    fig.tight_layout()
    return fig
