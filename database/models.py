from datetime import datetime, timezone
from typing import List

import pydantic


class TrustRating(pydantic.BaseModel):
    score: int  # 10 is they completely trust the voting machines.
    timestamp: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    message_index: int


class Message(pydantic.BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Conversation(pydantic.BaseModel):
    phone_number: str
    last_message: str
    history: List[Message] = []
    updated_at: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    language: str = "en"
    prompt_variant: str = "EN_prompt_A_control_condition"

    # metrics for tracking feelings
    conversation_phase: str = "awaiting_initial_rating"
    feeling_array: List[TrustRating] = []
    user_turn_count: int = 0
    intro_sent: bool = False
    pending_ai_response: str = ""

    def to_firestore(self) -> dict:
        """Converts the model to a dict, ensuring datetimes are handled."""
        return self.model_dump()
