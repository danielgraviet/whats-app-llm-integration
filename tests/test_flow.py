"""Conversation-service flow, phase 2: screening, baseline questions, high-trust
filter, arm drawn after the filter, control stages, ratings every 6 messages,
end by limit / button / inactivity."""
import asyncio

import pytest

from config import settings
from database import firebase
from services import conversation_service as cs
from services import prompt_service, trust_service

PT = trust_service.TRUST_PROMPTS["PT"]


def send(client, sid, text, kind="text", raw=None, contacts=None, events=None):
    return asyncio.run(cs.handle_incoming_message(client, sid, text, kind, raw_message=raw, contacts=contacts or [],
                                                  rating_events=events))


def end(client, sid, choice, rating=None, events=None):
    return asyncio.run(cs.end_conversation(client, sid, choice, rating=rating, rating_events=events))


def doc(client, sid):
    return client.collection(firebase.COLLECTION).document(sid).get().to_dict()


AD_RAW = {"id": "web.x.1", "timestamp": "1700000000", "type": "text", "channel": "web", "text": {"body": "[abrir página]"},
          "referral": {"source_type": "web_ad", "source_id": "ad_17", "ctwa_clid": "fb123", "params": {"utm_content": "ad_17"}},
          "web": {"query": {"utm_content": "ad_17"}, "user_agent": "UA", "ip_hash": "abc"}}


def open_page(client, sid="web_1"):
    return send(client, sid, "[abrir página]", raw=AD_RAW, contacts=[{"wa_id": sid, "channel": "web"}])


def pass_screening(client, sid="web_1"):
    open_page(client, sid)
    send(client, sid, "screening_q1_sim", "interactive")
    return send(client, sid, "screening_q2_sim", "interactive")


def test_first_contact_creates_document_without_arm_and_asks_q1(client):
    r = open_page(client)
    d = doc(client, "web_1")
    assert d["conversation_phase"] == "awaiting_screening" and d["intro_sent"]
    assert d["prompt_variant"] == "" and d["variant_assigned_at"] is None     # drawn after the filter
    assert d["first_message_raw"]["referral"]["source_id"] == "ad_17"
    assert r.text_messages == [PT["intro"]]
    assert r.send_screening == "q1" and not r.send_trust_flow


def test_fail_q1_records_answer_and_screens_out_with_new_closing(client):
    open_page(client)
    r = send(client, "web_1", "screening_q1_nao", "interactive")
    d = doc(client, "web_1")
    assert r.text_messages == [PT["screening_closing"]]
    assert PT["screening_closing"].startswith("Obrigado pela sua resposta! Nesta etapa")
    assert d["conversation_phase"] == "screened_out" and d["screened_out_at"] is not None
    assert d["screened_out_reason"] == "eligibility" and d["screening"]["passed"] is False
    r2 = send(client, "web_1", "oi")
    assert r2.text_messages == [PT["screening_closing"]] and not r2.send_trust_flow


@pytest.mark.parametrize("answer", ["nao", "nao_sei"])
def test_fail_q2_screens_out(client, answer):
    open_page(client)
    assert send(client, "web_1", "screening_q1_sim", "interactive").send_screening == "q2"
    r2 = send(client, "web_1", f"screening_q2_{answer}", "interactive")
    assert doc(client, "web_1")["conversation_phase"] == "screened_out"
    assert r2.text_messages == [PT["screening_closing"]]


def test_baseline_questions_then_arm_then_conversation(client, canned_llm):
    r = pass_screening(client)
    d = doc(client, "web_1")
    assert d["conversation_phase"] == "awaiting_initial_rating" and d["screening"]["passed"] is True
    assert r.send_trust_flow and r.trust_flow_prompt_key == "baseline"
    assert PT["baseline"] == "Antes de começar, responda duas perguntas rápidas."
    # text before the questions are answered -> invalid + baseline again
    r = send(client, "web_1", "olá")
    assert r.trust_flow_prompt_key == "baseline" and r.send_trust_flow
    # both answers in one reply: system=3, urnas=5, with the tap log
    taps = [{"q": "system", "value": 3, "action": "selected", "at": "2026-10-19T10:00:00Z"}]
    r = send(client, "web_1", "rating_3_5", "interactive", events=taps)
    d = doc(client, "web_1")
    assert d["rating_pre"] == 5 and d["rating_pre_system"] == 3 and d["conversation_phase"] == "normal"
    assert d["feeling_array"][0]["score"] == 5 and d["feeling_array"][0]["score_system"] == 3
    assert d["feeling_array"][0]["slot"] == "pre" and d["feeling_array"][0]["events"] == taps
    # the arm is drawn now, from the phase-2 list
    assert prompt_service.base_variant(d["prompt_variant"]) in prompt_service.VARIANTS and d["variant_assigned_at"]
    assert len(r.text_messages) == 1
    # the model gets the urnas answer as the belief level
    r = send(client, "web_1", "acho que sim")
    assert r.text_messages == ["resposta do modelo"]
    sp = canned_llm[-1]
    assert prompt_service.BELIEF_PLACEHOLDER not in sp and "Their answer is 5." in sp


@pytest.mark.parametrize("system", [1, 7])
def test_high_trust_filter_ends_session_whatever_question_1_says(client, system):
    pass_screening(client)
    r = send(client, "web_1", f"rating_{system}_7", "interactive")
    d = doc(client, "web_1")
    assert r.text_messages == [PT["screening_closing"]] and not r.send_trust_flow
    assert d["conversation_phase"] == "screened_out" and d["screened_out_reason"] == "high_trust"
    assert d["screening"]["passed"] is True                  # eligibility was fine
    assert d["rating_pre"] == 7 and d["rating_pre_system"] == system   # the answers are kept
    assert d["prompt_variant"] == ""                           # never randomised
    assert send(client, "web_1", "oi").text_messages == [PT["screening_closing"]]


def test_urnas_6_passes_the_filter(client):
    pass_screening(client)
    send(client, "web_1", "rating_7_6", "interactive")
    assert doc(client, "web_1")["conversation_phase"] == "normal"


def test_rating_parsers():
    assert trust_service.parse_interactive_rating("rating_2_6") == {"system": 2, "urnas": 6}
    assert trust_service.parse_interactive_rating("rating_6") == {"system": None, "urnas": 6}
    assert trust_service.parse_interactive_rating("rating_0_6") is None
    assert trust_service.parse_interactive_rating("rating_2_8") is None
    assert trust_service.parse_interactive_rating("rating_x_1") is None
    assert trust_service.parse_text_rating("4, 6") == {"system": 4, "urnas": 6}
    assert trust_service.parse_text_rating("oi") is None
    assert [o["label"] for o in trust_service.rating_options("PT")] == [
        "Não confio nada", "Confio muito pouco", "Confio pouco", "Confio mais ou menos",
        "Confio muito", "Confio quase totalmente", "Confio totalmente"]
    assert [q["key"] for q in trust_service.rating_questions("PT")] == ["system", "urnas"]
    assert trust_service.rating_questions("PT")[0]["text"].startswith("O quanto você confia no sistema eleitoral")


def test_text_answers_accepted_on_whatsapp_style_channel(client):
    open_page(client)
    assert send(client, "web_1", "SIM").send_screening == "q2"
    r = send(client, "web_1", "não sei")
    assert doc(client, "web_1")["conversation_phase"] == "screened_out"
    assert r.text_messages == [PT["screening_closing"]]


def test_unparseable_text_reasks_same_question(client):
    open_page(client)
    r = send(client, "web_1", "talvez")
    assert r.send_screening == "q1"
    assert r.text_messages == [PT["screening_invalid_q1"]]
    assert doc(client, "web_1")["screening"] == {}


def test_screening_disabled_goes_straight_to_baseline(client, monkeypatch):
    monkeypatch.setattr(settings, "SCREENING_ENABLED", False)
    r = open_page(client, "web_2")
    assert doc(client, "web_2")["conversation_phase"] == "awaiting_initial_rating"
    assert r.text_messages == [PT["intro"]]
    assert r.send_trust_flow and r.trust_flow_prompt_key == "baseline" and r.send_screening is None


def _qualify(client, sid, variant, pre="2_3"):
    """Screening, then force the arm before the baseline answers so the test is
    deterministic (the service only draws an arm when none is set)."""
    pass_screening(client, sid)
    client.collection(firebase.COLLECTION).document(sid).update({"prompt_variant": f"PT_prompt_{variant}"})
    return send(client, sid, f"rating_{pre}", "interactive")


def _talk(client, sid, n, prefix="msg"):
    r = None
    for i in range(n):
        r = send(client, sid, f"{prefix} {i}")
    return r


def test_control_condition_dog_then_urnas_then_ends_at_24(client, canned_llm):
    r = _qualify(client, "ctl", prompt_service.CONTROL_VARIANT)
    assert r.text_messages == [PT["rating_received_control"]]
    assert r.text_messages[0].startswith("Antes de conversar sobre as eleições brasileiras, vou fazer algumas perguntas rápidas")
    # six dog turns under the stage-1 prompt
    r = _talk(client, "ctl", 6)
    assert "You are now in Phase 1" in canned_llm[-1] and "cachorro caramelo" in canned_llm[-1]
    assert r.send_trust_flow and r.trust_flow_prompt_key == "check_in"       # questions after message 6
    assert PT["check_in"] == "Antes de continuar, responda mais duas perguntas rápidas."
    r = send(client, "ctl", "rating_4_4", "interactive")
    d = doc(client, "ctl")
    assert d["rating_post"] == 4 and d["rating_post_system"] == 4 and d["feeling_array"][1]["slot"] == "post"
    assert r.text_messages[-1] == PT["control_transition"] and d["debriefed_at"] is None
    assert d["conversation_phase"] == "normal"
    # urnas turns under the stage-2 prompt, ratings at 12 and 18, no debrief yet
    for turn in (12, 18):
        r = _talk(client, "ctl", 6, "urnas")
        assert "You are now in Phase 2" in canned_llm[-1]
        assert r.send_trust_flow and r.trust_flow_prompt_key == "check_in"
        r = send(client, "ctl", "rating_4_5", "interactive")
        d = doc(client, "ctl")
        assert d["user_turn_count"] == turn and d["debriefed_at"] is None and d["conversation_phase"] == "normal"
        assert d["feeling_array"][-1]["slot"] is None and d["feeling_array"][-1]["message_index"] == turn
    # the rating at 24 is followed by the debrief, and the chat closes
    r = _talk(client, "ctl", 6, "urnas")
    assert r.send_trust_flow and r.trust_flow_prompt_key == "check_in"
    r = send(client, "ctl", "rating_5_5", "interactive")
    d = doc(client, "ctl")
    assert d["debriefed_at"] is not None and d["conversation_phase"] == "ended" and d["ended_reason"] == "limit"
    assert r.text_messages[-1] == PT["debrief"] and len(d["feeling_array"]) == 5
    assert send(client, "ctl", "mais?").text_messages == [PT["conversation_ended"]]


def test_treatment_arms_use_their_prompt_and_debrief_only_at_24(client, canned_llm):
    for sid, variant in (("b", "B_motivational_v6"), ("c", "C_refutational_v6")):
        r = _qualify(client, sid, variant, pre="2_3")
        assert r.text_messages == [PT["rating_received"]]
        r = _talk(client, sid, 6)
        sp = canned_llm[-1]
        assert "Their answer is 3." in sp and "### Verified Facts" in sp
        assert ("Motivational Interviewing" in sp) == (variant.startswith("B"))
        assert ("Empathetic Refutational Interviewing" in sp) == (variant.startswith("C"))
        assert r.send_trust_flow and r.trust_flow_prompt_key == "check_in"
        r = send(client, sid, "rating_3_4", "interactive")
        d = doc(client, sid)
        assert d["rating_pre"] == 3 and d["rating_post"] == 4 and d["debriefed_at"] is None
        assert r.text_messages == [] or r.text_messages[-1] != PT["debrief"]


def test_button_with_exit_rating(client, canned_llm):
    _qualify(client, "ex", "B_motivational_v6")
    _talk(client, "ex", 2)
    taps = [{"q": "urnas", "value": 2, "action": "confirmed", "at": "t"}]
    r = end(client, "ex", "rated", rating={"system": 1, "urnas": 2}, events=taps)
    d = doc(client, "ex")
    assert r.text_messages == [PT["debrief"]]
    assert d["conversation_phase"] == "ended" and d["ended_reason"] == "button" and d["debriefed_at"]
    assert d["rating_exit"] == 2 and d["rating_exit_system"] == 1
    assert d["feeling_array"][-1]["slot"] == "exit" and d["feeling_array"][-1]["message_index"] == 2
    assert d["feeling_array"][-1]["events"] == taps
    assert d["exit"]["choice"] == "rated" and d["exit"]["user_turns"] == 2 and d["exit"]["at"]
    assert d["rating_post"] is None                         # an exit rating never fills the post slot
    # idempotent
    assert end(client, "ex", "skipped").text_messages == [PT["debrief"]]
    assert doc(client, "ex")["exit"]["choice"] == "rated"


def test_button_skipped_and_after_rating(client, canned_llm):
    _qualify(client, "sk", "C_refutational_v6")
    _talk(client, "sk", 1)
    end(client, "sk", "skipped")
    d = doc(client, "sk")
    assert d["ended_reason"] == "button" and d["exit"]["choice"] == "skipped" and d["rating_exit"] is None
    _qualify(client, "ar", "C_refutational_v6")
    end(client, "ar", "after_rating")
    d = doc(client, "ar")
    assert d["ended_reason"] == "button" and d["exit"]["choice"] == "after_rating" and d["exit"]["user_turns"] == 0


def test_inactivity_ends_without_exit_record(client, canned_llm):
    _qualify(client, "idle", "B_motivational_v6")
    _talk(client, "idle", 3)
    r = end(client, "idle", "inactivity")
    d = doc(client, "idle")
    assert r.text_messages == [PT["debrief"]]
    assert d["conversation_phase"] == "ended" and d["ended_reason"] == "inactivity" and d["exit"] == {}


def test_end_before_the_conversation_started_does_nothing(client):
    open_page(client, "early")
    r = end(client, "early", "skipped")
    d = doc(client, "early")
    assert d["conversation_phase"] == "awaiting_screening" and d["debriefed_at"] is None
    assert r.text_messages == [PT["conversation_ended"]]


def test_all_prompt_files_load_and_have_no_raw_placeholders(client):
    for lang in ("PT", "EN"):
        for v in prompt_service.VARIANTS + [prompt_service.CONTROL_STAGE2_VARIANT]:
            txt = prompt_service.get_prompt(lang, f"{lang}_prompt_{v}", user_belief_level=6)
            assert "**" not in txt, (lang, v)
            assert "### Safety Rules" in txt and "Their answer is 6." in txt
            assert "Flávio Bolsonaro" in txt and "October 25, 2026" in txt     # current-context section present
    assert set(prompt_service.VARIANTS) == {"A_control_v6", "B_motivational_v6", "C_refutational_v6"}
