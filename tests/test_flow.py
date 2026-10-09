"""Conversation-service flow: screening, baseline, control stages, debrief."""
import asyncio

import pytest

from config import settings
from database import firebase
from services import conversation_service as cs
from services import prompt_service, trust_service


def send(client, sid, text, kind="text", raw=None, contacts=None):
    return asyncio.run(cs.handle_incoming_message(client, sid, text, kind, raw_message=raw, contacts=contacts or []))


def doc(client, sid):
    return client.collection(firebase.COLLECTION).document(sid).get().to_dict()


AD_RAW = {"id": "web.x.1", "timestamp": "1700000000", "type": "text", "channel": "web", "text": {"body": "[abrir página]"},
          "referral": {"source_type": "web_ad", "source_id": "ad_17", "ctwa_clid": "fb123", "params": {"utm_content": "ad_17"}},
          "web": {"query": {"utm_content": "ad_17"}, "user_agent": "UA", "ip_hash": "abc"}}


def open_page(client, sid="web_1"):
    return send(client, sid, "[abrir página]", raw=AD_RAW, contacts=[{"wa_id": sid, "channel": "web"}])


def test_first_contact_creates_document_with_metadata_and_asks_q1(client):
    r = open_page(client)
    d = doc(client, "web_1")
    assert d["conversation_phase"] == "awaiting_screening" and d["intro_sent"]
    assert d["first_message_raw"]["referral"]["source_id"] == "ad_17"
    assert d["referrals"][0]["referral"]["ctwa_clid"] == "fb123"
    assert r.text_messages == [trust_service.TRUST_PROMPTS["PT"]["intro"]]
    assert r.send_screening == "q1" and not r.send_trust_flow


def test_fail_q1_records_answer_and_screens_out(client):
    open_page(client)
    r = send(client, "web_1", "screening_q1_nao", "interactive")
    d = doc(client, "web_1")
    assert r.text_messages == [trust_service.TRUST_PROMPTS["PT"]["screening_closing"]]
    assert d["conversation_phase"] == "screened_out" and d["screened_out_at"] is not None
    assert d["screening"]["age_18"] == "nao" and d["screening"]["passed"] is False
    assert d["screening"]["eligible_voter"] is None if "eligible_voter" in d["screening"] else True
    # the referral metadata survives for a screened-out visitor
    assert d["first_message_raw"]["referral"]["source_id"] == "ad_17"
    # anything further: closing again, never the study
    r2 = send(client, "web_1", "oi")
    assert r2.text_messages == [trust_service.TRUST_PROMPTS["PT"]["screening_closing"]] and not r2.send_trust_flow


@pytest.mark.parametrize("answer", ["nao", "nao_sei"])
def test_fail_q2_screens_out(client, answer):
    open_page(client)
    r1 = send(client, "web_1", "screening_q1_sim", "interactive")
    assert r1.send_screening == "q2" and r1.text_messages == []
    r2 = send(client, "web_1", f"screening_q2_{answer}", "interactive")
    d = doc(client, "web_1")
    assert d["conversation_phase"] == "screened_out"
    assert d["screening"]["age_18"] == "sim" and d["screening"]["eligible_voter"] == answer
    assert r2.text_messages == [trust_service.TRUST_PROMPTS["PT"]["screening_closing"]]


def test_pass_both_leads_to_baseline_then_conversation(client, canned_llm):
    open_page(client)
    send(client, "web_1", "screening_q1_sim", "interactive")
    r = send(client, "web_1", "screening_q2_sim", "interactive")
    d = doc(client, "web_1")
    assert d["conversation_phase"] == "awaiting_initial_rating" and d["screening"]["passed"] is True
    assert r.send_trust_flow and r.trust_flow_prompt_key == "baseline" and r.send_screening is None
    # text before rating -> invalid + baseline again
    r = send(client, "web_1", "olá")
    assert r.trust_flow_prompt_key == "baseline" and r.send_trust_flow
    # rating 0-100
    r = send(client, "web_1", "rating_42", "interactive")
    d = doc(client, "web_1")
    assert d["rating_pre"] == 42 and d["conversation_phase"] == "normal"
    assert len(r.text_messages) == 1
    # first real message reaches the model with the belief level substituted (non-control) or no placeholder
    r = send(client, "web_1", "acho que sim")
    assert r.text_messages == ["resposta do modelo"]
    sp = canned_llm[-1]
    assert prompt_service.BELIEF_PLACEHOLDER not in sp
    variant = prompt_service.base_variant(d["prompt_variant"])
    if variant != prompt_service.CONTROL_VARIANT:
        assert "42" in sp and "0% (Nenhuma confiança) a 100% (Confiança total)" in sp


def test_text_answers_accepted_on_whatsapp_style_channel(client):
    open_page(client)
    assert send(client, "web_1", "SIM").send_screening == "q2"
    r = send(client, "web_1", "não sei")
    assert doc(client, "web_1")["conversation_phase"] == "screened_out"
    assert r.text_messages == [trust_service.TRUST_PROMPTS["PT"]["screening_closing"]]


def test_unparseable_text_reasks_same_question(client):
    open_page(client)
    r = send(client, "web_1", "talvez")
    assert r.send_screening == "q1"
    assert r.text_messages == [trust_service.TRUST_PROMPTS["PT"]["screening_invalid_q1"]]
    assert doc(client, "web_1")["screening"] == {}


def test_screening_disabled_goes_straight_to_baseline(client, monkeypatch):
    monkeypatch.setattr(settings, "SCREENING_ENABLED", False)
    r = open_page(client, "web_2")
    d = doc(client, "web_2")
    assert d["conversation_phase"] == "awaiting_initial_rating"
    assert r.text_messages == [trust_service.TRUST_PROMPTS["PT"]["intro"]]
    assert r.send_trust_flow and r.trust_flow_prompt_key == "baseline" and r.send_screening is None


def test_legacy_document_in_awaiting_initial_rating_still_works(client):
    # a document written before screening existed
    client.collection(firebase.COLLECTION).document("old").set(
        {"last_message": "", "history": [], "language": "PT", "prompt_variant": "PT_prompt_B_motivational_learning",
         "conversation_phase": "awaiting_initial_rating", "intro_sent": True, "feeling_array": [], "user_turn_count": 0})
    r = send(client, "old", "rating_70", "interactive")
    assert doc(client, "old")["rating_pre"] == 70 and len(r.text_messages) == 1


def _qualify(client, sid, variant):
    open_page(client, sid)
    # force the condition so the test is deterministic
    client.collection(firebase.COLLECTION).document(sid).update({"prompt_variant": f"PT_prompt_{variant}"})
    send(client, sid, "screening_q1_sim", "interactive")
    send(client, sid, "screening_q2_sim", "interactive")
    return send(client, sid, "rating_30", "interactive")


def test_control_condition_two_stages_and_debrief(client, canned_llm):
    r = _qualify(client, "ctl", "A_control_condition")
    assert r.text_messages == [trust_service.TRUST_PROMPTS["PT"]["rating_received_control"]]
    assert "cachorro caramelo" in r.text_messages[0]
    # six dog turns under the stage-1 prompt
    for i in range(6):
        r = send(client, "ctl", f"msg {i}")
    assert "cachorro caramelo" in canned_llm[-1] and "urnas eletrônicas do Brasil. A primeira etapa" not in canned_llm[-1]
    assert r.send_trust_flow and r.trust_flow_prompt_key == "check_in"   # post rating at turn 6
    r = send(client, "ctl", "rating_55", "interactive")
    d = doc(client, "ctl")
    assert d["rating_post"] == 55
    assert r.text_messages[-1] == trust_service.TRUST_PROMPTS["PT"]["control_transition"]
    assert d["debriefed_at"] is None            # control is debriefed after its election turns
    # election turns under the stage-2 prompt
    for i in range(6):
        r = send(client, "ctl", f"eleições {i}")
    assert "A primeira etapa da conversa, sobre o cachorro caramelo, já terminou" in canned_llm[-1]
    assert r.send_trust_flow and r.trust_flow_prompt_key == "check_in"   # rating at turn 12
    r = send(client, "ctl", "rating_60", "interactive")
    d = doc(client, "ctl")
    assert d["debriefed_at"] is not None and d["conversation_phase"] == "normal"   # web: continues after debrief
    assert r.text_messages[-1] == trust_service.TRUST_PROMPTS["PT"]["debrief_open"]


def test_treatment_condition_debrief_after_six_turns(client, canned_llm):
    r = _qualify(client, "trt", "D_christmas_dinner")
    assert r.text_messages == [trust_service.TRUST_PROMPTS["PT"]["rating_received"]]
    for i in range(6):
        r = send(client, "trt", f"msg {i}")
    assert "30" in canned_llm[-1] and "Posso explicar como esse processo funciona?" in canned_llm[-1]
    assert r.send_trust_flow and r.trust_flow_prompt_key == "check_in"
    r = send(client, "trt", "rating_35", "interactive")
    d = doc(client, "trt")
    assert d["rating_pre"] == 30 and d["rating_post"] == 35 and d["debriefed_at"] is not None
    assert r.text_messages[-1] == trust_service.TRUST_PROMPTS["PT"]["debrief_open"]


def test_all_prompt_files_load_and_have_no_raw_placeholders(client):
    for lang in ("PT", "EN"):
        for v in prompt_service.VARIANTS + [prompt_service.CONTROL_STAGE2_VARIANT]:
            txt = prompt_service.get_prompt(lang, f"{lang}_prompt_{v}", user_belief_level=77)
            assert "**" not in txt, (lang, v)
            assert "Regras de Segurança" in txt or "Safety Rules" in txt
            if v.startswith("A"):
                assert "77" not in txt           # control prompts carry no belief level
            else:
                assert "77" in txt
