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


def get_prompt(language: str, variant: str) -> str:
    """Load prompt from file.

    Args:
        language: "EN" or "PT"
        variant: e.g. "EN_prompt_A_control_condition"

    Example: get_prompt("EN", "EN_prompt_A_control_condition")
    """
    key = variant
    if key not in _cache:
        folder = language.lower()  # en or pt
        filename = f"{variant}.txt"
        path = Path(__file__).parent.parent / "prompt" / folder / filename
        _cache[key] = path.read_text()

    return _cache[key]


def assign_variant() -> str:
    """Randomly assign a variant for A/B testing."""
    return random.choice(VARIANTS)
