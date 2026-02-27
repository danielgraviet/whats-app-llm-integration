# Phase 2: Whisper Speech-to-Text Integration

## How WhatsApp Audio Works

When a user sends a voice note, the webhook payload looks like this instead of `"text"`:

```json
{
  "type": "audio",
  "audio": {
    "id": "SOME_MEDIA_ID",
    "mime_type": "audio/ogg; codecs=opus"
  }
}
```

Getting the actual audio requires **two** Meta API calls:

```
1. GET graph.facebook.com/v22.0/{media_id}  →  returns { url: "https://..." }
2. GET that URL (with auth header)           →  returns raw audio bytes
```

Then those bytes go to Whisper, which returns a transcript string. After that, your existing conversation flow is **completely unchanged** — it just sees text.

---

## What Changes, and Where

| File | Change |
|---|---|
| `main.py` | 1. Detect `msg_type == "audio"` in webhook, queue background task with `media_id` <br> 2. Add `download_whatsapp_audio(media_id)` helper <br> 3. In `process_whatsapp_ai`, if audio: download → transcribe → then proceed as normal |
| `integrations/openai_client.py` | Add `transcribe_audio(audio_bytes)` — reuses the existing `client` |
| `conversation_service.py` | **No changes** — receives transcript as plain text |
| `config.py` | **No changes** — `ACCESS_TOKEN` already there |

---

## The Flow After the Change

```
voice note arrives
       ↓
webhook extracts media_id, queues background task
       ↓
process_whatsapp_ai sees msg_type == "audio"
       ↓
download_whatsapp_audio(media_id) → raw bytes
       ↓
transcribe_audio(bytes) → "Hello, how are you?"
       ↓
handle_incoming_message(..., "Hello, how are you?", "audio")
       ↓
[everything else identical to text]
```

---

## Decisions Made

- **Transcription service**: OpenAI Whisper (`whisper-1`) — reuses existing OpenAI client/token
- **Direction**: One-way only — user voice → bot text (no TTS output)
- **Audio source**: WhatsApp voice notes only
- **Latency target**: Best effort, not a hard constraint at this stage
- **Scale target**: 1,000 concurrent users (real near-term goal)

---

## Status: Implemented and committed

### What was built
- `download_whatsapp_audio(media_id)` added to `main.py` — two sequential Meta API calls to retrieve raw audio bytes
- `transcribe_audio(audio_bytes)` added to `integrations/openai_client.py` — passes bytes to Whisper via the existing `AsyncOpenAI` client
- Webhook handler in `main.py` extended with an `elif` branch for `msg_type == "audio"` — extracts `media_id` and queues background task
- `process_whatsapp_ai` intercepts audio before conversation service, downloads and transcribes, then continues as normal text
- `_WA_HEADERS` module-level variable added to `main.py` to consolidate the repeated `Authorization` header across all three Meta API functions

### Test coverage
- `e2e/test_whisper.py` — reads a real `.ogg` file and calls `transcribe_audio()` against the live Whisper API. Test passed.

### Next step
- Deploy to Railway and send a real WhatsApp voice note to confirm the full end-to-end flow in production
