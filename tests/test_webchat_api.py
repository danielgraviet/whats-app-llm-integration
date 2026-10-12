"""Web chat HTTP API in demo mode (in-memory store, canned replies)."""
import os
import sys

import pytest

os.environ["WEBCHAT_DEMO"] = "1"
sys.argv = [sys.argv[0]]   # app.py inspects argv for --demo

from fastapi.testclient import TestClient  # noqa: E402

from webchat import app as webapp  # noqa: E402


@pytest.fixture(scope="module")
def http():
    webapp.configure()
    return TestClient(webapp.app)


META = {"query": {"utm_content": "ad_17", "fbclid": "fb.1"}, "referrer": "https://facebook.com/", "user_agent": "UA",
        "language": "pt-BR", "languages": ["pt-BR", "pt"], "screen": "390x844@3", "viewport": "390x700", "timezone": "America/Sao_Paulo",
        "page_url": "https://x/pesquisa/?utm_content=ad_17", "platform": "iPhone", "touch": True, "cookies_enabled": True,
        "color_depth": 24, "connection": "4g", "device_memory": 4, "hardware_concurrency": 6, "opened_at": "2026-10-09T10:00:00Z",
        "client_hints": {"mobile": "true"}}


def test_new_session_shows_intro_and_q1_and_records_visitor(http):
    st = http.post("api/session", json=META, headers={"accept-language": "pt-BR", "sec-ch-ua-platform": '"iOS"'}).json()
    assert not st["resumed"]
    intro = st["intro"]
    assert intro["messages"] == [webapp.trust_service.TRUST_PROMPTS["PT"]["intro"]]
    assert intro["screening"]["question"] == "q1" and [o["label"] for o in intro["screening"]["options"]] == ["Sim", "Não"]
    assert intro["rating"] is None
    d = webapp.CLIENT.collection(webapp.firebase.COLLECTION).document(st["session_id"]).get().to_dict()
    web = d["first_message_raw"]["web"]
    assert web["languages"] == ["pt-BR", "pt"] and web["viewport"] == "390x700" and web["connection"] == "4g"
    assert web["headers"]["sec-ch-ua-platform"] == '"iOS"' and web["accept_language"] == "pt-BR"
    assert d["first_message_raw"]["referral"]["source_id"] == "ad_17" and d["first_message_raw"]["referral"]["ctwa_clid"] == "fb.1"
    assert d["page_loads"] == 1 and len(d["visits"]) == 1 and d["visits"][0]["platform"] == "iPhone"


def test_screened_out_visitor_is_kept_and_blocked(http):
    sid = http.post("api/session", json=META).json()["session_id"]
    r = http.post(f"api/session/{sid}/screening", json={"question": "q1", "answer": "nao"}).json()
    assert r["screened_out"] and r["messages"] == [webapp.trust_service.TRUST_PROMPTS["PT"]["screening_closing"]]
    # typing afterwards: closing again, no model call
    r = http.post(f"api/session/{sid}/message", json={"text": "oi"}).json()
    assert r["screened_out"] and r["messages"] == [webapp.trust_service.TRUST_PROMPTS["PT"]["screening_closing"]]
    # a rating is refused
    assert http.post(f"api/session/{sid}/rating", json={"score": 50}).status_code == 409
    # resume shows closing, counts the visit
    st = http.post("api/session", json={**META, "session_id": sid}).json()
    assert st["resumed"] and st["screened_out"] and st["closing"]
    d = webapp.CLIENT.collection(webapp.firebase.COLLECTION).document(sid).get().to_dict()
    assert d["page_loads"] == 2 and d["screening"] == {k: v for k, v in d["screening"].items()}  # present
    assert d["screening"]["age_18"] == "nao" and d["screening"]["passed"] is False and d["screened_out_at"]


def test_qualified_visitor_gets_baseline_then_chat(http):
    sid = http.post("api/session", json=META).json()["session_id"]
    # text while q1 is open re-offers the question
    r = http.post(f"api/session/{sid}/message", json={"text": "oi"}).json()
    assert r["screening"]["question"] == "q1" and r["messages"] == []
    # wrong question id is rejected
    assert http.post(f"api/session/{sid}/screening", json={"question": "q2", "answer": "sim"}).status_code == 409
    r = http.post(f"api/session/{sid}/screening", json={"question": "q1", "answer": "sim"}).json()
    assert r["screening"]["question"] == "q2" and [o["value"] for o in r["screening"]["options"]] == ["sim", "nao", "nao_sei"]
    r = http.post(f"api/session/{sid}/screening", json={"question": "q2", "answer": "sim"}).json()
    assert r["screening"] is None and r["rating"]["kind"] == "baseline"
    assert "0% a 100%" in r["rating"]["prompt"] and "Não confio nem um pouco" in r["rating"]["prompt"]
    # resume mid-way: baseline pending, intro text available for replay
    st = http.post("api/session", json={**META, "session_id": sid}).json()
    assert st["pending_rating"]["kind"] == "baseline" and st["pending_screening"] is None and st["intro_text"]
    r = http.post(f"api/session/{sid}/rating", json={"score": 88}).json()
    assert len(r["messages"]) == 1 and r["phase"] == "normal"
    r = http.post(f"api/session/{sid}/message", json={"text": "acho que funciona"}).json()
    assert r["messages"] and r["phase"] == "normal"
    d = webapp.CLIENT.collection(webapp.firebase.COLLECTION).document(sid).get().to_dict()
    assert d["rating_pre"] == 88 and d["screening"]["passed"] is True


def test_ui_text_has_percent_scale(http):
    t = http.get("api/text").json()
    assert t["rating_min"] == 0 and t["rating_max"] == 100 and t["rate_unit"] == "%"
    assert t["rate_low"] == "Não confio nem um pouco" and t["rate_high"] == "Confio totalmente"
    assert http.get("health").json()["screening_enabled"] is True


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
    # the page script fires the two custom events with the exact (case-sensitive) names from the brief
    assert 'trackOnce("ConversaIniciada")' in page and 'trackOnce("PesquisaConcluida")' in page
    assert "criativo: creative" in page


def test_creative_and_completed_fields_drive_the_custom_events(http):
    st = http.post("api/session", json=META).json()
    sid = st["session_id"]
    assert st["creative"] == "ad_17" and st["completed"] is False
    for q in ("q1", "q2"):
        http.post(f"api/session/{sid}/screening", json={"question": q, "answer": "sim"})
    r = http.post(f"api/session/{sid}/rating", json={"score": 40}).json()
    assert r["completed"] is False                      # pre rating alone is not a completion
    # resumed without utm_content in the URL: the creative is remembered from the first visit
    st = http.post("api/session", json={**META, "query": {}, "session_id": sid}).json()
    assert st["resumed"] and st["creative"] == "ad_17" and st["completed"] is False
    for i in range(6):
        r = http.post(f"api/session/{sid}/message", json={"text": f"mensagem {i}"}).json()
        assert r["completed"] is False
    assert r["rating"]["kind"] == "check_in"
    r = http.post(f"api/session/{sid}/rating", json={"score": 60}).json()
    assert r["completed"] is True                       # post rating recorded -> PesquisaConcluida
    d = webapp.CLIENT.collection(webapp.firebase.COLLECTION).document(sid).get().to_dict()
    assert d["rating_pre"] == 40 and d["rating_post"] == 60
    assert http.post("api/session", json={**META, "session_id": sid}).json()["completed"] is True


def test_session_without_ad_parameters_has_no_creative(http):
    st = http.post("api/session", json={**META, "query": {}}).json()
    assert st["creative"] is None
