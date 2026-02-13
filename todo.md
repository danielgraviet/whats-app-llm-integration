# WhatsApp Bot — Public Launch Checklist

## Phase 1: Phone Number Setup
- [ ] Wait for Google Voice verification to complete
- [ ] Confirm you can receive SMS or calls on the new Google Voice number

## Phase 2: Meta App Dashboard Configuration
- [ ] Go to Meta App Dashboard → WhatsApp → API Setup
- [ ] Click **Add Phone Number** and enter your Google Voice number
- [ ] Complete SMS/voice verification with the code Meta sends
- [ ] Set a **Display Name** for your WhatsApp Business profile (must follow Meta's naming guidelines)

## Phase 3: Business Verification
- [ ] Go to [business.facebook.com](https://business.facebook.com) → Settings → Business Info
- [ ] Click **Start Verification** and submit required documents
- [ ] Wait for approval (can take a few days to ~2 weeks)

## Phase 4: Permissions & Access
- [ ] In Meta App Dashboard → App Review → Permissions and Features
- [ ] Request **Advanced Access** for `whatsapp_business_messaging`
- [ ] Switch App Mode from **Development** to **Live**
- [ ] Add a valid **payment method** in Meta Business Suite (conversations are billed)

## Phase 5: Test It
- [ ] Text the new number from a phone that is NOT a registered tester
- [ ] Confirm the bot responds correctly
- [ ] Check your logs/Firestore to verify the message was processed

## Notes
- Your personal WhatsApp number stays untouched — the Google Voice number is the bot's number
- One phone number = one WhatsApp account (that's why you needed a second number)
- Meta's conversation-based pricing: first 1,000 service conversations/month are free
