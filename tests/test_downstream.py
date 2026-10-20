"""The dashboard poller's flatten() and the conversation browser's Conv on a
phase-2 document, plus a phase-1 document for backwards compatibility.
No database and no network: both modules are imported for their pure parts."""
import datetime as dt
import importlib
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
pytest.importorskip("psycopg2")

os.environ.setdefault("DASHBOARD_HASH_SALT", "test")
sys.path.insert(0, str(ROOT / "dashboard")); sys.path.insert(0, str(ROOT / "browser"))
poller = importlib.import_module("export_to_postgres")
browser = importlib.import_module("server")

T0 = dt.datetime(2026, 10, 20, 10, 0, tzinfo=dt.timezone.utc)


def phase2_doc():
    return {
        "history": [{"role": "assistant", "content": "Obrigado! ...", "timestamp": T0},
                    {"role": "user", "content": "oi", "timestamp": T0 + dt.timedelta(minutes=1)},
                    {"role": "assistant", "content": "Entendi.", "timestamp": T0 + dt.timedelta(minutes=1, seconds=5)}],
        "updated_at": T0 + dt.timedelta(minutes=30), "language": "PT",
        "prompt_variant": "PT_prompt_C_refutational_v6", "variant_assigned_at": T0,
        "conversation_phase": "ended", "ended_reason": "button", "debriefed_at": T0 + dt.timedelta(minutes=30),
        "exit": {"choice": "rated", "at": T0 + dt.timedelta(minutes=30), "user_turns": 7},
        "intro_sent": True, "user_turn_count": 7, "page_loads": 2,
        "screening": {"age_18": "sim", "eligible_voter": "sim", "passed": True},
        "rating_pre": 3, "rating_pre_system": 2, "rating_post": 5, "rating_post_system": 4, "rating_exit": 6, "rating_exit_system": 5,
        "feeling_array": [
            {"score": 3, "score_system": 2, "message_index": 0, "slot": "pre", "timestamp": T0 - dt.timedelta(minutes=1),
             "events": [{"q": "system", "value": 2, "action": "confirmed", "at": "t"}]},
            {"score": 5, "score_system": 4, "message_index": 6, "slot": "post", "timestamp": T0 + dt.timedelta(minutes=20), "events": []},
            {"score": 6, "score_system": 5, "message_index": 7, "slot": "exit", "timestamp": T0 + dt.timedelta(minutes=30), "events": []},
        ],
        "first_message_raw": {"id": "web.1", "timestamp": "1760954400", "type": "text", "channel": "web",
                              "referral": {"source_type": "web_ad", "source_id": "open_question", "ctwa_clid": "fb.1"},
                              "web": {"query": {"utm_content": "open_question"}}},
        "referrals": [], "first_contacts_raw": [],
    }


def phase1_doc():
    return {"history": [], "updated_at": T0, "language": "PT", "prompt_variant": "PT_prompt_B_motivational_learning",
            "conversation_phase": "normal", "intro_sent": True, "user_turn_count": 8, "rating_pre": 40, "rating_post": 55,
            "feeling_array": [{"score": 40, "message_index": 0, "timestamp": T0}, {"score": 55, "message_index": 6, "timestamp": T0},
                              {"score": 60, "message_index": 12, "timestamp": T0}],
            "first_message_raw": {}, "referrals": [], "screening": {}}


def test_poller_flattens_phase2_fields():
    conv, msgs, ratings = poller.flatten("web_x", phase2_doc())
    assert conv["variant"] == "C_refutational_v6" and conv["phase"] == "ended" and conv["ended_reason"] == "button"
    assert conv["exit_choice"] == "rated" and conv["exit_at"] == T0 + dt.timedelta(minutes=30) and conv["variant_assigned_at"] == T0
    assert (conv["rating_pre"], conv["rating_pre_system"], conv["rating_post"], conv["rating_post_system"]) == (3, 2, 5, 4)
    assert (conv["rating_exit"], conv["rating_exit_system"]) == (6, 5)
    assert conv["later_ratings"].adapted == []          # exit is not a "later check-in"
    assert conv["screened_out_reason"] is None and conv["ad_source_id"] == "open_question"
    assert [(r[2], r[3], r[5], r[6]) for r in ratings] == [(0, 3, 2, "pre"), (6, 5, 4, "post"), (7, 6, 5, "exit")]
    assert len(msgs) == 3


def test_poller_keeps_phase1_documents_working():
    conv, _, ratings = poller.flatten("web_old", phase1_doc())
    assert conv["rating_pre"] == 40 and conv["rating_post"] == 55 and conv["rating_pre_system"] is None
    assert [x["score"] for x in conv["later_ratings"].adapted] == [60]
    assert [(r[5], r[6]) for r in ratings] == [(None, None)] * 3


def test_browser_conv_phase2_summary_and_csv():
    now = T0 + dt.timedelta(hours=1)
    c = browser.Conv("web_x", phase2_doc())
    s = c.summary(now)
    assert s["outcome"] == "ended button" and s["ended_reason"] == "button" and s["exit_choice"] == "rated"
    assert s["rating_change"] == 2 and s["rating_change_system"] == 2 and s["rating_exit"] == 6
    assert s["n_later_ratings"] == 0 and s["n_ratings"] == 3
    row = c.csv_row(now)
    assert set(browser.CSV_COLUMNS) >= {k for k in row if k not in ("phone", "profile_name")} - {"snippet"}
    assert row["ratings"] == "0:3;6:5;7:6" and row["ratings_system"] == "0:2;6:4;7:5"
    assert c.ratings[0]["n_taps"] == 1 and c.ratings[0]["slot"] == "pre"


def test_browser_outcomes():
    now = T0 + dt.timedelta(days=2)
    d = phase2_doc(); d.update(conversation_phase="screened_out", screened_out_reason="high_trust", debriefed_at=None, ended_reason=None)
    assert browser.Conv("a", d).outcome(now) == "high trust"
    d = phase2_doc(); d.update(conversation_phase="normal", debriefed_at=None, ended_reason=None)
    assert browser.Conv("b", d).outcome(now) == "abandoned after post"
    d = phase1_doc(); d.update(conversation_phase="ended", debriefed_at=T0)
    assert browser.Conv("c", d).outcome(now) == "debriefed"


def test_demo_source_documents_flatten_cleanly():
    for phone, d in browser.DemoSource(n=40).docs:
        conv, _, _ = poller.flatten(phone, d)
        browser.Conv(phone, d).csv_row(T0)
        assert conv["variant"] in ("A_control_v6", "B_motivational_v6", "C_refutational_v6", "")
