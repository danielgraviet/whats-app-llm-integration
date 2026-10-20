from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pydantic


class TrustRating(pydantic.BaseModel):
    """One answer to the pair of trust questions (scale 1-7, see trust_service.RATING_OPTIONS).

    score is the voting-machine question ("urnas", question 2), the primary
    measure; score_system is question 1, trust in the electoral system as a
    whole. slot is "pre" (baseline), "post" (after the 6th message), "exit"
    (optional, when the participant ends early) or None (later check-ins).
    events are the participant's taps on the buttons, each with a timestamp.
    """
    score: int
    score_system: Optional[int] = None
    timestamp: datetime = pydantic.Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    message_index: int
    slot: Optional[str] = None
    events: List[Dict[str, Any]] = []


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
    # Study arm. Empty until the participant passes the baseline high-trust
    # filter, when one is drawn at random (prompt_service.assign_variant).
    prompt_variant: str = ""
    variant_assigned_at: Optional[datetime] = None

    # metrics for tracking feelings
    # phases: awaiting_screening -> awaiting_initial_rating -> normal <-> awaiting_check_in_rating -> ended
    #         awaiting_screening -> screened_out (terminal; failed eligibility)
    conversation_phase: str = "awaiting_initial_rating"
    debriefed_at: Optional[datetime] = None
    # Eligibility screening answers, written as each one arrives so a partial
    # screening is still recorded: {"age_18": "sim"|"nao", "age_18_at": ts,
    # "eligible_voter": "sim"|"nao"|"nao_sei", "eligible_voter_at": ts,
    # "passed": bool, "completed_at": ts}
    screening: Dict[str, Any] = {}
    screened_out_at: Optional[datetime] = None
    # "eligibility" (failed the screening) or "high_trust" (answered 7 to the
    # voting-machine question at the baseline; the rating is still stored).
    screened_out_reason: Optional[str] = None
    # Why the conversation ended: "limit" (rating at the 24th message), "button"
    # (Encerrar conversa; see `exit` for whether the optional exit rating was
    # answered) or "inactivity" (15 minutes without a message, page still open).
    ended_reason: Optional[str] = None
    exit: Dict[str, Any] = {}
    # Engagement metadata (web): how many times the page was opened/resumed,
    # when it was last opened, and the per-visit page metadata.
    page_loads: int = 0
    last_seen_at: Optional[datetime] = None
    visits: List[Dict[str, Any]] = []
    # The ratings the primary analysis uses: before the conversation (pre), after
    # the first TRUST_CHECK_INTERVAL turns (post) and, optionally, when the
    # participant ends early (exit). *_system is question 1 (electoral system as a
    # whole); the unsuffixed field is question 2 (voting machines). All ratings
    # stay in feeling_array.
    rating_pre: Optional[int] = None
    rating_post: Optional[int] = None
    rating_pre_system: Optional[int] = None
    rating_post_system: Optional[int] = None
    rating_exit: Optional[int] = None
    rating_exit_system: Optional[int] = None
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
