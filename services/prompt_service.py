import random
from pathlib import Path

VARIANTS = [
    "A_control_condition",
    "B_motivational_learning",
    "C_perspective",
    "D_christmas_dinner",
    "E_critical_thinking",
]

LANGUAGES = ["EN", "PT"]

_cache: dict[str, str] = {}

# Every prompt file contains this literal token where the participant's initial
# trust rating (1-10) should appear. It is substituted at request time.
BELIEF_PLACEHOLDER = "**user_belief_level**"
_BELIEF_UNKNOWN = "not provided"


def get_prompt(
    language: str, variant: str, user_belief_level: int | None = None
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
    key = variant
    if key not in _cache:
        folder = language.lower()  # en or pt
        filename = f"{variant}.txt"
        path = Path(__file__).parent.parent / "prompt" / folder / filename
        _cache[key] = path.read_text()

    template = _cache[key]
    belief = str(user_belief_level) if user_belief_level is not None else _BELIEF_UNKNOWN
    return template.replace(BELIEF_PLACEHOLDER, belief)


def assign_variant() -> str:
    """Randomly assign a variant for A/B testing."""
    return random.choice(VARIANTS)
