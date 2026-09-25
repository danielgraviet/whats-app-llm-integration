# Conversation Browser

A self-contained web page for reading study conversations: every transcript,
its metadata, the trust ratings, and the raw ad-referral payload, with keyword
search, sorting, and a client-side "Translate to English" view.

```
index.html (browser)  ──only talks to──►  server.py  ──►  Firestore (transcripts)
                                              └──►  OpenAI (translation, optional)
```

The page never sees a credential. `server.py` holds the Firebase service
account and the OpenAI key, keeps an in-memory copy of all conversations that
it refreshes incrementally every 30 seconds, and answers the page's requests.
Nothing is ever written to Firestore; translations are cached in the server's
memory only and vanish on restart.

## Files

| File | Purpose |
|---|---|
| `server.py` | FastAPI server: Firestore cache, search, translation proxy, HTTP Basic auth, serves `index.html` |
| `index.html` | The UI. Single file, no build step, no external resources |
| `.env.schema` | Template for `browser/.env` |
| `requirements.txt` | Python deps |

## Run it

```bash
pip install -r browser/requirements.txt
cp browser/.env.schema browser/.env      # set BROWSER_PASSWORD, salt, and (optionally) OPENAI_API_KEY
python browser/server.py                 # from the project root
```

Open `http://<server>:8090` and log in with user `research` and the password
you set. To preview the UI with generated fake data and no credentials:

```bash
python browser/server.py --demo
```

Settings are read from `browser/.env`, then the app's `.env.<APP_ENV>` (so the
Firebase credentials usually need no repeating), and shell variables win over
both. The server refuses to start without Firebase credentials or without a
password (unless `BROWSER_ALLOW_NO_AUTH=1`, for a machine that is only
reachable through an SSH tunnel).

## Using the page

- **Search** matches whole transcripts, ignoring case and accents, so `eleicao` finds `eleição`. Every word must match. Matches are highlighted in the transcript and a snippet shows in the list. `/` focuses the search box.
- **Sort** by start time, last activity, turns, messages, total length, user-text length, duration, rating change, initial or latest rating, or number of ratings. Missing values sort last.
- **Filters** narrow by outcome, variant, phase, and language.
- **Translate to English** sends the transcript to OpenAI through the server and shows English under each message; a selector switches between Portuguese only, both, or English only. The translation is never stored in the database.
- **Links** carry the selected conversation (`#id`) and the search (`?q=`), so a URL can be pasted to a colleague who has the password. `j` / `k` move through the list.

Participant identifiers are the same salted hashes the Grafana dashboard uses,
so an id from a Grafana table can be pasted into the search box here. Raw
phone numbers and WhatsApp profile names are hidden unless
`BROWSER_SHOW_PHONE=true`.

## Running it on the droplet next to Grafana

The simplest reliable way is a systemd unit so it survives reboots:

```ini
# /etc/systemd/system/conversation-browser.service
[Unit]
Description=WhatsApp study conversation browser
After=network.target

[Service]
WorkingDirectory=/root/whats-app-llm-integration
ExecStart=/usr/bin/python3 browser/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload && systemctl enable --now conversation-browser
```

Open port 8090 in the DigitalOcean firewall, or better, put both Grafana and
this server behind Caddy or nginx with HTTPS. Basic auth over plain HTTP sends
the password in the clear on every request, so HTTPS matters more here than
for the read-only Grafana link.

## API (for scripts)

All endpoints require the same Basic auth as the page.

| Endpoint | Returns |
|---|---|
| `GET /api/status` | counts by outcome, cache freshness, feature flags |
| `GET /api/conversations?q=words` | summaries for all (or matching) conversations |
| `GET /api/conversations/{id}` | full transcript, ratings, metadata, raw first message and referrals |
| `POST /api/translate` `{"texts": [...]}` | English translations, same order |
| `POST /api/refresh` | force a full reload from Firestore |
