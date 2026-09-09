from datetime import datetime, timezone
from typing import Any, Dict, List

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
    language: str = "PT"
    prompt_variant: str = "PT_prompt_A_control_condition"

    # metrics for tracking feelings
    conversation_phase: str = "awaiting_initial_rating"
    feeling_array: List[TrustRating] = []
    user_turn_count: int = 0
    intro_sent: bool = False
    pending_ai_response: str = ""

    # Raw webhook metadata for research attribution. All fields are stored
    # exactly as Meta sent them; nothing is filtered or renamed.
    # first_message_raw: the complete message dict from the participant's very
    #   first message (this is the one that carries the ad "referral" object).
    # first_contacts_raw: the sibling "contacts" array (profile name, wa_id).
    # referrals: every "referral" object ever received from this number, each
    #   tagged with the Meta message id and timestamp it arrived on. Lets a
    #   second ad click be recorded without overwriting the first touch.
    first_message_raw: Dict[str, Any] = {}
    first_contacts_raw: List[Dict[str, Any]] = []
    referrals: List[Dict[str, Any]] = []

    def to_firestore(self) -> dict:
        """Converts the model to a dict, ensuring datetimes are handled."""
        return self.model_dump()
