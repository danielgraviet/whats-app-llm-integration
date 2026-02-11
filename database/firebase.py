import datetime as dt
import os

from google.cloud import firestore
from google.oauth2 import service_account

from . import models


def init_firestore():
    """Initializes the Firestore client using service account credentials."""
    credential_path = os.getenv("FIREBASE_CREDS_PATH")

    try:
        credentials = service_account.Credentials.from_service_account_file(
            credential_path
        )
        client = firestore.Client(project="whatsapp-llm-test", credentials=credentials)
        return client
    except Exception as e:
        print(f"Failed to create firestore client: {e}")
        raise


def save_message(
    client, phone_number: str, message_text: str, role: str = "user"
) -> bool:
    """Saves a message to the 'conversations' collection.

    Args:
        client: Firestore client
        phone_number: User's phone number (document ID)
        message_text: The message content
        role: Either "user" or "assistant"
    """
    try:
        doc_ref = client.collection("conversations").document(phone_number)

        new_message = models.Message(role=role, content=message_text)

        doc_ref.set(
            {
                "last_message": message_text,
                "updated_at": dt.datetime.now(),
                "history": firestore.ArrayUnion([new_message.model_dump()]),
            },
            merge=True,
        )

        return True
    except Exception as e:
        print(f"Error saving message: {e}")
        return False


def save_user_message(client, phone_number: str, message_text: str) -> bool:
    """Saves a user message. Wrapper for backwards compatibility."""
    return save_message(client, phone_number, message_text, role="user")


def get_or_create_conversation(
    client, phone_number: str, language: str, variant: str
) -> models.Conversation:
    # check the database for existing conversation
    # if exists return convo.
    doc_ref = client.collection("conversations").document(phone_number)
    doc = doc_ref.get()

    if doc.exists:
        print("Returning existing conversation!")
        data = doc.to_dict()
        data["phone_number"] = phone_number
        convo = models.Conversation(**data)
        return convo
    else:
        print("Creating new conversation! assigning variant...")
        convo = models.Conversation(
            phone_number=phone_number,
            last_message="",
            language=language,
            prompt_variant=variant,
            history=[],
        )
        doc_ref.set(convo.to_firestore())
        return convo


def save_trust_rating(
    client, phone_number: str, score: int, message_index: int
) -> bool:
    """Appends a trust rating to the feeling_array in Firestore."""
    try:
        doc_ref = client.collection("conversations").document(phone_number)
        rating = models.TrustRating(score=score, message_index=message_index)
        doc_ref.set(
            {
                "feeling_array": firestore.ArrayUnion([rating.model_dump()]),
                "updated_at": dt.datetime.now(),
            },
            merge=True,
        )
        return True
    except Exception as e:
        print(f"Error saving trust rating: {e}")
        return False


def update_conversation_phase(
    client, phone_number: str, phase: str, user_turn_count: int = None
) -> bool:
    """Updates the conversation phase and optionally the turn count."""
    try:
        doc_ref = client.collection("conversations").document(phone_number)
        update_data = {
            "conversation_phase": phase,
            "updated_at": dt.datetime.now(),
        }
        if user_turn_count is not None:
            update_data["user_turn_count"] = user_turn_count
        doc_ref.update(update_data)
        return True
    except Exception as e:
        print(f"Error updating conversation phase: {e}")
        return False


def update_intro_sent(client, phone_number: str) -> bool:
    """Marks the intro as sent for this conversation."""
    try:
        doc_ref = client.collection("conversations").document(phone_number)
        doc_ref.update({"intro_sent": True, "updated_at": dt.datetime.now()})
        return True
    except Exception as e:
        print(f"Error updating intro_sent: {e}")
        return False


def delete_conversation(client, phone_number: str) -> bool:
    try:
        client.collection("conversations").document(phone_number).delete()
        return True
    except Exception as e:
        print(f"Error deleting conversation: {e}")
        return False
