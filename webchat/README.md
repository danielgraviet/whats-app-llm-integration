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

1. Intro text with the study sponsor, ethics approval and consent language ("Antes de começar, preciso que você responda algumas perguntas rápidas.").
2. **Eligibility screening**, one question at a time with buttons: "Você tem 18 anos ou mais?" (Sim / Não), then "Você está apto(a) a votar nas eleições brasileiras?" (Sim / Não / Não sei). Only Sim + Sim proceeds. Any other answer shows the closing message ("Obrigado pelo interesse! Para participar desta pesquisa, é necessário ter 18 anos ou mais e estar apto(a) a votar…") and ends the session: no baseline question, no conversation. Text typed while a question is open re-shows the buttons. Each answer is stored the moment it is given, so a participant who answers the first question and leaves is still recorded. `SCREENING_ENABLED=false` skips this step.
3. The **baseline question** with a **0% to 100% slider**: "O quanto você confia que as urnas eletrônicas brasileiras registram e contam corretamente cada voto?", labelled "0% = Não confio nem um pouco" and "100% = Confio totalmente". The slider starts in the middle, greyed out; nothing is recorded until the participant moves it and taps "Avaliar agora". Ordinary text is refused with a note until the rating is given.
4. The LLM conversation under one of the five randomly assigned prompt conditions (prompts v5, 4 Oct 2026).
5. After every `TRUST_CHECK_INTERVAL` (6) user messages, the attitude-change question ("Antes de continuar a conversa, responda mais uma pergunta rápida…") with the same slider. The second rating is the **post** measurement; the first is **pre**. Both are stored as plain fields (`rating_pre`, `rating_post`) on the document; every rating also stays in `feeling_array`.
6. After the rating at turn `DEBRIEF_AFTER_TURNS` (6), the debriefing text with the TSE links, worded to say the participant may keep talking. The conversation then simply continues, with the slider again every 6 turns (12, 18, ...). Nothing ends it except closing the page.

**Control condition (`A_control_condition`)** is a two-stage conversation. After the pre rating the fixed opener is sent ("Vamos conversar sobre as eleições brasileiras. Antes, para começar com um assunto mais leve, queria saber: o que você acha do cachorro caramelo…"), and the assistant talks only about the cachorro caramelo (its own prompt, no election content) for 6 turns; the post rating follows; then the fixed transition ("Agora vamos mudar de assunto e falar sobre as eleições…") and a neutral, question-only conversation about the electronic voting machines under a second prompt (`A2_control_elections`). The researchers' prompt A describes both halves in one text with "for the first six turns"; it is split in two files because the code counts the turns (the model only sees the last five), which makes the switch exact. Its debrief comes after the rating at turn 12, so every condition sees the debrief after six election turns. Pre and post are therefore comparable across all five conditions.

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
- `screening`: `age_18` and `eligible_voter` (`sim` / `nao` / `nao_sei`) with a timestamp each, `passed`, `completed_at`; `screened_out_at` on failure. Phases `awaiting_screening` (opened the page, not done) and `screened_out` (failed) exist alongside the usual ones, so **every visitor has a document** from the moment the page opens, qualified or not
- `page_loads`, `last_seen_at` and a `visits` list (one entry per page open/resume with that visit's page metadata)
- `first_message_raw.referral`: built from the ad URL. `source_id` = `utm_content` (fall back `ad_id`, `utm_campaign`), `ctwa_clid` = `fbclid`, plus every `utm_*` / `fbclid` / `gclid` / `ad_id` / `adset_id` / `campaign_id` parameter under `params`
- `first_message_raw.web`: full query string, referrer, user agent, browser language(s), Accept-Language, screen and viewport size, colour depth, timezone, platform, touch support, cookies enabled, connection type, device memory and CPU count where the browser exposes them, User-Agent client hints, page URL, the client's clock at page open, client-hint and proxy request headers, and a salted hash of the IP (never the IP itself)

**Ad setup:** give every ad a distinct `utm_content` (e.g. `ad_17`) in its destination URL. Facebook adds `fbclid` on its own. There is no server-side click attribution on the web like WhatsApp's referral object, so the URL parameters are the only attribution.

## Meta Pixel

The page carries the study's Meta Pixel (dataset) so the Facebook campaigns can
be optimised and measured per creative (brief: *Meta Pixel Implementation
Brief*, Oct 2026). Three events, names exactly as in the brief (case-sensitive,
Portuguese by design):

| Event | Type | Fires when | Guard |
|---|---|---|---|
| `PageView` | standard | every page load (the base code is in `<head>`) | none, by design |
| `ConversaIniciada` | custom | the participant submits their **first text message** of the session (after screening and the pre rating; `/` developer commands do not count) | once per session |
| `PesquisaConcluida` | custom | the **post rating** is stored (`rating_post`, the second slider, turn 6 in every condition), i.e. the session has become a research-usable pre/post pair | once per session |

Both custom events carry one parameter, `criativo`, with the ad's
`utm_content` (the four creatives: `skeptical_frame`, `open_question`,
`voice_matters`, `curiosity_frame`). Nothing else is ever sent to Meta: no
session id, no answers, no ratings, no text. The server returns the creative
of the *first* visit with the session state (`creative`), so a participant who
resumes later from a URL without parameters is still attributed correctly.

"Once per session" means once per study session: the guard is stored in
`localStorage` under `fb_<event>_<session id>` (the session id itself lives
there), so a reload, back navigation, a closed tab or a later visit never
repeats an event. `?new=1` or `/reset` creates a new session and the events
fire again for it. The page also knows the server state (`completed`, number of
user turns in the history), so a cleared browser cannot re-fire
`ConversaIniciada` for a conversation that already has messages.

The pixel id is `META_PIXEL_ID` in `webchat/.env` (default: the study's pixel
`1276196112839237`; `--demo` defaults to none). Set it empty to serve the page
without the pixel, e.g. on a staging host. `/health` reports `meta_pixel:
true|false`. The base code is injected into `index.html` at the
`<!--META_PIXEL-->` placeholder when the page is served. If a browser blocks
`fbevents.js` (ad blocker), Meta's own queue stub swallows the calls and the
page works unchanged; if there is no pixel at all, `fbq` is undefined and the
events are skipped.

**Consent.** The base code fires `PageView` on load, before the participant
reads the intro and consent text, exactly as the brief's base code does. If
the IRB protocol requires the pixel to run only after consent, move the
`<!--META_PIXEL-->` injection to after the first screening answer instead; the
custom events already fire after consent by construction.

To verify in production: Meta Events Manager > Test events, or the Meta Pixel
Helper browser extension, with a `?utm_content=...` URL; go through screening,
the slider, one message (ConversaIniciada), six messages and the second slider
(PesquisaConcluida). `e2e/test_webchat_pixel_browser.py` does the same walk in
headless Chrome against a demo server (needs `pip install playwright` and
Chrome; skipped otherwise).

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
