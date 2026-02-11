# Python WhatsApp Chatbot

A WhatsApp Business API chatbot built with FastAPI and Firebase Firestore. This project is a research tool for studying trust in electronic voting machines — it conducts LLM-powered conversations and periodically collects trust ratings via WhatsApp's native interactive list UI.

## Architecture Overview

```
WhatsApp User
      │
      ▼
Meta WhatsApp Business API ──webhook──► FastAPI Server (POST /)
                                              │
                                      ┌───────┴────────┐
                                      │ msg_type="text" │ msg_type="interactive"
                                      ▼                 ▼
                              Background Task Processor
                                      │
                                      ▼
                              Conversation Service
                                      │
                          ┌───────────┼───────────┐
                          ▼           ▼           ▼
                    OpenAI LLM   Firestore   Trust Service
                          │                       │
                          ▼                       ▼
                    BotResponse (text_messages + optional interactive list)
                          │
                          ▼
Meta WhatsApp Business API ◄── send_message_to_whatsapp()
                               send_interactive_list_to_whatsapp()
      │
      ▼
WhatsApp User
```

### Components

| Component | File | Description |
|-----------|------|-------------|
| **FastAPI App** | `main.py` | Webhook endpoints, message routing, WhatsApp API client (text + interactive lists) |
| **Conversation Service** | `services/conversation_service.py` | Message routing, phase management, `BotResponse` dataclass |
| **Trust Service** | `services/trust_service.py` | Rating prompts (EN/PT), interactive list reply parsing, check-in trigger logic |
| **Prompt Service** | `services/prompt_service.py` | A/B test variant assignment and system prompt loading |
| **Firebase Integration** | `database/firebase.py` | Firestore client, message persistence, conversation retrieval |
| **Data Models** | `database/models.py` | Pydantic models for `Message`, `Conversation`, `TrustRating` |
| **OpenAI Client** | `integrations/openai_client.py` | LLM API calls |
| **Config** | `config.py` | Centralized settings from environment variables |

## Trust Rating System

The chatbot collects trust ratings at two points:

1. **Initial rating** — Before the conversation begins, the user receives a WhatsApp interactive list asking them to rate their trust (1-10).
2. **Periodic check-ins** — Every N turns (configured via `TRUST_CHECK_INTERVAL`), the user's message is processed by the LLM normally, then an interactive list is sent as a follow-up.

### Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Rating UI | WhatsApp interactive lists | Native UI feels natural, no text parsing needed, structured data |
| Scale | 1-10 | Matches the research instrument's granularity |
| Check-in delivery | Send AI response first, then list | No context is lost — user's message always reaches the LLM |
| Blocking behavior | Conversation blocked until rating received | Ensures data collection completeness for the study |
| After initial rating | "Thank you for sharing. What were you about to ask?" | User hasn't said anything yet, so prompt them to start |
| After check-in rating | No message (silent acknowledgment) | Less intrusive — conversation resumes naturally on next user message |
| Return type | `BotResponse` dataclass | Separation of concerns — conversation service decides *what* to send, `main.py` decides *how* to format it for WhatsApp |

### Conversation Phases

```
awaiting_initial_rating ──(user selects rating)──► normal
                                                     │
                                              (every N turns)
                                                     │
                                                     ▼
                                          awaiting_check_in_rating
                                                     │
                                              (user selects rating)
                                                     │
                                                     ▼
                                                   normal
```

### Interactive List Payload

When a rating is requested, the bot sends a WhatsApp interactive list message:

```json
{
  "messaging_product": "whatsapp",
  "to": "PHONE_NUMBER",
  "type": "interactive",
  "interactive": {
    "type": "list",
    "body": { "text": "Trust rating prompt text..." },
    "action": {
      "button": "Select Rating",
      "sections": [{
        "rows": [
          {"id": "rating_10", "title": "10 - Complete trust"},
          {"id": "rating_9", "title": "9"},
          ...
          {"id": "rating_1", "title": "1 - No trust"}
        ]
      }]
    }
  }
}
```

When the user selects a rating, WhatsApp sends back:

```json
{
  "type": "interactive",
  "interactive": {
    "type": "list_reply",
    "list_reply": { "id": "rating_7", "title": "7" }
  }
}
```

The `id` is parsed by `parse_interactive_rating()` — splitting on `_` and extracting the integer.

## Project Structure

```
python-whatsapp/
├── main.py                     # FastAPI app, webhook handlers, WhatsApp API senders
├── config.py                   # Centralized settings from .env
├── database/
│   ├── firebase.py             # Firestore CRUD operations
│   └── models.py               # Pydantic data models
├── services/
│   ├── conversation_service.py # Message routing, BotResponse, phase management
│   ├── trust_service.py        # Rating prompts, parsing, check-in logic
│   └── prompt_service.py       # A/B variant assignment, system prompts
├── integrations/
│   └── openai_client.py        # OpenAI API calls
├── .env                        # Environment variables (not in repo)
├── <firebase-credentials>.json # Firebase service account (not in repo)
└── .venv/                      # Python virtual environment
```

## Environment Setup

### Prerequisites

- Python 3.10+
- Meta WhatsApp Business Account
- Firebase project with Firestore enabled
- OpenAI API key

### 1. Clone and Install Dependencies

```bash
git clone <repository-url>
cd python-whatsapp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install fastapi uvicorn httpx pydantic firebase-admin google-cloud-firestore python-dotenv openai
```

### 2. Firebase Configuration

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Create a new project or select existing one
3. Enable **Cloud Firestore** in Database section
4. Go to **Project Settings > Service Accounts**
5. Click **Generate New Private Key** and save the JSON file to the project root

### 3. WhatsApp Business API Setup

1. Go to [Meta for Developers](https://developers.facebook.com/)
2. Create an app with **WhatsApp Business** product
3. In WhatsApp > API Setup, note down:
   - **Phone Number ID**
   - **WhatsApp Business Account ID**
   - **Temporary Access Token** (or generate a permanent one)

### 4. Environment Variables

Create a `.env` file in the project root:

```env
FIREBASE_CREDS_PATH="your-firebase-credentials.json"
PHONE_NUMBER_ID=your_phone_number_id
WHATSAPP_BUSINESS_ACC_ID=your_business_account_id
ACCESS_TOKEN="your_meta_access_token"
OPENAI_API_KEY="your_openai_api_key"
TRUST_CHECK_INTERVAL=3
```

### 5. Configure Webhook

1. Start your server (see [Running Locally](#running-locally))
2. Expose it via ngrok or deploy to a public URL
3. In Meta Developer Console > WhatsApp > Configuration:
   - Set **Callback URL** to `https://your-domain.com/`
   - Set **Verify Token** to match `_VERIFICATION_TOKEN` in `main.py`
   - Subscribe to **messages** webhook field

## Dev Commands

Send these as WhatsApp messages to trigger dev actions:

| Command | Action |
|---------|--------|
| `/info` | Returns current variant, phase, turn count, ratings, and system prompt |
| `/reset` | Deletes user conversation data from Firestore |

## API Endpoints

### `GET /` - Webhook Verification

Meta uses this endpoint to verify your webhook during setup.

| Parameter | Description |
|-----------|-------------|
| `hub.mode` | Should be `subscribe` |
| `hub.verify_token` | Must match your `_VERIFICATION_TOKEN` |
| `hub.challenge` | Challenge string to return |

### `POST /` - Receive Messages

Receives incoming WhatsApp messages (text and interactive replies) from Meta's webhook. Handles both `type: "text"` and `type: "interactive"` messages.

**Response:** `{"status": "accepted"}`

### `GET /health` - Health Check

**Response:** `{"status": "healthy"}`

## Data Models

### Conversation

```python
{
    "phone_number": "+1234567890",
    "last_message": "Latest message text",
    "history": [Message, ...],
    "updated_at": "2024-01-01T12:00:00Z",
    "language": "EN",
    "prompt_variant": "EN_prompt_A_control_condition",
    "conversation_phase": "normal",
    "feeling_array": [TrustRating, ...],
    "user_turn_count": 5,
    "intro_sent": true
}
```

### TrustRating

```python
{
    "score": 7,
    "timestamp": "2024-01-01T12:00:00Z",
    "message_index": 3
}
```

## Running Locally

```bash
source .venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Expose with ngrok (for webhook testing)

```bash
ngrok http 8000
```

Use the generated HTTPS URL as your webhook callback URL in Meta's dashboard.

## Deployment Guide

### Option 1: Railway / Render / Fly.io

1. Push code to GitHub
2. Connect repository to your platform
3. Set environment variables in dashboard
4. Deploy

**Example Procfile:**
```
web: uvicorn main:app --host 0.0.0.0 --port $PORT
```

### Option 2: Google Cloud Run

```bash
gcloud run deploy whatsapp-bot \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "FIREBASE_CREDS_PATH=credentials.json,PHONE_NUMBER_ID=xxx,ACCESS_TOKEN=xxx"
```

### Option 3: Docker

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY . .

RUN pip install --no-cache-dir fastapi uvicorn httpx pydantic firebase-admin google-cloud-firestore python-dotenv openai

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
docker build -t whatsapp-bot .
docker run -p 8000:8000 --env-file .env whatsapp-bot
```

### Production Considerations

- Use a permanent Meta access token (system user token)
- Move `_VERIFICATION_TOKEN` to environment variables
- Add proper logging (replace `print()` statements)
- Implement rate limiting
- Add error monitoring (Sentry, etc.)

## Current Status

| Feature | Status |
|---------|--------|
| Webhook verification | Implemented |
| Message reception (text + interactive) | Implemented |
| Firebase storage | Implemented |
| Conversation history | Implemented |
| Send text messages | Implemented |
| Send interactive lists | Implemented |
| LLM integration (OpenAI) | Implemented |
| Trust rating collection | Implemented |
| A/B test variant assignment | Implemented |
| Multi-language support (EN/PT) | Implemented |
| Dev commands (/info, /reset) | Implemented |

## License

MIT
