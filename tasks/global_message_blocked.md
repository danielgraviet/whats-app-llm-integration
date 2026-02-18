# Brazilian Users Not Receiving Replies

## Problem
Users in Brazil can message the chatbot (WhatsApp accepts it) but receive no reply.
US users in multiple states work fine. App is in Live mode.

## Status: Waiting on logs

A Brazilian user needs to send a test message while Railway logs are being watched.
Look for a line like:
```
ERROR ... WhatsApp API error 400: {...}
```
The error code in that response will tell us the root cause.

## What We've Done So Far

### 1. Fixed Railway logging (merged to main)
Logs were being written to `testing.log` (a file inside Railway's container) instead of stdout.
Railway only captures stdout/stderr, so all WhatsApp API errors were silently disappearing.

**Fix:** Added a `StreamHandler` to `logging.basicConfig` in `main.py` so logs now go to both
the local file and stdout (visible in Railway dashboard).

### 2. Ruled out code-level filtering
The code passes the `from` phone number directly to the WhatsApp reply API with no
transformation or filtering. Brazilian numbers (+55) are not being blocked by the app.

## Likely Causes (not yet confirmed)

| Cause | How to confirm | Fix |
|---|---|---|
| Brazil 9-digit number normalization | Error code `131026` in logs | Try both 12 and 13 digit formats on reply |
| US number restricted from international sending | Error code `131026` or `131047` in logs | May require a non-US business number |
| Business not verified with Meta | Check Business Manager → Business Info | Complete Meta business verification |
| Phone number quality rating is low | Check WA Business Manager → Phone Numbers | Improve quality rating |
| `whatsapp_business_messaging` permission not approved for Live mode | Check App → App Review | Submit permission for review |

## Things Already Checked
- App is in Live mode
- No messaging tier limit reached
- Production number is a US number (American flag shown in WA Business Manager)
- No international messaging toggle exists in WA Business Manager for this number