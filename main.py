import json
import logging

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request

import database.firebase as firebase_db
from config import settings
from services import conversation_service, trust_service

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="%(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler("testing.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)


app = FastAPI()

# Initialize Firestore client at startup
firestore_client = firebase_db.init_firestore()


async def process_whatsapp_ai(phone_number: str, message_text: str, msg_type: str):
    """Process incoming WhatsApp message and send AI response.

    Runs as a background task after the webhook response is sent.
    """
    try:
        # need to add msg type to function.
        bot_response = await conversation_service.handle_incoming_message(
            firestore_client, phone_number, message_text, msg_type
        )

        for text in bot_response.text_messages:
            await send_message_to_whatsapp(phone_number, text)

        if bot_response.send_trust_flow:
            body_text = trust_service.get_trust_prompt(
                language=bot_response.trust_flow_language,
                prompt_key=bot_response.trust_flow_prompt_key,
            )
            if settings.USE_FLOWS:
                await send_flow_to_whatsapp(phone_number, body_text)
            else:
                await send_message_to_whatsapp(phone_number, body_text)

    except Exception as e:
        print(f"[ERROR] process_whatsapp_ai failed: {e}")


async def send_message_to_whatsapp(to_phone: str, text: str):
    logging.debug("[DEBUG] Sending this message back to WhatsAPP: %s", text)
    url = f"https://graph.facebook.com/v22.0/{settings.PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": text},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(
                "WhatsApp API error %s: %s", response.status_code, response.text
            )
        else:
            logger.debug("WhatsApp API success: %s", response.text)


async def send_flow_to_whatsapp(to_phone: str, body_text: str):
    logging.debug("[DEBUG] FLOW being sent back to WhatsApp")
    url = f"https://graph.facebook.com/v22.0/{settings.PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {settings.ACCESS_TOKEN}"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": {
            "type": "flow",
            "body": {"text": body_text},
            "action": {
                "name": "flow",
                "parameters": {
                    "flow_message_version": "3",
                    "flow_id": settings.FLOW_ID,
                    "flow_cta": "Rate Now",
                    "flow_action": "navigate",
                    "flow_action_payload": {"screen": "QUESTION_ONE"},
                },
            },
        },
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code != 200:
            logger.error(
                "WhatsApp API error %s: %s", response.status_code, response.text
            )
        else:
            logger.debug("WhatsApp API success: %s", response.text)


@app.post("/")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks):
    """Receive incoming WhatsApp messages and queue for processing."""
    data = await request.json()

    try:
        messages_to_process = []

        # Handle full webhook payload (object -> entry -> changes -> value)
        if data.get("object") == "whatsapp_business_account":
            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    metadata = value.get("metadata", {})
                    incoming_phone_id = metadata.get("phone_number_id")
                    if value and "messages" in value and incoming_phone_id == settings.PHONE_NUMBER_ID:
                        messages_to_process.extend(value["messages"])

        # Handle direct value payload (field + value structure)
        elif data.get("field") == "messages" and "value" in data:
            value = data["value"]
            metadata = value.get("metadata", {})
            incoming_phone_id = str(metadata.get("phone_number_id", ""))
            if "messages" in value and incoming_phone_id == str(settings.PHONE_NUMBER_ID):
                messages_to_process.extend(value["messages"])

        # Process each text message
        for message in messages_to_process:
            sender = message.get("from")
            msg_type = message.get("type")

            if msg_type == "text" and "text" in message:
                text = message["text"]["body"]
                background_tasks.add_task(process_whatsapp_ai, sender, text, msg_type)
            elif msg_type == "interactive" and "interactive" in message:
                interactive = message["interactive"]
                logger.info("Interactive message received: %s", json.dumps(interactive))
                if interactive.get("type") == "nfm_reply":
                    response_json = json.loads(
                        interactive["nfm_reply"]["response_json"]
                    )
                    rating_value = response_json.get("confidence_rating", "")
                    reply_id = f"rating_{rating_value}"
                    background_tasks.add_task(
                        process_whatsapp_ai, sender, reply_id, msg_type
                    )

        return {"status": "accepted"}

    except Exception as e:
        print(f"[ERROR] Webhook parsing failed: {e}")
        return {"status": "error", "detail": str(e)}


@app.get("/")
def verify_whatsapp(
    hub_mode: str = Query(
        "subscribe", description="The mode of the webhook", alias="hub.mode"
    ),
    hub_challenge: int = Query(
        ..., description="The challenge to verify the webhook", alias="hub.challenge"
    ),
    hub_verify_token: str = Query(
        ..., description="The verification token", alias="hub.verify_token"
    ),
):
    if hub_mode == "subscribe" and hub_verify_token == settings.VERIFY_TOKEN:
        return hub_challenge
    raise HTTPException(status_code=403, detail="Invalid verification token")


@app.get("/health")
def health():
    return {"status": "healthy"}
