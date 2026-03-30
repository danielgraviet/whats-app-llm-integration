from config import settings

TRUST_PROMPTS = {
    "EN": {
        "intro": (
            "Welcome! You are participating in a research study about "
            "trust in electronic voting machines.\n\n"
            "To get started, please rate your current level of trust using "
            "the 'Rate Now' button below — do not type your rating in the chat."
        ),
        "invalid": (
            "Please use the 'Rate Now' button below to submit your rating "
            "— we're not able to record ratings sent as text messages."
        ),
        "check_in": (
            "Quick check-in: has your level of trust changed at all? "
            "Use the 'Rate Now' button below to update your score."
        ),
        "rating_received": (
            "Thank you! To get us started, I'd love to hear your thoughts — "
            "what comes to mind when you think about the electronic voting system in Brazil?"
        ),
    },
    "PT": {
        "intro": (
            "Bem-vindo! Você está participando de um estudo de pesquisa sobre a "
            "confiança nas urnas eletrônicas.\n\n"
            "Para começar, por favor, avalie seu nível atual de confiança usando "
            "o botão 'Avaliar Agora' abaixo — não digite sua avaliação no chat."
        ),
        "invalid": (
            "Por favor, use o botão 'Avaliar Agora' abaixo para enviar sua avaliação "
            "— não conseguimos registrar notas enviadas por mensagens de texto."
        ),
        "check_in": (
            "Verificação rápida: seu nível de confiança mudou? "
            "Use o botão 'Avaliar Agora' abaixo para atualizar sua pontuação."
        ),
        "rating_received": (
            "Obrigado! Para começarmos, eu adoraria ouvir sua opinião — "
            "o que vem à sua mente quando você pensa no sistema de votação eletrônica no Brasil?"
        ),
    },
}


def parse_text_rating(text: str) -> int | None:
    """Try to extract a valid 1-10 rating from plain text like '7'."""
    try:
        value = int(text.strip())
        if 1 <= value <= 10:
            return value
    except ValueError:
        pass
    return None


def parse_interactive_rating(list_reply_id: str) -> int | None:
    """Try to extract a valid 1-10 rating from user input.

    Returns the integer score if valid, None otherwise.
    Only accepts bare integers (e.g. "7"), not "seven" or "7/10".
    """
    if not list_reply_id.startswith("rating_"):
        # add potential logging here.
        return None
    try:
        value = int(list_reply_id.split("_")[1])
        if 1 <= value <= 10:
            return value
    except (ValueError, IndexError):
        pass
    return None


def should_trigger_check_in(user_turn_count: int) -> bool:
    """Return True if it's time for a periodic trust check-in."""
    interval = settings.TRUST_CHECK_INTERVAL
    return user_turn_count > 0 and user_turn_count % interval == 0


def get_trust_prompt(language: str, prompt_key: str) -> str:
    """Get a trust-related prompt string for the given language.

    Args:
        language: "EN" or "PT"
        prompt_key: "intro", "invalid", "check_in", or "rating_received"
    """
    lang = language.upper()
    if lang not in TRUST_PROMPTS:
        lang = "EN"
    prompt = TRUST_PROMPTS[lang][prompt_key]
    if not settings.USE_FLOWS:
        prompt = (
            prompt.replace(
                "Please select your rating from the list below.",
                "Please reply with a number from 1 to 10.",
            )
            .replace(
                "please use the list below to select your rating.",
                "please reply with a number from 1 to 10.",
            )
            .replace(
                "Por favor, selecione sua avaliacao na lista abaixo.",
                "Por favor, responda com um numero de 1 a 10.",
            )
            .replace(
                "Por favor, use a lista abaixo para selecionar sua avaliacao.",
                "Por favor, responda com um numero de 1 a 10.",
            )
        )
    return prompt
