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
    """Which analysis slot the rating about to be saved fills."""
    n = len(conversation.feeling_array)
    if n == 0:
        return "pre"
    if n == 1:
        return "post"
    return None


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
    trust_flow_prompt_key: str = "intro"


async def handle_incoming_message(
    client,
    phone_number: str,
    message_text: str,
    msg_type: str,
    raw_message: dict | None = None,
    contacts: list | None = None,
    allow_dev_commands: bool = True,
) -> BotResponse:
    """Main entry point. Routes to the correct handler based on conversation phase.

    allow_dev_commands=False (web deployment) treats "/info", "/reset" and
    "/lang" as ordinary participant text instead of developer commands.

    raw_message / contacts are the untouched webhook objects from Meta. They are
    stored on the conversation for research metadata (see firebase.record_metadata).
    Condition assignment is random and independent of any ad referral by design.
    """

    # 1. Get or create conversation (assign variant if new)
    base_variant = prompt_service.assign_variant()
    language = "PT"
    full_prompt_name = f"{language}_prompt_{base_variant}"

    conversation = firebase.get_or_create_conversation(
        client, phone_number, language=language, variant=full_prompt_name
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
        system_prompt = prompt_service.get_prompt(
            language=conversation.language,
            variant=conversation.prompt_variant,
            user_belief_level=belief,
        )
        info_text = (
            f"[Dev Info]\n"
            f"Variant: {conversation.prompt_variant}\n"
            f"Initial belief level: {belief}\n"
            f"Phase: {conversation.conversation_phase}\n"
            f"Turn count: {conversation.user_turn_count} "
            f"(debrief after {settings.DEBRIEF_AFTER_TURNS})\n"
            f"Ratings: {len(conversation.feeling_array)} "
            f"(pre={conversation.rating_pre}, post={conversation.rating_post}, "
            f"scale {settings.TRUST_RATING_MIN}-{settings.TRUST_RATING_MAX})\n"
            f"Debriefed: {bool(conversation.debriefed_at)} "
            f"(due after turn {trust_service.debrief_turn(prompt_service.base_variant(conversation.prompt_variant))}, "
            f"{'conversation continues' if settings.CONTINUE_AFTER_DEBRIEF else 'conversation ends'})\n"
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

    if phase == "awaiting_initial_rating":
        return await _handle_initial_rating(
            client, phone_number, message_text, conversation, msg_type
        )

    elif phase == "awaiting_check_in_rating":
        return await _handle_check_in_rating(
            client, phone_number, message_text, conversation, msg_type
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


async def _handle_initial_rating(
    client, phone_number, message_text, conversation, msg_type
) -> BotResponse:
    """Handle messages when we're waiting for the first trust rating."""
    lang = conversation.language

    # First message ever — send the intro, don't process their message
    if not conversation.intro_sent:
        firebase.update_intro_sent(client, phone_number)
        return BotResponse(
            send_trust_flow=True,
            trust_flow_language=lang,
            trust_flow_prompt_key="intro",
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
            trust_flow_prompt_key="intro",
        )

    # Valid rating — save (slot "pre") and transition to normal conversation
    firebase.save_trust_rating(client, phone_number, score, message_index=0, slot=_rating_slot(conversation))
    firebase.update_conversation_phase(
        client, phone_number, "normal", user_turn_count=0
    )
    key = "rating_received_control" if _is_control(conversation) else "rating_received"
    return BotResponse(text_messages=[trust_service.get_trust_prompt(lang, key)])


async def _handle_check_in_rating(
    client, phone_number, message_text, conversation, msg_type
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
        client, phone_number, score, message_index=conversation.user_turn_count, slot=slot
    )
    pending = firebase.get_and_clear_pending_response(client, phone_number)
    messages = []
    if pending:
        messages.append(pending)

    # Control condition: the second rating closes the pets segment; move on to elections.
    if slot == "post" and _is_control(conversation):
        messages.append(trust_service.get_trust_prompt(lang, "control_transition"))

    # If the debrief turn landed on a check-in turn, the check-in ran first so
    # the rating is collected; now deliver the held reply and the debrief.
    if trust_service.should_debrief(conversation.user_turn_count,
                                    prompt_service.base_variant(conversation.prompt_variant),
                                    conversation.debriefed_at is not None):
        end = not settings.CONTINUE_AFTER_DEBRIEF
        firebase.mark_debriefed(client, phone_number, end_conversation=end)
        messages.append(trust_service.get_trust_prompt(lang, "debrief" if end else "debrief_open"))
        return BotResponse(text_messages=messages)

    firebase.update_conversation_phase(client, phone_number, "normal")
    return BotResponse(text_messages=messages)


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
        firebase.mark_debriefed(client, phone_number, end_conversation=end)
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
