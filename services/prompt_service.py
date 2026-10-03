import random
from pathlib import Path

from config import settings

VARIANTS = [
    "A_control_condition",
    "B_motivational_learning",
    "C_perspective",
    "D_christmas_dinner",
    "E_critical_thinking",
]

LANGUAGES = ["EN", "PT"]

# The control condition runs in two stages: a conversation about cats and dogs
# (its own prompt, A_control_condition) and, after the second rating, a
# conversation about elections in general (A2_control_elections).
CONTROL_VARIANT = "A_control_condition"
CONTROL_STAGE2_VARIANT = "A2_control_elections"

_cache: dict[str, str] = {}

# Every prompt file contains this literal token where the participant's initial
# trust rating (1-10) should appear. It is substituted at request time.
BELIEF_PLACEHOLDER = "**user_belief_level**"
_BELIEF_UNKNOWN = "not provided"
# Scale endpoints, so the same prompt text serves the 1-10 and 0-100 deployments.
RATING_MIN_PLACEHOLDER = "**rating_min**"
RATING_MAX_PLACEHOLDER = "**rating_max**"


def base_variant(prompt_variant: str) -> str:
    """'PT_prompt_A_control_condition' -> 'A_control_condition'."""
    return prompt_variant.split("_prompt_", 1)[1] if "_prompt_" in prompt_variant else prompt_variant


def get_prompt(
    language: str, variant: str, user_belief_level: int | None = None, control_stage2: bool = False
) -> str:
    """Load a prompt template from file and fill in the participant's rating.

    Args:
        language: "EN" or "PT"
        variant: e.g. "EN_prompt_A_control_condition"
        user_belief_level: the participant's initial 1-10 trust rating. If None,
            the placeholder is replaced with "not provided" so the raw token
            never reaches the model.

    Example: get_prompt("EN", "EN_prompt_A_control_condition", 7)
    """
    if control_stage2 and base_variant(variant) == CONTROL_VARIANT:
        variant = f"{language.upper()}_prompt_{CONTROL_STAGE2_VARIANT}"
    key = variant
    if key not in _cache:
        folder = language.lower()  # en or pt
        filename = f"{variant}.txt"
        path = Path(__file__).parent.parent / "prompt" / folder / filename
        _cache[key] = path.read_text()

    template = _cache[key]
    belief = str(user_belief_level) if user_belief_level is not None else _BELIEF_UNKNOWN
    return (template.replace(BELIEF_PLACEHOLDER, belief)
            .replace(RATING_MIN_PLACEHOLDER, str(settings.TRUST_RATING_MIN))
            .replace(RATING_MAX_PLACEHOLDER, str(settings.TRUST_RATING_MAX)))


def assign_variant() -> str:
    """Randomly assign a variant for A/B testing."""
    return random.choice(VARIANTS)
