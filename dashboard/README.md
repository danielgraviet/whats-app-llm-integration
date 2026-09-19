# WhatsApp Study Dashboard

Grafana + TimescaleDB, fed from Firestore by a small poller. Same shape as the
VAPI dashboard: Docker containers on your machine, a script that fills the
database every 30 seconds, and an `rt_metrics` table that records zeros so the
live graph stays flat instead of disappearing when nothing is happening.

```
Firestore (Railway app writes) ──poll every 30s──► export_to_postgres.py ──► TimescaleDB ◄── Grafana
```

Nothing in the Railway app changes. The poller reads Firestore with the same
service-account credentials you use for local development.

## Files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Starts TimescaleDB and Grafana together, with persistent volumes |
| `schema.sql` | Creates the tables and hypertables. Applied automatically on the first container start; safe to re-run by hand |
| `export_to_postgres.py` | The poller. Mirrors conversations, messages and ratings, and writes one `rt_metrics` row per tick |
| `grafana/provisioning/datasources/timescale.yml` | Registers the TimescaleDB datasource (uid `wa-timescale`) |
| `grafana/provisioning/dashboards/whatsapp_dashboard.json` | The dashboard. Loaded automatically; edits made in the UI are kept |
| `requirements.txt` | Python deps for the poller |

## First-time setup

"Docker Compose" is just a YAML file describing the containers you used to
start by hand with `docker run`. One command starts or stops all of them.

```bash
cd dashboard

# 1. Start the database and Grafana. First start creates the schema.
docker compose up -d

# 2. Install the poller's dependencies (once, in the project venv)
pip install -r requirements.txt

# 3. Configure the poller: copy the example and set the hash salt
cp .env.schema .env
$EDITOR .env

# 4. Run the poller from the project root. Firebase credentials come from
#    the app's .env.local unless you set them in dashboard/.env.
cd ..
python dashboard/export_to_postgres.py --backfill
```

Open <http://localhost:3000> (admin / admin, it asks you to change it). The
"WhatsApp Study" dashboard is already there.

### If port 3000 or 5432 is taken

The old VAPI Grafana container uses port 3000 on the host network. Either stop
it (`docker stop grafana`) or run this stack on other ports:

```bash
GRAFANA_PORT=3001 PG_PORT=5433 docker compose up -d
```

and set `DASHBOARD_PG_DSN=postgresql://postgres:password@localhost:5433/postgres`
in `dashboard/.env`.

### Manual equivalent (no compose)

```bash
docker volume create wa-timescale-data
docker run -d --name wa-timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=password \
  -v wa-timescale-data:/var/lib/postgresql/data timescale/timescaledb:latest-pg17
psql postgresql://postgres:password@localhost:5432/postgres -f dashboard/schema.sql

docker volume create wa-grafana-data
docker run -d --name wa-grafana -p 3000:3000 -e PG_PASSWORD=password \
  -v wa-grafana-data:/var/lib/grafana \
  -v "$PWD/dashboard/grafana/provisioning:/etc/grafana/provisioning:ro" grafana/grafana-enterprise
```

To use the dashboard in an existing Grafana instead, create a PostgreSQL
datasource with uid `wa-timescale` (Connections > Data sources > Add, then
set the uid in the URL bar or via the API) and import the JSON file.

## Poller

```bash
python dashboard/export_to_postgres.py             # loop forever
python dashboard/export_to_postgres.py --once      # single tick
python dashboard/export_to_postgres.py --backfill  # re-read everything once, then continue
```

Settings are read from `.env` files, in this order. The first definition of a
variable wins, and anything already set in the shell wins over both.

1. `dashboard/.env` (copy `dashboard/.env.schema` to start). Override the path with `DASHBOARD_ENV_FILE`.
2. `.env.<APP_ENV>` in the project root, `APP_ENV` defaulting to `local`. This is the app's own file, so the Firebase credentials do not need to be repeated.

| Variable | Default | Meaning |
|---|---|---|
| `DASHBOARD_PG_DSN` | `postgresql://postgres:password@localhost:5432/postgres` | Where to write |
| `DASHBOARD_HASH_SALT` | empty | Salt for hashing phone numbers. Set it once; changing it splits participants into new rows |
| `POLL_INTERVAL` | `30` | Seconds between ticks |
| `FIREBASE_CREDS_PATH` or `FIREBASE_CREDS_JSON` | from `.env.local` | Firestore service account, same as the app |
| `APP_ENV` | `local` | Which app env file to fall back to |

The poller refuses to start without Firebase credentials and logs which env
files it loaded, so a misconfiguration shows up immediately.

Each tick reads only the Firestore documents whose `updated_at` changed since
the last tick (watermark stored in `poller_state`), so Firestore read cost is
proportional to activity, not to the number of participants. The first run,
and `--backfill`, read everything.

Phone numbers never enter the dashboard database. Participants are keyed on a
salted SHA-256 prefix, so a leaked dashboard DB cannot be joined back to
Firestore without the salt.

Run it under `nohup`, `tmux`, or a systemd user service so it survives a
closed terminal; it reconnects to Postgres on error and logs every tick.

## Tables

| Table | Grain | Notes |
|---|---|---|
| `wa_conversations` | one row per participant | Upserted on every change. Phase, variant, timestamps, turn count, initial and latest rating, first ad referral |
| `wa_messages` | one row per stored message | Hypertable on `ts`. Role and length only, no content |
| `wa_ratings` | one row per trust rating | Hypertable on `ts` |
| `rt_metrics` | one row per poll tick | Hypertable. Active counts, phase counts, hourly starts and debriefs. Zeros are recorded |
| `poller_state` | key/value | Watermark |

## What "active" means

There is no call object, so activity is defined by recency and recorded under
several definitions so you can choose in Grafana:

- **active (5 min)**: not ended, and the conversation document was updated in the last 5 minutes. Someone is effectively typing.
- **active (30 min)**: same with a 30-minute window. A session in progress with slow replies.
- **awaiting rating**: blocked on a trust-rating reply (initial or check-in).
- **Outcome** (pie and stats): `completed` = debriefed; `never rated` = dropped before the first rating; `abandoned` = not ended and silent longer than `abandon_after()` (default 24 hours); otherwise `in progress`.

The abandon threshold is a tiny SQL function rather than a Grafana variable,
because shared/public dashboards cannot use template variables. To change it:

```sql
CREATE OR REPLACE FUNCTION abandon_after() RETURNS interval
    LANGUAGE sql IMMUTABLE AS $$ SELECT interval '48 hours' $$;
```

## Sharing the dashboard

Grafana's **Share > Share externally** (a "public dashboard") gives a link
that works without a login. Limitations that matter here:

- Template variables are not interpolated, which is why the dashboard has none.
- The time range picker is off unless you enable it in the share settings.
- Viewers see data only; nothing is editable.

If colleagues need to edit or explore, create Viewer accounts instead
(Administration > Users) and keep the public link for read-only sharing.

## Running on a server (e.g. a DigitalOcean droplet)

- Postgres is bound to `127.0.0.1` in `docker-compose.yml`. Do not change that
  to `0.0.0.0` on a machine with a public IP: the default password would be
  open to the internet.
- Change the Grafana admin password on first login, and put Grafana behind
  HTTPS (Caddy or nginx with Let's Encrypt) before sharing links widely.
- After pulling a new version: `docker compose up -d` picks up compose changes,
  provisioning re-reads the dashboard JSON within about 10 seconds, and any
  new SQL objects need `psql ... -f dashboard/schema.sql` once (safe to re-run).


Reply latency is not shown: the app stamps both the user message and the reply
when it saves them after the LLM returns, so their timestamps are nearly
identical. Storing Meta's message timestamp on each history entry would enable
it.
