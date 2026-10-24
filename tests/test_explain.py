"""Tests for task 8 explanations (src/explain.py).

These tests NEVER touch the network. They cover:
- extract_context + build_brief_prompt: only the computed numbers reach the prompt -- no
  invented facts, the suggestion text is NOT sent (so the brief cannot restate it), and
  the overlap-not-harm framing is present.
- template_brief: the deterministic fallback sentence summarizes only the numbers, keeps
  the overlap framing, and does NOT restate the suggestion.
- brief(): returns the template when the API client raises (stubbed to raise) and when
  there is no API key, so the app can never crash or hang on the LLM.
"""

import os
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(REPO_ROOT, "src")
for p in (REPO_ROOT, SRC_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import explain  # noqa: E402


# A representative lease_signals row (the real columns; a Rising case with revenue).
SAMPLE_ROW = {
    "lease_id": "OCS-A 0501",
    "lease_name": "Vineyard Wind 1",
    "species": "black_sea_bass",
    "svspp": "141",
    "delta": 2,
    "baseline": 0.42,
    "scenario": 0.61,
    "change": 0.452,
    "signal": "Rising",
    "suggestion": (
        "Fishing interest here is likely to grow over the project's life. Options to "
        "plan for: wider turbine spacing or transit lanes for mobile gear."
    ),
    "auc": 0.81,
    "n_cells": 4,
    "n_nearby_tows": 55,
    "avg_value": "1234567",
}

# A "no data" / Uncertain case with a near-zero baseline (the tricky formatting path).
NODATA_ROW = {
    "lease_id": "OCS-A 0482",
    "lease_name": "GSOE 1",
    "species": "atlantic_cod",
    "svspp": "073",
    "delta": 1,
    "baseline": 2.7e-05,
    "scenario": 2.7e-05,
    "change": 0.0,
    "signal": "Stable",
    "suggestion": "Today's exposure data is a fair guide to future overlap here.",
    "auc": 0.78,
    "avg_value": "no data",
}


# --- extract_context --------------------------------------------------------


def test_extract_context_formats_numbers():
    c = explain.extract_context(SAMPLE_ROW)
    assert c["species"] == "black sea bass"
    assert c["lease"] == "Vineyard Wind 1"
    assert c["delta"] == "2"
    assert c["baseline"] == "0.420"
    assert c["scenario"] == "0.610"
    assert c["change"] == "+45.2%"
    assert c["signal"] == "Rising"
    assert c["auc"] == "0.81"
    assert c["value"] == "$1,234,567/yr"
    assert c["suggestion"] == SAMPLE_ROW["suggestion"]


def test_extract_context_handles_no_data_and_tiny_baseline():
    c = explain.extract_context(NODATA_ROW)
    assert c["value"] == "no data"  # never $0
    assert c["baseline"] == "0.000"  # tiny baseline rounds to 0.000, not an error
    assert c["change"] == "+0.0%"


# --- build_brief_prompt: ONLY numbers + suggestion, overlap framing ---------


def test_build_brief_prompt_contains_the_numbers():
    c = explain.extract_context(SAMPLE_ROW)
    messages = explain.build_brief_prompt(c)
    assert [m["role"] for m in messages] == ["system", "user"]

    user = messages[1]["content"]
    # Every computed number appears in the user message.
    for value in (
        c["species"], c["lease"], c["delta"], c["baseline"], c["scenario"],
        c["change"], c["signal"], c["auc"], c["value"],
    ):
        assert value in user, f"missing {value!r} from prompt"


def test_build_brief_prompt_does_not_include_the_suggestion():
    # The brief summarizes only the numbers; the suggestion ("what to consider") is
    # rendered in its own section by the app and is NOT fed to the model, so the brief
    # cannot echo it and the two sections never duplicate on screen.
    c = explain.extract_context(SAMPLE_ROW)
    messages = explain.build_brief_prompt(c)
    whole = messages[0]["content"] + "\n" + messages[1]["content"]
    assert c["suggestion"] not in whole
    # A distinctive phrase from the fixed suggestion must not leak in either.
    assert "wider turbine spacing" not in whole
    assert "Suggestion:" not in whole  # no suggestion field label in the prompt


def test_build_brief_prompt_forbids_invented_facts_and_keeps_framing():
    c = explain.extract_context(SAMPLE_ROW)
    messages = explain.build_brief_prompt(c)
    system = messages[0]["content"].lower()
    user = messages[1]["content"].lower()
    whole = system + "\n" + user

    # The guardrail instructions are present: use ONLY the numbers, add no facts/causes/
    # advice, keep the overlap framing, no harm-to-fish, no build/don't-build verdict.
    assert "only the numbers" in whole
    assert "do not add facts" in whole or "do not add any other facts" in whole
    assert "fishing overlap, not harm to fish" in whole
    assert "verdict" in whole


def test_build_brief_prompt_injects_no_extra_species_knowledge():
    # The prompt must not smuggle in domain facts about the species beyond its name.
    # Build a context with a nonsense species token and confirm nothing else about it
    # leaks in (the only mention is the token we supplied).
    row = dict(SAMPLE_ROW, species="xyzzy_fish")
    messages = explain.build_brief_prompt(explain.extract_context(row))
    user = messages[1]["content"]
    assert user.count("xyzzy fish") == 1  # appears once, as the Species line only


# --- template_brief: deterministic, overlap framing -------------------------


def test_template_brief_reads_from_numbers():
    c = explain.extract_context(SAMPLE_ROW)
    text = explain.template_brief(c)
    assert "Black sea bass" in text
    assert "Vineyard Wind 1" in text
    assert "+45.2%" in text
    assert "+2" in text and "\u00b0C" in text
    assert "Rising" in text
    assert "change in fishing overlap, not harm to fish" in text


def test_template_brief_does_not_restate_the_suggestion():
    # The fallback summarizes only the numbers; it must NOT append/restate the fixed
    # suggestion sentence, which the app shows in its own separate section (no duplication).
    c = explain.extract_context(SAMPLE_ROW)
    text = explain.template_brief(c)
    assert c["suggestion"] not in text
    assert "wider turbine spacing" not in text


def test_template_brief_no_data_case():
    c = explain.extract_context(NODATA_ROW)
    text = explain.template_brief(c)
    assert "Atlantic cod" in text
    assert "Stable" in text
    assert "harm to fish" in text  # framing preserved even for the stable/no-data case


# --- brief(): falls back to the template on any failure ---------------------


class _RaisingClient:
    """A stub DeepSeek client whose create() always raises (network/timeout stand-in)."""

    class _Chat:
        class _Completions:
            def create(self, *args, **kwargs):
                raise RuntimeError("simulated network failure")

        completions = _Completions()

    chat = _Chat()


def test_brief_falls_back_to_template_when_client_raises(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key")  # force the call path
    result = explain.brief(SAMPLE_ROW, client=_RaisingClient())
    assert result == explain.template_brief(explain.extract_context(SAMPLE_ROW))


def test_brief_falls_back_to_template_when_no_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = explain.brief(SAMPLE_ROW)  # no key, no client -> template, no network
    assert result == explain.template_brief(explain.extract_context(SAMPLE_ROW))


def test_brief_uses_client_response_when_it_succeeds(monkeypatch):
    # A stub client that returns a canned message -> brief returns it verbatim (trimmed).
    class _OkClient:
        class _Chat:
            class _Completions:
                def create(self, *args, **kwargs):
                    class _Msg:
                        content = "  A short overlap note.  "

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        choices = [_Choice()]

                    return _Resp()

            completions = _Completions()

        chat = _Chat()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key")
    assert explain.brief(SAMPLE_ROW, client=_OkClient()) == "A short overlap note."


def test_brief_falls_back_when_response_is_empty(monkeypatch):
    class _EmptyClient:
        class _Chat:
            class _Completions:
                def create(self, *args, **kwargs):
                    class _Msg:
                        content = "   "

                    class _Choice:
                        message = _Msg()

                    class _Resp:
                        choices = [_Choice()]

                    return _Resp()

            completions = _Completions()

        chat = _Chat()

    monkeypatch.setenv("DEEPSEEK_API_KEY", "dummy-key")
    result = explain.brief(SAMPLE_ROW, client=_EmptyClient())
    assert result == explain.template_brief(explain.extract_context(SAMPLE_ROW))


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
