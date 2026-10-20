import dataclasses

from config import settings
from database import firebase
from integrations import openai_client
from services import prompt_service, trust_service

_N_HISTORY_TURNS = 5


def _is_control(conversation) -> bool:
    return prompt_service.base_variant(conversation.prompt_variant) == prompt_service.CONTROL_VARIANT


def _control_stage2(conversation) -> bool:
    """Control participants move to the elections prompt once their second rating is in."""
    return _is_control(conversation) and conversation.rating_post is not None


def _rating_slot(conversation) -> str | None:
    """Which analysis slot the rating about to be saved fills: "pre" for the
    baseline, "post" for the first check-in (after the 6th message), None later.
    An exit rating is saved with its own slot by end_conversation()."""
    slots = {r.slot for r in conversation.feeling_array if r.slot}
    n = len(conversation.feeling_array)
    if n == 0 and "pre" not in slots:
        return "pre"
    if "post" not in slots and n == 1:
        return "post"
    return None


def last_rating_turn(conversation) -> int | None:
    """message_index of the most recent rating, or None if none yet."""
    if not conversation.feeling_array:
        return None
    return max(r.message_index for r in conversation.feeling_array)


def _initial_belief_level(conversation) -> int | None:
    """The participant's first trust rating (collected before the conversation).

    Prefers the rating recorded at message_index 0; falls back to the earliest
    rating in the array; None if no rating has been collected yet.
    """
    if conversation.rating_pre is not None:
        return conversation.rating_pre
    ratings = conversation.feeling_array
    if not ratings:
        return None
    for r in ratings:
        if r.message_index == 0:
            return r.score
    return ratings[0].score


@dataclasses.dataclass
class BotResponse:
    text_messages: list[str] = dataclasses.field(default_factory=list)
    send_trust_flow: bool = False
    trust_flow_language: str = "EN"
    trust_flow_prompt_key: str = "baseline"
    # Eligibility screening question to show next ("q1" / "q2"), rendered as
    # buttons on the web and as a text question with options on WhatsApp.
    send_screening: str | None = None


def _initial_phase() -> str:
    return "awaiting_screening" if settings.SCREENING_ENABLED else "awaiting_initial_rating"


async def handle_incoming_message(
    client,
    phone_number: str,
    message_text: str,
    msg_type: str,
    raw_message: dict | None = None,
    contacts: list | None = None,
    allow_dev_commands: bool = True,
    rating_events: list | None = None,
) -> BotResponse:
    """Main entry point. Routes to the correct handler based on conversation phase.

    allow_dev_commands=False (web deployment) treats "/info", "/reset" and
    "/lang" as ordinary participant text instead of developer commands.

    rating_events: the participant's button taps (with timestamps) when the
    message is a rating reply; stored with the rating.

    raw_message / contacts are the untouched webhook objects from Meta. They are
    stored on the conversation for research metadata (see firebase.record_metadata).
    Condition assignment is random and independent of any ad referral by design.
    """

    # 1. Get or create conversation. The study arm is drawn later, once the
    #    participant has passed the baseline high-trust filter.
    language = "PT"
    conversation = firebase.get_or_create_conversation(
        client, phone_number, language=language, variant=prompt_service.UNASSIGNED,
        initial_phase=_initial_phase(),
    )

    # 2. Persist raw webhook metadata (first-touch raw message, contact profile,
    #    and every ad referral ever seen for this number).
    if raw_message is not None:
        firebase.record_metadata(
            client, phone_number, conversation, raw_message, contacts or []
        )

    # Dev commands — bypass all state logic
    if allow_dev_commands and message_text.strip().lower() == "/info":
        belief = _initial_belief_level(conversation)
        if conversation.prompt_variant:
            system_prompt = prompt_service.get_prompt(
                language=conversation.language,
                variant=conversation.prompt_variant,
                user_belief_level=belief,
                control_stage2=_control_stage2(conversation),
            )
        else:
            system_prompt = "(no arm assigned yet: drawn after the baseline questions)"
        info_text = (
            f"[Dev Info]\n"
            f"Variant: {conversation.prompt_variant or 'unassigned'}\n"
            f"Initial belief level (urnas): {belief}\n"
            f"Phase: {conversation.conversation_phase}"
            f"{' (' + conversation.screened_out_reason + ')' if conversation.screened_out_reason else ''}\n"
            f"Screening: {conversation.screening or 'not started'}\n"
            f"Turn count: {conversation.user_turn_count} "
            f"(ratings every {settings.TRUST_CHECK_INTERVAL}, ends after the rating at {settings.DEBRIEF_AFTER_TURNS})\n"
            f"Ratings: {len(conversation.feeling_array)} "
            f"(pre={conversation.rating_pre}/{conversation.rating_pre_system}, "
            f"post={conversation.rating_post}/{conversation.rating_post_system}, "
            f"exit={conversation.rating_exit}/{conversation.rating_exit_system}; urnas/system, "
            f"scale {settings.TRUST_RATING_MIN}-{settings.TRUST_RATING_MAX})\n"
            f"Debriefed: {bool(conversation.debriefed_at)}"
            f"{' (' + conversation.ended_reason + ')' if conversation.ended_reason else ''}\n"
            f"Ad referrals: {len(conversation.referrals)}\n"
            f"First-message raw captured: {bool(conversation.first_message_raw)}\n\n"
            f"--- System Prompt ---\n{system_prompt}"
        )
        return BotResponse(text_messages=[info_text])

    if allow_dev_commands and message_text.strip().lower() == "/reset":
        result = firebase.delete_conversation(client, phone_number)
        if result:
            return_msg = "User data has been reset. Please clear your chat and restart."
        else:
            return_msg = "Error deleting data. Contact Danny!"
        return BotResponse(text_messages=[return_msg])

    lang_cmd = message_text.strip().lower()
    if allow_dev_commands and lang_cmd in ("/lang en", "/lang pt"):
        new_lang = "EN" if lang_cmd == "/lang en" else "PT"
        base = conversation.prompt_variant.split("_prompt_", 1)[1]
        new_variant = f"{new_lang}_prompt_{base}"
        firebase.update_language(client, phone_number, new_lang, new_variant)
        confirm = {
            "EN": "Language switched to English.",
            "PT": "Idioma alterado para Português.",
        }
        return BotResponse(text_messages=[confirm[new_lang]])

    # 3. Route based on conversation phase
    phase = conversation.conversation_phase

    if phase == "awaiting_screening":
        return _handle_screening(client, phone_number, message_text, conversation, msg_type)

    elif phase == "screened_out":
        # Failed eligibility: repeat the closing message, never start the study.
        return BotResponse(
            text_messages=[trust_service.get_trust_prompt(conversation.language, "screening_closing")]
        )

    elif phase == "awaiting_initial_rating":
        return await _handle_initial_rating(
            client, phone_number, message_text, conversation, msg_type, rating_events
        )

    elif phase == "awaiting_check_in_rating":
        return await _handle_check_in_rating(
            client, phone_number, message_text, conversation, msg_type, rating_events
        )

    elif phase == "ended":
        # Study is over for this participant: no LLM call, just a short note.
        return BotResponse(
            text_messages=[
                trust_service.get_trust_prompt(
                    conversation.language, "conversation_ended"
                )
            ]
        )

    else:  # "normal" or unknown fallback
        return await _handle_normal_message(
            client, phone_number, message_text, conversation, msg_type
        )


def _handle_screening(client, phone_number, message_text, conversation, msg_type) -> BotResponse:
    """Eligibility screening before the baseline rating.

    First contact: intro (consent) text + question 1. Each answer is stored as
    it arrives. "sim" to both questions -> phase awaiting_initial_rating and the
    baseline rating prompt. Anything else -> closing message, phase screened_out.
    The document, with all ad/page metadata, exists from the first contact on.
    """
    lang = conversation.language

    if not conversation.intro_sent:
        firebase.update_intro_sent(client, phone_number)
        q = trust_service.pending_screening_question(conversation.screening)
        return BotResponse(
            text_messages=[trust_service.get_trust_prompt(lang, "intro")],
            send_screening=q["key"], trust_flow_language=lang,
        )

    q = trust_service.pending_screening_question(conversation.screening)
    if q is None:  # all answered already (should not happen); re-evaluate
        return _finish_screening(client, phone_number, conversation)

    answer = trust_service.parse_screening_answer(message_text, q, msg_type)
    if answer is None:
        return BotResponse(
            text_messages=[trust_service.get_trust_prompt(lang, f"screening_invalid_{q['key']}")],
            send_screening=q["key"], trust_flow_language=lang,
        )

    firebase.save_screening_answer(client, phone_number, conversation, q["field"], answer)
    if answer not in q["pass"]:
        firebase.finish_screening(client, phone_number, conversation, passed=False)
        return BotResponse(text_messages=[trust_service.get_trust_prompt(lang, "screening_closing")])

    nxt = trust_service.pending_screening_question(conversation.screening)
    if nxt is not None:
        return BotResponse(send_screening=nxt["key"], trust_flow_language=lang)
    return _finish_screening(client, phone_number, conversation)


def _finish_screening(client, phone_number, conversation) -> BotResponse:
    """All screening questions answered: pass only if every answer is a passing one."""
    lang = conversation.language
    passed = all(conversation.screening.get(q["field"]) in q["pass"] for q in trust_service.SCREENING_QUESTIONS)
    firebase.finish_screening(client, phone_number, conversation, passed=passed)
    if not passed:
        return BotResponse(text_messages=[trust_service.get_trust_prompt(lang, "screening_closing")])
    return BotResponse(send_trust_flow=True, trust_flow_language=lang, trust_flow_prompt_key="baseline")


async def _handle_initial_rating(
    client, phone_number, message_text, conversation, msg_type, rating_events=None
) -> BotResponse:
    """Handle messages when we're waiting for the baseline trust questions."""
    lang = conversation.language

    # First message ever (screening disabled) — intro + baseline prompt, don't process their message
    if not conversation.intro_sent:
        firebase.update_intro_sent(client, phone_number)
        return BotResponse(
            text_messages=[trust_service.get_trust_prompt(lang, "intro")],
            send_trust_flow=True,
            trust_flow_language=lang,
            trust_flow_prompt_key="baseline",
        )

    if msg_type == "interactive":
        score = trust_service.parse_interactive_rating(message_text)
    else:
        score = trust_service.parse_text_rating(message_text)

    if score is None:
        return BotResponse(
            text_messages=[trust_service.get_trust_prompt(lang, "invalid")],
            send_trust_flow=True,
            trust_flow_language=lang,
            trust_flow_prompt_key="baseline",
        )

    # Valid rating: save it (slot "pre") even if the participant is filtered out.
    firebase.save_trust_rating(client, phone_number, score, message_index=0, slot=_rating_slot(conversation),
                               events=rating_events)

    # High-trust filter: 7 on the voting-machine question ends the session here,
    # with the same closing message as the screening. No arm, no conversation.
    if trust_service.is_high_trust(score["urnas"]):
        firebase.screen_out(client, phone_number, conversation, reason="high_trust")
        return BotResponse(text_messages=[trust_service.get_trust_prompt(lang, "screening_closing")])

    # Passed: draw the study arm now, then start the conversation.
    if not conversation.prompt_variant:
        firebase.assign_variant(client, phone_number, conversation, f"{lang}_prompt_{prompt_service.assign_variant()}")
    firebase.update_conversation_phase(
        client, phone_number, "normal", user_turn_count=0
    )
    key = "rating_received_control" if _is_control(conversation) else "rating_received"
    opener = trust_service.get_trust_prompt(lang, key)
    # The opener is sent by the code, not the model; put it in the history so the
    # model sees its own first message and does not repeat it or ignore it.
    firebase.save_message(client, phone_number, opener, role="assistant")
    return BotResponse(text_messages=[opener])


async def _handle_check_in_rating(
    client, phone_number, message_text, conversation, msg_type, rating_events=None
) -> BotResponse:
    """Handle messages when we're waiting for a periodic check-in rating."""
    lang = conversation.language

    if msg_type == "interactive":
        score = trust_service.parse_interactive_rating(message_text)
    else:
        score = trust_service.parse_text_rating(message_text)

    if score is None:
        return BotResponse(
            text_messages=[trust_service.get_trust_prompt(lang, "invalid")],
            send_trust_flow=True,
            trust_flow_language=lang,
            trust_flow_prompt_key="check_in",
        )

    # Valid rating — save (slot "post" for the second rating) and return to normal conversation
    slot = _rating_slot(conversation)
    firebase.save_trust_rating(
        client, phone_number, score, message_index=conversation.user_turn_count, slot=slot,
        events=rating_events,
    )
    pending = firebase.get_and_clear_pending_response(client, phone_number)
    messages = []
    if pending:
        messages.append(pending)

    # Control condition: the second rating closes the dog segment; move on to the
    # voting machines. The transition is sent by the code and stored in the history.
    if slot == "post" and _is_control(conversation):
        transition = trust_service.get_trust_prompt(lang, "control_transition")
        firebase.save_message(client, phone_number, transition, role="assistant")
        messages.append(transition)

    # If the debrief turn landed on a check-in turn, the check-in ran first so
    # the rating is collected; now deliver the held reply and the debrief.
    if trust_service.should_debrief(conversation.user_turn_count,
                                    prompt_service.base_variant(conversation.prompt_variant),
                                    conversation.debriefed_at is not None):
        end = not settings.CONTINUE_AFTER_DEBRIEF
        firebase.mark_debriefed(client, phone_number, end_conversation=end, reason="limit")
        messages.append(trust_service.get_trust_prompt(lang, "debrief" if end else "debrief_open"))
        return BotResponse(text_messages=messages)

    firebase.update_conversation_phase(client, phone_number, "normal")
    return BotResponse(text_messages=messages)


async def end_conversation(client, phone_number: str, choice: str, rating: dict | None = None,
                           rating_events: list | None = None) -> BotResponse:
    """The participant ends the conversation early: the "Encerrar conversa" button
    (choice "rated" with the optional exit answers, "skipped", or "after_rating"
    when pressed right after a regular rating) or the page's inactivity timer
    (choice "inactivity"). Saves the exit rating if given, records the choice,
    sends the debrief and moves the conversation to the terminal 'ended' phase.
    Idempotent: an already-ended conversation just gets the debrief again.
    """
    conversation = firebase.get_or_create_conversation(
        client, phone_number, language="PT", variant=prompt_service.UNASSIGNED, initial_phase=_initial_phase())
    lang = conversation.language
    if conversation.conversation_phase == "ended":
        return BotResponse(text_messages=[trust_service.get_trust_prompt(lang, "debrief")])
    if conversation.conversation_phase in ("awaiting_screening", "screened_out", "awaiting_initial_rating"):
        # Nothing to debrief: the study conversation never started.
        key = "screening_closing" if conversation.conversation_phase == "screened_out" else "conversation_ended"
        return BotResponse(text_messages=[trust_service.get_trust_prompt(lang, key)])
    if rating is not None:
        firebase.save_trust_rating(client, phone_number, rating, message_index=conversation.user_turn_count,
                                   slot="exit", events=rating_events)
    if choice != "inactivity":
        firebase.record_exit(client, phone_number, choice, conversation.user_turn_count)
    firebase.get_and_clear_pending_response(client, phone_number)   # a held reply, if the timer fired mid-rating
    firebase.mark_debriefed(client, phone_number, end_conversation=True,
                            reason="inactivity" if choice == "inactivity" else "button")
    return BotResponse(text_messages=[trust_service.get_trust_prompt(lang, "debrief")])


async def _handle_normal_message(
    client, phone_number, message_text, conversation, msg_type
) -> BotResponse:
    """Handle normal LLM-powered conversation, with check-in trigger logic."""

    # Check if a check-in should trigger before processing this message
    new_turn_count = conversation.user_turn_count + 1

    system_prompt = prompt_service.get_prompt(
        language=conversation.language,
        variant=conversation.prompt_variant,
        user_belief_level=_initial_belief_level(conversation),
        control_stage2=_control_stage2(conversation),
    )

    recent_history = conversation.history[-(_N_HISTORY_TURNS * 2) :]
    messages = [{"role": msg.role, "content": msg.content} for msg in recent_history]
    messages.append({"role": "user", "content": message_text})

    ai_response = await openai_client.get_ai_response(messages, system_prompt)

    # Save messages to history
    firebase.save_message(client, phone_number, message_text, role="user")
    firebase.save_message(client, phone_number, ai_response, role="assistant")

    # Check if it's time for a rating after processing
    if trust_service.should_trigger_check_in(new_turn_count):
        firebase.save_pending_response(client, phone_number, ai_response)
        firebase.update_conversation_phase(
            client,
            phone_number,
            "awaiting_check_in_rating",
            user_turn_count=new_turn_count,
        )
        return BotResponse(
            send_trust_flow=True,
            trust_flow_language=conversation.language,
            trust_flow_prompt_key="check_in",
        )

    # Debrief turn (when it does not coincide with a check-in): answer, then
    # send the debrief and either end the conversation or let it continue.
    if trust_service.should_debrief(new_turn_count,
                                    prompt_service.base_variant(conversation.prompt_variant),
                                    conversation.debriefed_at is not None):
        firebase.update_conversation_phase(
            client, phone_number, "normal", user_turn_count=new_turn_count
        )
        end = not settings.CONTINUE_AFTER_DEBRIEF
        firebase.mark_debriefed(client, phone_number, end_conversation=end, reason="limit")
        return BotResponse(
            text_messages=[
                ai_response,
                trust_service.get_trust_prompt(conversation.language, "debrief" if end else "debrief_open"),
            ]
        )

    # No check-in — just the AI response
    firebase.update_conversation_phase(
        client, phone_number, "normal", user_turn_count=new_turn_count
    )
    return BotResponse(text_messages=[ai_response])
