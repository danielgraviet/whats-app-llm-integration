import random
from pathlib import Path

from config import settings

# Phase 2 arms (prompts v6, 17 Oct 2026), drawn with equal probability once the
# participant has passed the baseline high-trust filter. The phase-1 arms and
# their prompt files (v5, Portuguese) were removed on 2026-10-20; see git
# history before that date if an old conversation's prompt is ever needed.
VARIANTS = [
    "A_control_v6",
    "B_motivational_v6",
    "C_refutational_v6",
]

LANGUAGES = ["EN", "PT"]

# The control condition runs in two stages: six messages about the cachorro
# caramelo (A_control_v6) and, after the rating at the sixth message, a
# question-only conversation about the voting machines (A2_control_elections_v6).
# One prompt text in the study document, two files here, because the code
# counts the turns and the model only sees the last few.
CONTROL_VARIANT = "A_control_v6"
CONTROL_STAGE2_VARIANT = "A2_control_elections_v6"

# prompt_variant of a document whose arm has not been drawn yet.
UNASSIGNED = ""

_cache: dict[str, str] = {}

# Every prompt file contains this literal token where the participant's initial
# trust rating (1-10) should appear. It is substituted at request time.
BELIEF_PLACEHOLDER = "**user_belief_level**"
_BELIEF_UNKNOWN = "not provided"
# Scale endpoints, so the same prompt text serves the 1-10 and 0-100 deployments.
RATING_MIN_PLACEHOLDER = "**rating_min**"
RATING_MAX_PLACEHOLDER = "**rating_max**"


def base_variant(prompt_variant: str) -> str:
    """'PT_prompt_A_control_v6' -> 'A_control_v6'."""
    return prompt_variant.split("_prompt_", 1)[1] if "_prompt_" in prompt_variant else prompt_variant


def get_prompt(
    language: str, variant: str, user_belief_level: int | None = None, control_stage2: bool = False
) -> str:
    """Load a prompt template from file and fill in the participant's rating.

    Args:
        language: "EN" or "PT"
        variant: e.g. "PT_prompt_A_control_v6"
        user_belief_level: the participant's initial 1-10 trust rating. If None,
            the placeholder is replaced with "not provided" so the raw token
            never reaches the model.

    Example: get_prompt("PT", "PT_prompt_B_motivational_v6", 4)
    """
    if control_stage2 and base_variant(variant) == CONTROL_VARIANT:
        variant = f"{language.upper()}_prompt_{CONTROL_STAGE2_VARIANT}"
    key = variant
    if key not in _cache:
        folder = language.lower()  # en or pt
        filename = f"{variant}.txt"
        path = Path(__file__).parent.parent / "prompt" / folder / filename
        if not path.is_file():
            # The v6 prompts are written in English and kept once, under pt/
            # (there is no en/ folder). An EN_ variant falls back to the same text.
            path = Path(__file__).parent.parent / "prompt" / "pt" / filename.replace(f"{language.upper()}_prompt_", "PT_prompt_", 1)
        _cache[key] = path.read_text()

    template = _cache[key]
    belief = str(user_belief_level) if user_belief_level is not None else _BELIEF_UNKNOWN
    return (template.replace(BELIEF_PLACEHOLDER, belief)
            .replace(RATING_MIN_PLACEHOLDER, str(settings.TRUST_RATING_MIN))
            .replace(RATING_MAX_PLACEHOLDER, str(settings.TRUST_RATING_MAX)))


def assign_variant() -> str:
    """Draws the study arm, equal probability. Called after the baseline filter."""
    return random.choice(VARIANTS)
