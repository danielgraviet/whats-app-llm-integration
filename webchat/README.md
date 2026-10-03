# Web version of the study conversation

A browser-based replacement for the WhatsApp bot, built for the case where
the WhatsApp number is unavailable. It reuses the WhatsApp deployment's
conversation logic, prompts, texts, and Firestore document format unchanged,
so every downstream tool (Grafana dashboard, conversation browser, CSV export,
purge script) works on the new data with one environment variable.

```
Facebook ad ─► https://pccgo.cs.byu.edu/pesquisa/?utm_campaign=…&utm_content=ad_17
                      │ nginx (TLS, already in place)
                      ▼
               webchat/app.py  (127.0.0.1:8100)
                      │  services/conversation_service.py  ← same code as WhatsApp
                      ├─► OpenAI (same key, same prompts in prompt/pt/)
                      └─► Firestore collection  web_conversations   ← separate from "conversations"
```

## What the participant sees

Portuguese only, phone-first layout in the WhatsApp visual style:

1. Intro text with the study sponsor, ethics approval and consent language, then a **0 to 100 trust-rating slider**. The slider starts in the middle, greyed out; nothing is recorded until the participant moves it and taps "Avaliar agora". Ordinary text is refused with a note until the rating is given.
2. The LLM conversation under one of the five randomly assigned prompt conditions.
3. After every `TRUST_CHECK_INTERVAL` (6) user messages, the same slider again. The second rating is the **post** measurement; the first is **pre**. Both are stored as plain fields (`rating_pre`, `rating_post`) on the document; every rating also stays in `feeling_array`.
4. After the rating at turn `DEBRIEF_AFTER_TURNS` (6), the debriefing text with the TSE links, worded to say the participant may keep talking. The conversation then simply continues, with the slider again every 6 turns (12, 18, ...). Nothing ends it except closing the page.

**Control condition (`A_control_condition`)** is a two-stage conversation: after the pre rating the assistant says it will talk about elections later and first chats about cats and dogs (its own prompt, no election content) for 6 turns; the post rating follows; then "Agora vamos falar sobre eleições" and a neutral conversation about elections in general under a second prompt (`A2_control_elections`). Its debrief comes after the rating at turn 12, so every condition sees the debrief after six election turns. Pre and post are therefore comparable across all five conditions.

Every message and rating is written to Firestore as it happens, so a participant who leaves mid-way still contributes a partial record. Reloading the page resumes the same session (id kept in the browser's localStorage).

The WhatsApp developer commands work the same way here, typed as messages:
`/info` shows the condition, phase, turn count, pre/post ratings and system prompt;
`/reset` deletes the session from Firestore and reloads the page as a brand
new participant (new session id, fresh random condition); `/lang en` or
`/lang pt` switches the prompt language. `?new=1` on the URL also starts a
fresh session.

These are the web deployment's defaults, set in `webchat/app.py` and
overridable in `webchat/.env`: `TRUST_RATING_MIN=0`, `TRUST_RATING_MAX=100`,
`TRUST_CHECK_INTERVAL=6`, `DEBRIEF_AFTER_TURNS=6`, `CONTINUE_AFTER_DEBRIEF=true`.
The WhatsApp app keeps its own defaults (1-10, debrief ends the conversation).

## What is recorded

Same document shape as WhatsApp, in collection `web_conversations`, keyed by a random session id (`web_…`) instead of a phone number:

- history, phase, variant, turn count, ratings, debriefed_at (identical fields), plus `rating_pre` and `rating_post`
- `first_message_raw.referral`: built from the ad URL. `source_id` = `utm_content` (fall back `ad_id`, `utm_campaign`), `ctwa_clid` = `fbclid`, plus every `utm_*` / `fbclid` / `gclid` / `ad_id` / `adset_id` / `campaign_id` parameter under `params`
- `first_message_raw.web`: full query string, referrer, user agent, browser language, Accept-Language, screen size, timezone, page URL, and a salted hash of the IP (never the IP itself)

**Ad setup:** give every ad a distinct `utm_content` (e.g. `ad_17`) in its destination URL. Facebook adds `fbclid` on its own. There is no server-side click attribution on the web like WhatsApp's referral object, so the URL parameters are the only attribution.

## Install on pccgo.cs.byu.edu

Requires **Python 3.10 or newer** (the code uses `X | None` annotations and
the OpenAI SDK's `jiter` dependency has no wheels for older interpreters). If
`python3 --version` on the server is older, do not fight the system Python:
let `uv` fetch a private one into the venv (no root needed).

```bash
# 1. code + venv
sudo git clone https://github.com/danielgraviet/whats-app-llm-integration.git /opt/whats-app-llm-integration
cd /opt/whats-app-llm-integration

# 1a. system Python is 3.10+:
python3 -m venv .venv && .venv/bin/pip install -r webchat/requirements.txt

# 1b. system Python is older (e.g. Ubuntu 20.04/22.04):
curl -LsSf https://astral.sh/uv/install.sh | sh && export PATH="$HOME/.local/bin:$PATH"
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -r webchat/requirements.txt
.venv/bin/python --version      # 3.12.x

# 2. secrets: copy the template and fill in Firebase creds + OpenAI key (same values Railway has)
sudo cp webchat/.env.schema webchat/.env && sudo nano webchat/.env
chmod 600 webchat/.env

# 3. service: set the user and paths to match your checkout (the template assumes
#    /opt/... owned by www-data; a wrong User shows as "status=217/USER")
sudo cp webchat/deploy/webchat.service /etc/systemd/system/
sudo sed -i "s/^User=.*/User=$USER/; s#/opt/whats-app-llm-integration#$PWD#g" /etc/systemd/system/webchat.service
sudo systemctl daemon-reload && sudo systemctl enable --now webchat
journalctl -u webchat -n 20 --no-pager        # startup log: env files loaded, collection, any missing key
curl -s http://127.0.0.1:8100/health          # {"status":"healthy",...,"collection":"web_conversations"}

# 4. nginx: paste webchat/deploy/nginx-pesquisa.conf into the pccgo server block
sudo nginx -t && sudo systemctl reload nginx
curl -s https://pccgo.cs.byu.edu/pesquisa/health
```

Updating later: `git pull`, then `sudo systemctl restart webchat`.

To try it without any credentials: `python webchat/app.py --demo --port 8100` and open http://127.0.0.1:8100/ (in-memory store, canned replies, nothing saved).

## Dashboard, browser and export for the web data

The Grafana stack gains a second database and dashboard ("Web Study"); see
`dashboard/README.md`, section "Second study (web)". The conversation browser
and the purge script take `FIRESTORE_COLLECTION=web_conversations` in their
own `.env` and otherwise work unchanged, CSV export included.

## Notes

- The LLM model is `OPENAI_MODEL` (default `gpt-5.5`, reasoning effort `OPENAI_REASONING_EFFORT`, default `low`), shared with the WhatsApp app through `integrations/openai_client.py`. WhatsApp conversations collected before 2026-10-01 ran on `gpt-4`.
- One turn per session is processed at a time; the page disables input while a reply is pending.
- `/health` reports `GIT_COMMIT_SHA` if the systemd unit sets it, so a deploy can be confirmed from outside.
