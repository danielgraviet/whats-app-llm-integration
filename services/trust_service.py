from config import settings

TRUST_PROMPTS = {
    "EN": {
        "intro": """Hello!

You are about to take part in a conversation with an artificial intelligence about a topic related to Brazilian elections.

This conversation is part of an academic research study conducted by researchers at the University of Texas at Austin. The study was approved by the university's Research Ethics Committee.

Your participation is voluntary, and you may end the conversation at any time. Your answers will be treated confidentially and used exclusively for research purposes. Please do not share your name, phone number, address, or other information that could identify you during the conversation.

Before we begin, I need you to answer a few quick questions.""",
        "screening_q1": """Before we begin, we need to confirm some information about you.

1. Are you 18 years of age or older?""",
        "screening_q2": """2. Are you eligible to vote in Brazilian elections?""",
        "screening_invalid_q1": """Please answer "Yes" or "No".""",
        "screening_invalid_q2": """Please answer "Yes", "No" or "I don't know".""",
        "screening_closing": """Thank you for your interest! To take part in this study you must be 18 or older and eligible to vote in Brazilian elections.""",
        "baseline": """How much do you trust that Brazilian electronic voting machines record and count every vote correctly?

Use the bar below to indicate your level of trust from 0% to 100%, where 0% means you do not trust them at all and 100% means you trust them completely.

0% = I do not trust them at all
100% = I trust them completely""",
        "invalid": """Please use the 'Rate Now' button below to submit your rating — we're not able to record ratings sent as text messages.""",
        "check_in": """Before continuing the conversation, please answer one more quick question by tapping the button below.

How much do you trust that Brazilian electronic voting machines record and count every vote correctly?

Use the bar below to indicate your level of trust from 0% to 100%, where 0% means you do not trust them at all and 100% means you trust them completely.

0% = I do not trust them at all
100% = I trust them completely""",
        "rating_received": """Thank you! To get us started, I'd love to hear your thoughts: what comes to mind when you think about Brazil's electronic voting machines?""",
        "debrief": """Thank you for participating in this research.

This conversation was part of an academic study conducted by researchers at the University of Texas at Austin on how people interact with artificial intelligence systems when discussing topics related to Brazilian elections.

If you are interested, here are some official and independent sources on how electronic voting machines work and how they are audited:

TSE: https://www.tse.jus.br/comunicacao/noticias/2026/Janeiro/urna-eletronica-entenda-como-o-equipamento-transformou-o-processo-eleitoral-brasileiro
Electoral Justice: https://www.justicaeleitoral.jus.br/urna-eletronica/

Thank you very much for your contribution to this research.
If you have any questions about the study, please contact us by email: k.vervuurt@utexas.edu""",
        "conversation_ended": """This research conversation has ended. Thank you again for participating. If you have any questions about the study, please contact us by email: k.vervuurt@utexas.edu""",
        "debrief_open": """Thank you for participating in this research.

This conversation is part of an academic study conducted by researchers at the University of Texas at Austin on how people interact with artificial intelligence systems when discussing topics related to Brazilian elections.

If you are interested, here are some official and independent sources on how electronic voting machines work and how they are audited:

TSE: https://www.tse.jus.br/comunicacao/noticias/2026/Janeiro/urna-eletronica-entenda-como-o-equipamento-transformou-o-processo-eleitoral-brasileiro
Electoral Justice: https://www.justicaeleitoral.jus.br/urna-eletronica/

Thank you very much for your contribution to this research. If you would like, you are welcome to keep the conversation going for as long as you wish; just keep writing. To finish, simply close this page.
If you have any questions about the study, please contact us by email: k.vervuurt@utexas.edu""",
        "rating_received_control": """Thank you! Let's talk about Brazilian elections. But first, to start with something lighter, I'd like to know: what do you think of the "cachorro caramelo", the caramel-colored dog so well known in Brazil?""",
        "control_transition": """Thank you! Now the topic changes: let's talk about the elections. To start, what comes to mind when you think about Brazil's electronic voting machines?""",
    },
    "PT": {
        "intro": """Olá!

Você vai participar de uma conversa com uma inteligência artificial sobre um tema relacionado às eleições brasileiras.

Esta conversa faz parte de uma pesquisa acadêmica conduzida por pesquisadores da Universidade do Texas em Austin. O estudo foi aprovado pelo Comitê de Ética em Pesquisa da universidade.

Sua participação é voluntária, e você pode encerrar a conversa a qualquer momento. Suas respostas serão tratadas de forma confidencial e utilizadas exclusivamente para fins de pesquisa. Por favor, não compartilhe seu nome, telefone, endereço ou outras informações que possam identificar você durante a conversa.

Antes de começar, preciso que você responda algumas perguntas rápidas.""",
        "screening_q1": """Antes de começar, precisamos confirmar algumas informações sobre você.

1. Você tem 18 anos ou mais?""",
        "screening_q2": """2. Você está apto(a) a votar nas eleições brasileiras?""",
        "screening_invalid_q1": """Por favor, responda "Sim" ou "Não".""",
        "screening_invalid_q2": """Por favor, responda "Sim", "Não" ou "Não sei".""",
        "screening_closing": """Obrigado pelo interesse! Para participar desta pesquisa, é necessário ter 18 anos ou mais e estar apto(a) a votar nas eleições brasileiras.""",
        "baseline": """O quanto você confia que as urnas eletrônicas brasileiras registram e contam corretamente cada voto?

Use a barra abaixo para indicar seu grau de confiança de 0% a 100%, onde 0% significa que você não confia nem um pouco e 100% indica que confia totalmente.

0% = Não confio nem um pouco
100% = Confio totalmente""",
        "invalid": """Por favor, use o botão 'Avaliar Agora' abaixo para enviar sua avaliação — não conseguimos registrar notas enviadas por mensagens de texto.""",
        "check_in": """Antes de continuar a conversa, responda mais uma pergunta rápida clicando no botão abaixo.

O quanto você confia que as urnas eletrônicas brasileiras registram e contam corretamente cada voto?

Use a barra abaixo para indicar seu grau de confiança de 0% a 100%, onde 0% significa que você não confia nem um pouco e 100% indica que confia totalmente.

0% = Não confio nem um pouco
100% = Confio totalmente""",
        "rating_received": """Obrigado! Para começarmos, eu adoraria ouvir sua opinião: o que vem à sua mente quando você pensa nas urnas eletrônicas do Brasil?""",
        "debrief": """Obrigado por participar desta pesquisa.

Esta conversa fez parte de um estudo acadêmico conduzido por pesquisadores da Universidade do Texas em Austin sobre a interação entre pessoas e sistemas de inteligência artificial ao discutir temas relacionados às eleições brasileiras.

Se você tiver interesse, aqui estão algumas fontes oficiais e independentes sobre como as urnas eletrônicas funcionam e são auditadas:

TSE: https://www.tse.jus.br/comunicacao/noticias/2026/Janeiro/urna-eletronica-entenda-como-o-equipamento-transformou-o-processo-eleitoral-brasileiro
Justiça Eleitoral: https://www.justicaeleitoral.jus.br/urna-eletronica/

Muito obrigado pela sua contribuição para esta pesquisa.
Se tiver dúvidas sobre a pesquisa, favor entrar em contato pelo email: k.vervuurt@utexas.edu""",
        "conversation_ended": """Esta conversa de pesquisa foi encerrada. Obrigado novamente por participar. Se tiver dúvidas sobre a pesquisa, favor entrar em contato pelo email: k.vervuurt@utexas.edu""",
        "debrief_open": """Obrigado por participar desta pesquisa.

Esta conversa faz parte de um estudo acadêmico conduzido por pesquisadores da Universidade do Texas em Austin sobre a interação entre pessoas e sistemas de inteligência artificial ao discutir temas relacionados às eleições brasileiras.

Se você tiver interesse, aqui estão algumas fontes oficiais e independentes sobre como as urnas eletrônicas funcionam e são auditadas:

TSE: https://www.tse.jus.br/comunicacao/noticias/2026/Janeiro/urna-eletronica-entenda-como-o-equipamento-transformou-o-processo-eleitoral-brasileiro
Justiça Eleitoral: https://www.justicaeleitoral.jus.br/urna-eletronica/

Muito obrigado pela sua contribuição para esta pesquisa. Se quiser, você pode continuar a conversa pelo tempo que desejar — é só continuar escrevendo. Para encerrar, basta fechar esta página.
Se tiver dúvidas sobre a pesquisa, favor entrar em contato pelo email: k.vervuurt@utexas.edu""",
        "rating_received_control": """Obrigado! Vamos conversar sobre as eleições brasileiras. Antes, para começar com um assunto mais leve, queria saber: o que você acha do cachorro caramelo, tão conhecido aqui no Brasil?""",
        "control_transition": """Obrigado! Agora vamos mudar de assunto e falar sobre as eleições. Para começar, o que vem à sua mente quando você pensa nas urnas eletrônicas do Brasil?""",
    },
}

# Eligibility screening, asked in order before the baseline rating. A
# participant proceeds only with "sim" to both; "nao" to either, or "nao_sei"
# to the voting question, ends the session (phase screened_out).
SCREENING_QUESTIONS = [
    {"key": "q1", "field": "age_18", "text_key": "screening_q1",
     "options": [("sim", {"PT": "Sim", "EN": "Yes"}), ("nao", {"PT": "Não", "EN": "No"})],
     "pass": {"sim"}},
    {"key": "q2", "field": "eligible_voter", "text_key": "screening_q2",
     "options": [("sim", {"PT": "Sim", "EN": "Yes"}), ("nao", {"PT": "Não", "EN": "No"}),
                 ("nao_sei", {"PT": "Não sei", "EN": "I don't know"})],
     "pass": {"sim"}},
]
_SCREENING_TEXT_ANSWERS = {
    "sim": "sim", "s": "sim", "yes": "sim", "y": "sim",
    "nao": "nao", "não": "nao", "n": "nao", "no": "nao",
    "nao sei": "nao_sei", "não sei": "nao_sei", "naosei": "nao_sei", "nao_sei": "nao_sei",
    "i don't know": "nao_sei", "i dont know": "nao_sei", "don't know": "nao_sei", "dont know": "nao_sei",
}


def pending_screening_question(screening: dict) -> dict | None:
    """The first screening question without a stored answer, or None when all answered."""
    for q in SCREENING_QUESTIONS:
        if screening.get(q["field"]) is None:
            return q
    return None


def parse_screening_answer(text: str, question: dict, msg_type: str) -> str | None:
    """Interactive answers arrive as 'screening_<q>_<answer>' (web buttons /
    WhatsApp list ids); text answers are matched case- and accent-insensitively."""
    valid = {opt for opt, _ in question["options"]}
    t = text.strip()
    if msg_type == "interactive":
        prefix = f"screening_{question['key']}_"
        if t.startswith(prefix) and t[len(prefix):] in valid:
            return t[len(prefix):]
        return None
    import unicodedata
    norm = "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")
    norm = norm.rstrip(".!")
    ans = _SCREENING_TEXT_ANSWERS.get(norm)
    return ans if ans in valid else None


def screening_options(question: dict, language: str) -> list[dict]:
    lang = language.upper() if language.upper() in ("PT", "EN") else "PT"
    return [{"id": f"screening_{question['key']}_{opt}", "value": opt, "label": labels[lang]}
            for opt, labels in question["options"]]


def _in_range(value: int) -> bool:
    return settings.TRUST_RATING_MIN <= value <= settings.TRUST_RATING_MAX


def parse_text_rating(text: str) -> int | None:
    """Try to extract a valid rating (within the configured scale) from plain text like '7'."""
    try:
        value = int(text.strip())
        if _in_range(value):
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
        if _in_range(value):
            return value
    except (ValueError, IndexError):
        pass
    return None


def should_trigger_check_in(user_turn_count: int) -> bool:
    """Return True if it's time for a periodic trust check-in."""
    interval = settings.TRUST_CHECK_INTERVAL
    return user_turn_count > 0 and user_turn_count % interval == 0


def debrief_turn(variant_base: str | None) -> int:
    """Turn after which the debrief is shown. The control condition talks about
    pets first, so its debrief comes one check-in interval later, after it has
    had the same number of election turns as the other conditions."""
    from services import prompt_service  # local import: avoids a cycle
    extra = settings.TRUST_CHECK_INTERVAL if variant_base == prompt_service.CONTROL_VARIANT else 0
    return settings.DEBRIEF_AFTER_TURNS + extra


def should_debrief(user_turn_count: int, variant_base: str | None = None, already_debriefed: bool = False) -> bool:
    """Return True when the debrief is due and has not been shown yet."""
    return (not already_debriefed) and user_turn_count >= debrief_turn(variant_base)


def get_trust_prompt(language: str, prompt_key: str) -> str:
    """Get a trust-related prompt string for the given language.

    Args:
        language: "EN" or "PT"
        prompt_key: "intro", "screening_q1", "screening_q2", "screening_closing",
            "baseline", "invalid", "check_in", "rating_received", "debrief",
            "conversation_ended", ...
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
