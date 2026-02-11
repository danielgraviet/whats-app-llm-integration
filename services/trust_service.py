from config import settings

TRUST_PROMPTS = {
    "EN": {
        "intro": (
            "Welcome! You are participating in a research study about "
            "trust in electronic voting machines.\n\n"
            "Before we begin, on a scale of 1 to 10, how much do you "
            "trust Brazil's electronic voting system?\n\n"
            "(1 = no trust at all, 10 = complete trust)\n\n"
            "Please select your rating from the list below."
        ),
        "invalid": (
            "Before we continue, please use the list below to select your rating."
        ),
        "check_in": (
            "Quick check-in: On a scale of 1 to 10, how much do you "
            "trust Brazil's electronic voting system right now?\n\n"
            "(1 = no trust at all, 10 = complete trust)\n\n"
            "Please select your rating from the list below."
        ),
        "rating_received": (
            "Thank you for sharing. Let's continue our conversation. What were you about to ask?"
        ),
    },
    "PT": {
        "intro": (
            "Bem-vindo! Voce esta participando de um estudo sobre "
            "confianca nas urnas eletronicas.\n\n"
            "Antes de comecarmos, em uma escala de 1 a 10, quanto voce "
            "confia no sistema eletronico de votacao do Brasil?\n\n"
            "(1 = nenhuma confianca, 10 = confianca total)\n\n"
            "Por favor, selecione sua avaliacao na lista abaixo."
        ),
        "invalid": ("Por favor, use a lista abaixo para selecionar sua avaliacao."),
        "check_in": (
            "Verificacao rapida: Em uma escala de 1 a 10, quanto voce "
            "confia no sistema eletronico de votacao do Brasil agora?\n\n"
            "(1 = nenhuma confianca, 10 = confianca total)\n\n"
            "Por favor, selecione sua avaliacao na lista abaixo."
        ),
        "rating_received": (
            "Obrigado por compartilhar. Vamos continuar nossa conversa."
        ),
    },
}


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
    return TRUST_PROMPTS[lang][prompt_key]
