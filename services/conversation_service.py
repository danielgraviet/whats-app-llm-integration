import dataclasses

from database import firebase
from integrations import openai_client
from services import prompt_service, trust_service

_N_HISTORY_TURNS = 5


@dataclasses.dataclass
class BotResponse:
    text_messages: list[str] = dataclasses.field(default_factory=list)
    send_trust_flow: bool = False
    trust_flow_language: str = "EN"
    trust_flow_prompt_key: str = "intro"


async def handle_incoming_message(
    client, phone_number: str, message_text: str, msg_type: str
) -> BotResponse:
    """Main entry point. Routes to the correct handler based on conversation phase."""

    # 1. Get or create conversation (assign variant if new)
    base_variant = prompt_service.assign_variant()
    language = "EN"
    full_prompt_name = f"{language}_prompt_{base_variant}"

    conversation = firebase.get_or_create_conversation(
        client, phone_number, language=language, variant=full_prompt_name
    )

    # Dev commands — bypass all state logic
    if message_text.strip().lower() == "/info":
        system_prompt = prompt_service.get_prompt(
            language=conversation.language, variant=conversation.prompt_variant
        )
        info_text = (
            f"[Dev Info]\n"
            f"Variant: {conversation.prompt_variant}\n"
            f"Phase: {conversation.conversation_phase}\n"
            f"Turn count: {conversation.user_turn_count}\n"
            f"Ratings: {len(conversation.feeling_array)}\n\n"
            f"--- System Prompt ---\n{system_prompt}"
        )
        return BotResponse(text_messages=[info_text])

    if message_text.strip().lower() == "/reset":
        result = firebase.delete_conversation(client, phone_number)
        if result:
            return_msg = "User data has been reset. Please clear your chat and restart."
        else:
            return_msg = "Error deleting data. Contact Danny!"
        return BotResponse(text_messages=[return_msg])

    # 2. Route based on conversation phase
    phase = conversation.conversation_phase

    if phase == "awaiting_initial_rating":
        return await _handle_initial_rating(
            client, phone_number, message_text, conversation, msg_type
        )

    elif phase == "awaiting_check_in_rating":
        return await _handle_check_in_rating(
            client, phone_number, message_text, conversation, msg_type
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

    # Valid rating — save and transition to normal conversation
    firebase.save_trust_rating(client, phone_number, score, message_index=0)
    firebase.update_conversation_phase(
        client, phone_number, "normal", user_turn_count=0
    )
    return BotResponse(
        text_messages=[trust_service.get_trust_prompt(lang, "rating_received")]
    )


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

    # Valid rating — save and return to normal conversation
    firebase.save_trust_rating(
        client, phone_number, score, message_index=conversation.user_turn_count
    )
    firebase.update_conversation_phase(client, phone_number, "normal")
    pending = firebase.get_and_clear_pending_response(client, phone_number)
    messages = []  # can add a potential, "thanks for answering"
    if pending:
        messages.append(pending)
    return BotResponse(text_messages=messages)


async def _handle_normal_message(
    client, phone_number, message_text, conversation, msg_type
) -> BotResponse:
    """Handle normal LLM-powered conversation, with check-in trigger logic."""

    # Check if a check-in should trigger before processing this message
    new_turn_count = conversation.user_turn_count + 1

    system_prompt = prompt_service.get_prompt(
        language=conversation.language, variant=conversation.prompt_variant
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

    # No check-in — just the AI response
    firebase.update_conversation_phase(
        client, phone_number, "normal", user_turn_count=new_turn_count
    )
    return BotResponse(text_messages=[ai_response])
