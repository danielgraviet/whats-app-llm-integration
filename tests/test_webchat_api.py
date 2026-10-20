"""Web chat HTTP API in demo mode (in-memory store, canned replies)."""
import os
import sys

import pytest

os.environ["WEBCHAT_DEMO"] = "1"
sys.argv = [sys.argv[0]]   # app.py inspects argv for --demo

from fastapi.testclient import TestClient  # noqa: E402

from services import prompt_service  # noqa: E402
from webchat import app as webapp  # noqa: E402

PT = webapp.trust_service.TRUST_PROMPTS["PT"]


@pytest.fixture(scope="module")
def http():
    webapp.configure()
    return TestClient(webapp.app)


META = {"query": {"utm_content": "ad_17", "fbclid": "fb.1"}, "referrer": "https://facebook.com/", "user_agent": "UA",
        "language": "pt-BR", "languages": ["pt-BR", "pt"], "screen": "390x844@3", "viewport": "390x700", "timezone": "America/Sao_Paulo",
        "page_url": "https://x/pesquisa/?utm_content=ad_17", "platform": "iPhone", "touch": True, "cookies_enabled": True,
        "color_depth": 24, "connection": "4g", "device_memory": 4, "hardware_concurrency": 6, "opened_at": "2026-10-09T10:00:00Z",
        "client_hints": {"mobile": "true"}}


def doc(sid):
    return webapp.CLIENT.collection(webapp.firebase.COLLECTION).document(sid).get().to_dict()


def qualified(http, system=3, urnas=4):
    """A new session through screening and the baseline questions."""
    sid = http.post("api/session", json=META).json()["session_id"]
    for q in ("q1", "q2"):
        http.post(f"api/session/{sid}/screening", json={"question": q, "answer": "sim"})
    r = http.post(f"api/session/{sid}/rating", json={"system": system, "urnas": urnas}).json()
    return sid, r


def test_new_session_shows_intro_and_q1_and_records_visitor(http):
    st = http.post("api/session", json=META, headers={"accept-language": "pt-BR", "sec-ch-ua-platform": '"iOS"'}).json()
    assert not st["resumed"]
    intro = st["intro"]
    assert intro["messages"] == [PT["intro"]]
    assert intro["screening"]["question"] == "q1" and [o["label"] for o in intro["screening"]["options"]] == ["Sim", "Não"]
    assert intro["rating"] is None
    d = doc(st["session_id"])
    web = d["first_message_raw"]["web"]
    assert web["languages"] == ["pt-BR", "pt"] and web["viewport"] == "390x700" and web["connection"] == "4g"
    assert web["headers"]["sec-ch-ua-platform"] == '"iOS"' and web["accept_language"] == "pt-BR"
    assert d["first_message_raw"]["referral"]["source_id"] == "ad_17" and d["first_message_raw"]["referral"]["ctwa_clid"] == "fb.1"
    assert d["page_loads"] == 1 and len(d["visits"]) == 1 and d["visits"][0]["platform"] == "iPhone"
    assert d["prompt_variant"] == ""   # no arm until the baseline filter is passed


def test_screened_out_visitor_is_kept_and_blocked(http):
    sid = http.post("api/session", json=META).json()["session_id"]
    r = http.post(f"api/session/{sid}/screening", json={"question": "q1", "answer": "nao"}).json()
    assert r["screened_out"] and r["messages"] == [PT["screening_closing"]]
    r = http.post(f"api/session/{sid}/message", json={"text": "oi"}).json()
    assert r["screened_out"] and r["messages"] == [PT["screening_closing"]]
    assert http.post(f"api/session/{sid}/rating", json={"system": 3, "urnas": 3}).status_code == 409
    st = http.post("api/session", json={**META, "session_id": sid}).json()
    assert st["resumed"] and st["screened_out"] and st["closing"] and st["screened_out_reason"] == "eligibility"
    d = doc(sid)
    assert d["page_loads"] == 2 and d["screening"]["age_18"] == "nao" and d["screening"]["passed"] is False and d["screened_out_at"]


def test_qualified_visitor_gets_the_two_questions_then_chat(http):
    sid = http.post("api/session", json=META).json()["session_id"]
    r = http.post(f"api/session/{sid}/message", json={"text": "oi"}).json()
    assert r["screening"]["question"] == "q1" and r["messages"] == []
    assert http.post(f"api/session/{sid}/screening", json={"question": "q2", "answer": "sim"}).status_code == 409
    r = http.post(f"api/session/{sid}/screening", json={"question": "q1", "answer": "sim"}).json()
    assert r["screening"]["question"] == "q2" and [o["value"] for o in r["screening"]["options"]] == ["sim", "nao", "nao_sei"]
    r = http.post(f"api/session/{sid}/screening", json={"question": "q2", "answer": "sim"}).json()
    assert r["screening"] is None and r["rating"]["kind"] == "baseline"
    assert r["rating"]["prompt"] == "Antes de começar, responda duas perguntas rápidas."
    assert [q["key"] for q in r["rating"]["questions"]] == ["system", "urnas"]
    assert [o["value"] for o in r["rating"]["options"]] == [1, 2, 3, 4, 5, 6, 7]
    assert r["rating"]["options"][0]["label"] == "Não confio nada" and r["rating"]["options"][6]["label"] == "Confio totalmente"
    # resume mid-way: baseline pending, intro text available for replay
    st = http.post("api/session", json={**META, "session_id": sid}).json()
    assert st["pending_rating"]["kind"] == "baseline" and st["pending_screening"] is None and st["intro_text"]
    # out-of-range or missing answers are rejected
    assert http.post(f"api/session/{sid}/rating", json={"system": 0, "urnas": 4}).status_code == 422
    assert http.post(f"api/session/{sid}/rating", json={"urnas": 4}).status_code == 422
    taps = [{"q": "system", "value": 2, "action": "selected", "at": "2026-10-19T10:00:00Z"},
            {"q": "system", "value": 3, "action": "changed", "at": "2026-10-19T10:00:01Z"},
            {"q": "system", "value": 3, "action": "confirmed", "at": "2026-10-19T10:00:02Z"}]
    r = http.post(f"api/session/{sid}/rating", json={"system": 3, "urnas": 5, "events": taps}).json()
    assert len(r["messages"]) == 1 and r["phase"] == "normal" and r["last_rating_turn"] == 0
    r = http.post(f"api/session/{sid}/message", json={"text": "acho que funciona"}).json()
    assert r["messages"] and r["phase"] == "normal" and r["user_turn_count"] == 1
    d = doc(sid)
    assert d["rating_pre"] == 5 and d["rating_pre_system"] == 3 and d["screening"]["passed"] is True
    assert d["feeling_array"][0]["events"] == taps
    assert d["prompt_variant"].split("_prompt_")[1] in prompt_service.VARIANTS


def test_high_trust_answer_ends_the_session(http):
    sid, r = qualified(http, system=2, urnas=7)
    assert r["screened_out"] and r["messages"] == [PT["screening_closing"]] and r["phase"] == "screened_out"
    st = http.post("api/session", json={**META, "session_id": sid}).json()
    assert st["screened_out"] and st["screened_out_reason"] == "high_trust" and st["closing"]
    d = doc(sid)
    assert d["rating_pre"] == 7 and d["rating_pre_system"] == 2 and d["prompt_variant"] == ""
    assert http.post(f"api/session/{sid}/message", json={"text": "oi"}).json()["screened_out"]


def test_ui_text_has_questions_options_and_phase2_texts(http):
    t = http.get("api/text").json()
    assert t["title"] == "Pesquisa acadêmica" and "urnas" not in t["title"].lower()
    assert t["rating_min"] == 1 and t["rating_max"] == 7
    assert len(t["rating_options"]) == 7 and t["rating_options"][3] == {"value": 4, "label": "Confio mais ou menos"}
    assert [q["key"] for q in t["rating_questions"]] == ["system", "urnas"]
    assert t["end_button"] == "Encerrar conversa" and t["exit_answer"] == "Responder" and t["exit_skip"] == "Pular e encerrar"
    assert t["exit_prompt"] == "Antes de sair, você pode responder duas perguntas rápidas? É opcional."
    assert t["inactivity_minutes"] == 15
    assert "Pesquisa acadêmica" in http.get("/").text and "🗳️" not in http.get("/").text
    h = http.get("health").json()
    assert h["rating_scale"] == [1, 7] and h["debrief_after_turns"] == 24 and h["continue_after_debrief"] is False


def test_end_with_exit_rating(http):
    sid, _ = qualified(http)
    http.post(f"api/session/{sid}/message", json={"text": "uma mensagem"})
    r = http.post(f"api/session/{sid}/end", json={"choice": "rated", "system": 1, "urnas": 2,
                                                  "events": [{"q": "urnas", "value": 2, "action": "confirmed", "at": "t"}]}).json()
    assert r["ended"] and r["phase"] == "ended" and r["messages"] == [PT["debrief"]]
    d = doc(sid)
    assert d["rating_exit"] == 2 and d["rating_exit_system"] == 1 and d["exit"]["choice"] == "rated" and d["exit"]["user_turns"] == 1
    assert d["ended_reason"] == "button" and d["feeling_array"][-1]["slot"] == "exit"
    # afterwards: ended, no model call; resume shows the debrief
    r = http.post(f"api/session/{sid}/message", json={"text": "oi"}).json()
    assert r["ended"] and r["messages"] == [PT["conversation_ended"]]
    st = http.post("api/session", json={**META, "session_id": sid}).json()
    assert st["ended"] and st["debrief"] == PT["debrief"] and st["ended_reason"] == "button"
    # 'rated' without answers is a client error
    sid2, _ = qualified(http)
    assert http.post(f"api/session/{sid2}/end", json={"choice": "rated"}).status_code == 422
    assert http.post(f"api/session/{sid2}/end", json={"choice": "nope"}).status_code == 422


def test_end_skipped_after_rating_and_inactivity(http):
    for choice, reason in (("skipped", "button"), ("after_rating", "button"), ("inactivity", "inactivity")):
        sid, _ = qualified(http)
        r = http.post(f"api/session/{sid}/end", json={"choice": choice}).json()
        assert r["ended"] and r["messages"] == [PT["debrief"]]
        d = doc(sid)
        assert d["ended_reason"] == reason and d["rating_exit"] is None
        assert (d["exit"].get("choice") == choice) if choice != "inactivity" else d["exit"] == {}


def test_ratings_every_six_messages_and_close_after_24(http):
    sid, _ = qualified(http)
    for n in range(1, 25):
        r = http.post(f"api/session/{sid}/message", json={"text": f"mensagem {n}"}).json()
        if n % 6:
            assert r["rating"] is None and r["phase"] == "normal", n
            continue
        assert r["rating"]["kind"] == "check_in" and r["rating"]["prompt"] == "Antes de continuar, responda mais duas perguntas rápidas."
        assert http.post(f"api/session/{sid}/message", json={"text": "x"}).json()["rating"]["kind"] == "check_in"   # blocked until rated
        r = http.post(f"api/session/{sid}/rating", json={"system": 4, "urnas": 4}).json()
        assert r["last_rating_turn"] == n
        if n < 24:
            assert r["phase"] == "normal" and not r["ended"] and r["messages"]     # the held reply arrives after the rating
        else:
            assert r["ended"] and r["phase"] == "ended" and r["messages"][-1] == PT["debrief"]
    d = doc(sid)
    assert d["ended_reason"] == "limit" and d["user_turn_count"] == 24 and len(d["feeling_array"]) == 5
    assert [x["slot"] for x in d["feeling_array"]] == ["pre", "post", None, None, None]
    assert d["rating_post"] == 4


# ---------------------------------------------------------------------------
# Meta Pixel (Facebook ad attribution)
# ---------------------------------------------------------------------------
def test_pixel_base_code_is_injected_only_when_configured(http, monkeypatch):
    monkeypatch.setattr(webapp, "META_PIXEL_ID", "")
    page = http.get("/").text
    assert "fbq('init'" not in page and "fbevents.js" not in page and "<!--META_PIXEL-->" not in page
    assert http.get("/health").json()["meta_pixel"] is False

    monkeypatch.setattr(webapp, "META_PIXEL_ID", "1276196112839237")
    page = http.get("/").text
    head = page.split("</head>")[0]
    assert "fbq('init', '1276196112839237')" in head and "fbq('track', 'PageView')" in head
    assert "connect.facebook.net/en_US/fbevents.js" in head
    assert 'src="https://www.facebook.com/tr?id=1276196112839237&ev=PageView&noscript=1"' in head
    assert page.count("Meta Pixel Code") == 2   # start + end markers, exactly one block
    assert http.get("/health").json()["meta_pixel"] is True
    assert 'trackOnce("ConversaIniciada")' in page and 'trackOnce("PesquisaConcluida")' in page
    assert "criativo: creative" in page


def test_creative_and_completed_fields_drive_the_custom_events(http):
    st = http.post("api/session", json=META).json()
    sid = st["session_id"]
    assert st["creative"] == "ad_17" and st["completed"] is False
    for q in ("q1", "q2"):
        http.post(f"api/session/{sid}/screening", json={"question": q, "answer": "sim"})
    r = http.post(f"api/session/{sid}/rating", json={"system": 2, "urnas": 2}).json()
    assert r["completed"] is False                      # pre rating alone is not a completion
    st = http.post("api/session", json={**META, "query": {}, "session_id": sid}).json()
    assert st["resumed"] and st["creative"] == "ad_17" and st["completed"] is False
    for i in range(6):
        r = http.post(f"api/session/{sid}/message", json={"text": f"mensagem {i}"}).json()
        assert r["completed"] is False
    assert r["rating"]["kind"] == "check_in"
    r = http.post(f"api/session/{sid}/rating", json={"system": 3, "urnas": 3}).json()
    assert r["completed"] is True                       # post rating recorded -> PesquisaConcluida
    d = doc(sid)
    assert d["rating_pre"] == 2 and d["rating_post"] == 3
    assert http.post("api/session", json={**META, "session_id": sid}).json()["completed"] is True


def test_session_without_ad_parameters_has_no_creative(http):
    st = http.post("api/session", json={**META, "query": {}}).json()
    assert st["creative"] is None


# ---------------------------------------------------------------------------
# /health probes Firestore so a dead store is visible to monitoring
# ---------------------------------------------------------------------------
def test_health_reports_firestore_and_fails_when_it_is_down(http, monkeypatch):
    r = http.get("health")
    assert r.status_code == 200 and r.json()["status"] == "healthy" and r.json()["firestore"] == "ok"

    class Broken:
        def collection(self, name):
            raise RuntimeError("429 Quota exceeded")

    monkeypatch.setattr(webapp, "CLIENT", Broken())
    r = http.get("health")
    assert r.status_code == 503
    assert r.json()["status"] == "unhealthy" and r.json()["firestore"] == "RuntimeError: 429 Quota exceeded"
