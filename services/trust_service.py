from config import settings

TRUST_PROMPTS = {
    "EN": {
        "intro": """Hi! You're about to have a conversation with an artificial intelligence about Brazilian elections. This conversation is part of an academic research project on how humans and AI can engage around complex topics. Before we start, please tap the button below to answer one quick question.""",
        "invalid": """Please use the 'Rate Now' button below to submit your rating — we're not able to record ratings sent as text messages.""",
        "check_in": """Quick check-in: has your level of trust changed at all? Use the 'Rate Now' button below to update your score.""",
        "rating_received": """Thank you! To get us started, I'd love to hear your thoughts — what comes to mind when you think about the electronic voting system in Brazil?""",
        "debrief": """Thank you for participating in this research.

This conversation was part of an academic study conducted by researchers at the University of Texas at Austin on how people interact with artificial intelligence systems when discussing topics related to Brazilian elections.

If you are interested, here are some official and independent sources on how electronic voting machines work and how they are audited:

TSE: https://www.tse.jus.br/comunicacao/noticias/2026/Janeiro/urna-eletronica-entenda-como-o-equipamento-transformou-o-processo-eleitoral-brasileiro
Electoral Justice: https://www.justicaeleitoral.jus.br/urna-eletronica/

Thank you very much for your contribution to this research.
If you have any questions about the study, please contact us by email: k.vervuurt@utexas.edu""",
        "conversation_ended": """This research conversation has ended. Thank you again for participating. If you have any questions about the study, please contact us by email: k.vervuurt@utexas.edu""",
    },
    "PT": {
        "intro": """Olá!

Você vai participar de uma conversa com uma inteligência artificial sobre um tema relacionado às eleições brasileiras.

Esta conversa faz parte de uma pesquisa acadêmica conduzida por pesquisadores da Universidade do Texas em Austin. O estudo foi aprovado pelo Comitê de Ética em Pesquisa da universidade.

Sua participação é voluntária. Não coletamos informações que permitam identificar você, e suas respostas serão utilizadas de forma anônima exclusivamente para fins de pesquisa. Você pode encerrar a conversa a qualquer momento.

Antes de começar, clique no botão abaixo para responder uma pergunta rápida.""",
        "invalid": """Por favor, use o botão 'Avaliar Agora' abaixo para enviar sua avaliação — não conseguimos registrar notas enviadas por mensagens de texto.""",
        "check_in": """Verificação rápida: seu nível de confiança mudou? Use o botão 'Avaliar Agora' abaixo para atualizar sua pontuação.""",
        "rating_received": """Obrigado! Para começarmos, eu adoraria ouvir sua opinião — o que vem à sua mente quando você pensa no sistema de votação eletrônica no Brasil?""",
        "debrief": """Obrigado por participar desta pesquisa.

Esta conversa fez parte de um estudo acadêmico conduzido por pesquisadores da Universidade do Texas em Austin sobre a interação entre pessoas e sistemas de inteligência artificial ao discutir temas relacionados às eleições brasileiras.

Se você tiver interesse, aqui estão algumas fontes oficiais e independentes sobre como as urnas eletrônicas funcionam e são auditadas:

TSE: https://www.tse.jus.br/comunicacao/noticias/2026/Janeiro/urna-eletronica-entenda-como-o-equipamento-transformou-o-processo-eleitoral-brasileiro
Justiça Eleitoral: https://www.justicaeleitoral.jus.br/urna-eletronica/

Muito obrigado pela sua contribuição para esta pesquisa.
Se tiver dúvidas sobre a pesquisa, favor entrar em contato pelo email: k.vervuurt@utexas.edu""",
        "conversation_ended": """Esta conversa de pesquisa foi encerrada. Obrigado novamente por participar. Se tiver dúvidas sobre a pesquisa, favor entrar em contato pelo email: k.vervuurt@utexas.edu""",
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


def should_debrief(user_turn_count: int) -> bool:
    """Return True once the participant has sent enough messages to end the study."""
    return user_turn_count >= settings.DEBRIEF_AFTER_TURNS


def get_trust_prompt(language: str, prompt_key: str) -> str:
    """Get a trust-related prompt string for the given language.

    Args:
        language: "EN" or "PT"
        prompt_key: "intro", "invalid", "check_in", "rating_received",
            "debrief", or "conversation_ended"
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
