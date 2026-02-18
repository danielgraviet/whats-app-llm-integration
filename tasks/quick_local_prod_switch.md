# Quick Local / Prod Switch Guide

## URLs
- **Railway (prod):** `whats-app-llm-integration-production.up.railway.app`
- **ngrok (local dev):** `https://courtney-pisciform-subterraneously.ngrok-free.dev/`

---

## Local Dev Credentials (phone ending in 5414)

- **Access token:** EAAbZBceSgmZB0BQ53opNG4AHWohhI14PL7xdZCm4b6fxZBq0e7IZA7ntv8R46Ii0pSC18uVoDUAuhk5On09nL7c3HFZCf2r0YjDWwW6g81t6KvzMMqvt01IoUcikJ5x92SMAFZC9HukiKWjkqU2NGKVKR9vHOkQsKWXR17fcNta6MbndNBaXO98bX5gvd5C3TSG04nrGVuFMwlpBnG256LzXBaooBtMg5s3VW9B2UMQEHrUuZCbjoI2arrfhAHr6cql2VPa53ayu4PrhDQfvHRhv
- **Phone number ID:** 968417933021257
- **WA Business Account ID:** 1603359010703261
- **Verify token:** localtesting
- **Env file:** `.env.local` (loaded when `APP_ENV=local`)

## Production Credentials (phone ending in 4260)
- **Env file:** set via Railway environment variables
- **Flow:** "Survey V4" under "Maple Mountain Consulting V4" in WA Business Manager

---

## Architecture Notes

Both the dev and prod Meta Apps are subscribed to the **same WABA** (WhatsApp Business Account). This means Meta sends webhook events to **both** servers whenever either number receives a message.

### How coupling is prevented (main.py)
Each server filters incoming webhooks by comparing the `phone_number_id` in the webhook metadata against its own `PHONE_NUMBER_ID` env var. If they don't match, the message is ignored.

```python
# In handle_webhook(), inside the entry/change loop:
metadata = value.get("metadata", {})
incoming_phone_id = str(metadata.get("phone_number_id", ""))
if value and "messages" in value and incoming_phone_id == str(settings.PHONE_NUMBER_ID):
    messages_to_process.extend(value["messages"])
```

- Local server: only processes messages where `phone_number_id` == dev number ID
- Railway server: only processes messages where `phone_number_id` == prod number ID

### Testing checklist when switching environments
- [ ] Confirm correct `.env.{local|prod}` is loaded (`APP_ENV` env var)
- [ ] Confirm ngrok is running and dev Meta App webhook URL is up to date
- [ ] Confirm Railway has the latest code deployed before prod testing