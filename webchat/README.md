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

## What the participant sees (phase 2, 17 Oct 2026 design)

Portuguese only, phone-first layout in the WhatsApp visual style. The header
says only "Pesquisa acadêmica": it must not name the topic.

1. Intro text with the study sponsor, ethics approval and consent language (unchanged).
2. **Eligibility screening**, one question at a time with buttons: 18 or older (Sim / Não), eligible to vote (Sim / Não / Não sei). Only Sim + Sim proceeds; anything else shows the closing message ("Obrigado pela sua resposta! Nesta etapa, a pesquisa está conversando com um perfil específico de participantes…") and ends the session. Each answer is stored the moment it is given. `SCREENING_ENABLED=false` skips this step.
3. **Baseline trust questions** in a fixed panel over the chat, after the lead-in "Antes de começar, responda duas perguntas rápidas.": question 1 "O quanto você confia no sistema eleitoral brasileiro como um todo?" and question 2 "O quanto você confia que as urnas eletrônicas brasileiras registram e contam corretamente cada voto?", each answered with seven labelled buttons (1 Não confio nada … 7 Confio totalmente). A tap only highlights; "Confirmar: <label>" records the answer. Nothing is pre-selected, the text box is off until both are confirmed, and every tap is logged with a timestamp. The answers are echoed into the chat as words.
4. **High-trust filter**: a 7 on question 2 ends the session with the same closing message as the screening. The answers are kept (`screened_out_reason: high_trust`); no arm is drawn and no conversation starts.
5. **Random assignment**, only now, to one of three arms with equal probability: A control (cachorro caramelo for six messages, then question-only about the urnas), B motivational interviewing (facts only when directly asked), C empathetic refutational interviewing (facts with permission). Prompts v6 in `prompt/pt/*_v6.txt`, English text as reviewed by the team.
6. The conversation. In arm A the fixed opener about the cachorro caramelo is sent by the code, and after the rating at message 6 the fixed transition to the urnas; the model then runs under `A2_control_elections_v6`.
7. **Ratings during the conversation**: the same two questions and buttons after the participant's 6th, 12th, 18th and 24th messages, lead-in "Antes de continuar, responda mais duas perguntas rápidas.", in every arm. The rating after the 6th message is the **post** measurement (main outcome); the baseline is **pre**.
8. **Ending.** A small "Encerrar conversa" button sits in the header from the moment the conversation starts. Pressing it asks for confirmation, then offers the optional exit questions ("Antes de sair, você pode responder duas perguntas rápidas? É opcional." with Responder / Pular e encerrar); the answers are saved as the **exit** rating with the message count at that moment, and the choice is logged. Pressed right after a regular rating, the button goes straight to the debrief. After the rating at message 24 the debrief is shown and the chat closes. With no participant message for `WEBCHAT_INACTIVITY_MINUTES` (15) while the page is open, the page shows the debrief and closes the chat by itself. The debrief appears only at the end; a participant who simply closes the page never sees it, as intended.
9. **The sheet is not a trap.** Opening the questions pushes a browser history entry. The system Back gesture (Android's reflex for dismissing a bottom sheet; in the Facebook/Instagram in-app browsers it would otherwise close the page) or a tap on the shaded chat only collapses the sheet to a "Responder às perguntas (n de 2)" bar over the text box; the chat can be read and scrolled, and the bar reopens the questions where they were. The page reports these moments to `POST /api/session/{id}/event` (`sheet_shown`, `back`, `shade`, `reopen`, `hidden`, `pagehide`, with the question number) for diagnosis of drop-outs at the check-in.

Every message, answer and tap is written to Firestore as it happens, so a participant who leaves mid-way still contributes a partial record. Reloading the page resumes the same session (id kept in the browser's localStorage).

The WhatsApp developer commands work the same way here, typed as messages:
`/info` shows the arm, phase, turn count, pre/post/exit ratings and system prompt;
`/reset` deletes the session from Firestore and reloads the page as a brand
new participant; `/lang en` or `/lang pt` switches the prompt language.
`?new=1` on the URL also starts a fresh session.

These are the web deployment's defaults, set in `webchat/app.py` and
overridable in `webchat/.env`: `TRUST_RATING_MIN=1`, `TRUST_RATING_MAX=7`,
`TRUST_CHECK_INTERVAL=6`, `DEBRIEF_AFTER_TURNS=24`, `CONTINUE_AFTER_DEBRIEF=false`,
`WEBCHAT_INACTIVITY_MINUTES=15`.

## What is recorded

Same document shape as WhatsApp, in collection `web_conversations`, keyed by a random session id (`web_…`) instead of a phone number:

- history, phase, variant (`prompt_variant`, empty until the arm is drawn after the baseline filter, with `variant_assigned_at`), turn count, `debriefed_at`
- ratings: `feeling_array` entries `{score, score_system, message_index, slot, timestamp, events}` where `score` is question 2 (urnas, the primary measure), `score_system` question 1, `slot` is `pre` / `post` / `exit` / null, and `events` the button taps (`q`, `value`, `selected|changed|confirmed`, `at`). The analysis fields `rating_pre`, `rating_post`, `rating_exit` (urnas) and `rating_pre_system`, `rating_post_system`, `rating_exit_system` are plain fields on the document
- `client_events`: UI events from the page while the questions were open (`{name, at, received_at, kind, question, collapsed}`; see step 9), at most 60 per session
- `screened_out_reason`: `eligibility` or `high_trust`; `ended_reason`: `limit`, `button` or `inactivity`; `exit`: `{choice: rated|skipped|after_rating, at, user_turns}` when the button was used
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
| `PesquisaConcluida` | custom | the **post rating** is stored (`rating_post`, the questions after message 6 in every arm), i.e. the session has become a research-usable pre/post pair | once per session |

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
the two questions, one message (ConversaIniciada), six messages and the questions again
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
