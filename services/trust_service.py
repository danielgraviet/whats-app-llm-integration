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
        "screening_closing": """Thank you for your answer! At this stage the study is talking with a specific profile of participants, so your participation ends here. We very much appreciate your time.""",
        "baseline": """Before we begin, please answer two quick questions.""",
        "invalid": """Please use the buttons above to answer the two questions.""",
        "check_in": """Before we continue, please answer two more quick questions.""",
        "exit_rating": """Before you go, could you answer two quick questions? It's optional.""",
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
        "rating_received_control": """Before we talk about the Brazilian elections, I'm going to ask a few quick questions about a lighter subject, and then we'll get to the elections. To start: what do you think of the cachorro caramelo, so well known in Brazil?""",
        "control_transition": """Thank you! Now let's change the subject and talk about the electronic voting machines. To start, what comes to mind when you think about Brazil's electronic voting machines?""",
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
        "screening_closing": """Obrigado pela sua resposta! Nesta etapa, a pesquisa está conversando com um perfil específico de participantes, e por isso sua participação termina aqui. Agradecemos muito o seu tempo.""",
        "baseline": """Antes de começar, responda duas perguntas rápidas.""",
        "invalid": """Por favor, use os botões acima para responder às duas perguntas.""",
        "check_in": """Antes de continuar, responda mais duas perguntas rápidas.""",
        "exit_rating": """Antes de sair, você pode responder duas perguntas rápidas? É opcional.""",
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
        "rating_received_control": """Antes de conversar sobre as eleições brasileiras, vou fazer algumas perguntas rápidas sobre um assunto mais leve e depois a gente fala das eleições. Para começar: o que você acha do cachorro caramelo, tão conhecido no Brasil?""",
        "control_transition": """Obrigado! Agora vamos mudar de assunto e conversar sobre as urnas eletrônicas. Para começar, o que vem à sua mente quando você pensa nas urnas eletrônicas do Brasil?""",
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


# The two trust questions, asked together at the baseline, after the 6th, 12th,
# 18th and 24th participant messages, and optionally when the participant ends
# early. Question 2 ("urnas") is the primary measure and drives the high-trust
# filter; question 1 ("system") is trust in the electoral system as a whole.
RATING_QUESTIONS = [
    {"key": "system", "text": {"PT": "O quanto você confia no sistema eleitoral brasileiro como um todo?",
                               "EN": "How much do you trust the Brazilian electoral system as a whole?"}},
    {"key": "urnas", "text": {"PT": "O quanto você confia que as urnas eletrônicas brasileiras registram e contam corretamente cada voto?",
                              "EN": "How much do you trust that Brazilian electronic voting machines record and count every vote correctly?"}},
]
# Seven labelled buttons, shown with the number, in this order, for both questions.
RATING_OPTIONS = [
    (1, {"PT": "Não confio nada", "EN": "Do not trust at all"}),
    (2, {"PT": "Confio muito pouco", "EN": "Trust very little"}),
    (3, {"PT": "Confio pouco", "EN": "Trust a little"}),
    (4, {"PT": "Confio mais ou menos", "EN": "Trust somewhat"}),
    (5, {"PT": "Confio muito", "EN": "Trust a lot"}),
    (6, {"PT": "Confio quase totalmente", "EN": "Trust almost completely"}),
    (7, {"PT": "Confio totalmente", "EN": "Trust completely"}),
]
# A baseline answer of this value to the voting-machine question ends the session
# before any conversation (Step 4 of the phase-2 design).
HIGH_TRUST_SCORE = 7


def _lang(language: str) -> str:
    return language.upper() if language.upper() in ("PT", "EN") else "PT"


def rating_questions(language: str) -> list[dict]:
    lang = _lang(language)
    return [{"key": q["key"], "text": q["text"][lang]} for q in RATING_QUESTIONS]


def rating_options(language: str) -> list[dict]:
    lang = _lang(language)
    return [{"value": v, "label": labels[lang]} for v, labels in RATING_OPTIONS]


def rating_label(value: int, language: str) -> str:
    lang = _lang(language)
    return next((labels[lang] for v, labels in RATING_OPTIONS if v == value), str(value))


def is_high_trust(urnas: int) -> bool:
    return urnas >= HIGH_TRUST_SCORE


def _in_range(value: int) -> bool:
    return settings.TRUST_RATING_MIN <= value <= settings.TRUST_RATING_MAX


def _pair(values: list[str]) -> dict | None:
    """["4", "6"] -> {"system": 4, "urnas": 6}; a single number is the urnas
    answer alone (legacy / text channel). None if anything is out of range."""
    try:
        nums = [int(v) for v in values]
    except ValueError:
        return None
    if len(nums) == 1:
        return {"system": None, "urnas": nums[0]} if _in_range(nums[0]) else None
    if len(nums) == 2 and all(_in_range(n) for n in nums):
        return {"system": nums[0], "urnas": nums[1]}
    return None


def parse_text_rating(text: str) -> dict | None:
    """Plain text like "4 6", "4,6" or "6" -> {"system": .., "urnas": ..}."""
    return _pair(text.replace(",", " ").split())


def parse_interactive_rating(list_reply_id: str) -> dict | None:
    """Button reply id "rating_<system>_<urnas>" (or legacy "rating_<urnas>")
    -> {"system": .., "urnas": ..}; None if malformed or out of range."""
    if not list_reply_id.startswith("rating_"):
        return None
    return _pair(list_reply_id[len("rating_"):].split("_"))


def should_trigger_check_in(user_turn_count: int) -> bool:
    """Return True if it's time for a periodic trust check-in."""
    interval = settings.TRUST_CHECK_INTERVAL
    return user_turn_count > 0 and user_turn_count % interval == 0


def debrief_turn(variant_base: str | None = None) -> int:
    """Turn after whose rating the debrief is shown and the conversation ends:
    DEBRIEF_AFTER_TURNS (24) in every arm, control included."""
    return settings.DEBRIEF_AFTER_TURNS


def should_debrief(user_turn_count: int, variant_base: str | None = None, already_debriefed: bool = False) -> bool:
    """Return True when the debrief is due and has not been shown yet."""
    return (not already_debriefed) and user_turn_count >= debrief_turn(variant_base)


def get_trust_prompt(language: str, prompt_key: str) -> str:
    """Get a trust-related prompt string for the given language.

    Args:
        language: "EN" or "PT"
        prompt_key: "intro", "screening_q1", "screening_q2", "screening_closing",
            "baseline", "invalid", "check_in", "exit_rating", "rating_received",
            "rating_received_control", "control_transition", "debrief",
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
