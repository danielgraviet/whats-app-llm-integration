"""Poll Firestore and mirror the WhatsApp study data into TimescaleDB.

Run from the project root so the app's own Firestore setup is reused:

    APP_ENV=local python dashboard/export_to_postgres.py            # loop forever
    APP_ENV=local python dashboard/export_to_postgres.py --once     # one tick
    APP_ENV=local python dashboard/export_to_postgres.py --backfill # ignore watermark once

Configuration is read from environment variables, loaded from .env files in
this order (first definition wins; variables already set in the shell win over
both):

    1. dashboard/.env            dashboard-specific settings (see dashboard/.env.schema)
    2. .env.<APP_ENV>            the app's own env file (APP_ENV defaults to "local"),
                                 so the Firebase credentials do not need repeating

Override the first path with DASHBOARD_ENV_FILE=/path/to/file.

Variables:
    DASHBOARD_PG_DSN     postgresql://postgres:password@localhost:5432/postgres
    DASHBOARD_HASH_SALT  salt for hashing phone numbers (set it once, never change it)
    POLL_INTERVAL        seconds between ticks (default 30)
    FIREBASE_CREDS_PATH / FIREBASE_CREDS_JSON   same as the app

Each tick:
  1. reads every conversation whose Firestore updated_at is newer than the
     stored watermark (or everything on the first run / --backfill) and upserts
     it into wa_conversations, wa_messages and wa_ratings;
  2. computes the real-time gauges from the local mirror and inserts one
     rt_metrics row, zeros included.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import logging
import os
import sys
import time
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from google.cloud.firestore_v1.base_query import FieldFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("export_to_postgres")

DASHBOARD_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = DASHBOARD_DIR.parent


def load_env_files() -> list[Path]:
    """Load dashboard/.env, then the app's .env.<APP_ENV>. Returns what was loaded."""
    loaded = []
    candidates = [
        Path(os.getenv("DASHBOARD_ENV_FILE") or DASHBOARD_DIR / ".env"),
        PROJECT_ROOT / f".env.{os.getenv('APP_ENV', 'local')}",
    ]
    for path in candidates:
        if path.is_file():
            # override=False: earlier files and the real environment take precedence
            load_dotenv(path, override=False)
            loaded.append(path)
    return loaded


_LOADED_ENV_FILES = load_env_files()

# Make the project root importable when run as dashboard/export_to_postgres.py
sys.path.insert(0, str(PROJECT_ROOT))

from database import firebase  # noqa: E402  (reuses the app's Firestore init)

PG_DSN = os.getenv("DASHBOARD_PG_DSN", "postgresql://postgres:password@localhost:5432/postgres")
HASH_SALT = os.getenv("DASHBOARD_HASH_SALT", "")
POLL_INTERVAL = float(os.getenv("POLL_INTERVAL", "30"))
WATERMARK_KEY = "firestore_updated_at_watermark"
# Re-read a little before the watermark so a doc written in the same second
# as the previous tick is not missed.
WATERMARK_SLACK = dt.timedelta(seconds=5)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def phone_hash(phone: str) -> str:
    return hashlib.sha256((HASH_SALT + phone).encode()).hexdigest()[:16]


def _utc(ts) -> dt.datetime | None:
    """Normalise Firestore / naive / epoch-string timestamps to aware UTC."""
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    if isinstance(ts, str):
        try:
            return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc)
        except ValueError:
            return None
    if isinstance(ts, dt.datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
    return None


def _base_variant(prompt_variant: str | None) -> str | None:
    if not prompt_variant or "_prompt_" not in prompt_variant:
        return prompt_variant
    return prompt_variant.split("_prompt_", 1)[1]


def flatten(phone: str, d: dict) -> tuple[dict, list[tuple], list[tuple]]:
    """Turn one Firestore conversation document into DB rows."""
    h = phone_hash(phone)
    history = d.get("history") or []
    ratings = d.get("feeling_array") or []
    referrals = d.get("referrals") or []
    raw_first = d.get("first_message_raw") or {}
    prompt_variant = d.get("prompt_variant")
    variant = _base_variant(prompt_variant)

    msg_rows = []
    for i, m in enumerate(history):
        ts = _utc(m.get("timestamp"))
        if ts is None:
            continue
        msg_rows.append((ts, h, i, m.get("role"), len(m.get("content") or ""), variant))

    rating_rows = []
    for r in ratings:
        ts = _utc(r.get("timestamp"))
        if ts is None or r.get("score") is None:
            continue
        rating_rows.append((ts, h, int(r.get("message_index", 0)), int(r["score"]), variant))

    user_ts = [ts for ts, _, _, role, _, _ in msg_rows if role == "user"]
    asst_ts = [ts for ts, _, _, role, _, _ in msg_rows if role == "assistant"]
    all_ts = [ts for ts, *_ in msg_rows]

    started_at = _utc(raw_first.get("timestamp")) or (min(all_ts) if all_ts else None)

    sorted_ratings = sorted(rating_rows, key=lambda r: (r[2], r[0]))
    initial = next((r[3] for r in sorted_ratings if r[2] == 0), None)
    if initial is None and sorted_ratings:
        initial = sorted_ratings[0][3]
    latest = sorted_ratings[-1][3] if sorted_ratings else None

    first_ref = (referrals[0].get("referral") or {}) if referrals else (raw_first.get("referral") or {})

    conv = {
        "phone_hash": h,
        "variant": variant,
        "prompt_variant": prompt_variant,
        "language": d.get("language"),
        "phase": d.get("conversation_phase"),
        "intro_sent": bool(d.get("intro_sent", False)),
        "started_at": started_at,
        "last_user_msg_at": max(user_ts) if user_ts else None,
        "last_assistant_msg_at": max(asst_ts) if asst_ts else None,
        "last_activity_at": _utc(d.get("updated_at")),
        "debriefed_at": _utc(d.get("debriefed_at")),
        "user_turn_count": int(d.get("user_turn_count") or 0),
        "n_messages": len(history),
        "n_ratings": len(rating_rows),
        "initial_rating": initial,
        "latest_rating": latest,
        "n_referrals": len(referrals),
        "ad_source_id": first_ref.get("source_id"),
        "ad_source_type": first_ref.get("source_type"),
        "ctwa_clid": first_ref.get("ctwa_clid"),
    }
    return conv, msg_rows, rating_rows


# ----------------------------------------------------------------------------
# database writes
# ----------------------------------------------------------------------------
UPSERT_CONV = """
INSERT INTO wa_conversations (
    phone_hash, variant, prompt_variant, language, phase, intro_sent, started_at,
    last_user_msg_at, last_assistant_msg_at, last_activity_at, debriefed_at,
    user_turn_count, n_messages, n_ratings, initial_rating, latest_rating,
    n_referrals, ad_source_id, ad_source_type, ctwa_clid, synced_at
) VALUES (
    %(phone_hash)s, %(variant)s, %(prompt_variant)s, %(language)s, %(phase)s, %(intro_sent)s, %(started_at)s,
    %(last_user_msg_at)s, %(last_assistant_msg_at)s, %(last_activity_at)s, %(debriefed_at)s,
    %(user_turn_count)s, %(n_messages)s, %(n_ratings)s, %(initial_rating)s, %(latest_rating)s,
    %(n_referrals)s, %(ad_source_id)s, %(ad_source_type)s, %(ctwa_clid)s, now()
)
ON CONFLICT (phone_hash) DO UPDATE SET
    variant = EXCLUDED.variant, prompt_variant = EXCLUDED.prompt_variant,
    language = EXCLUDED.language, phase = EXCLUDED.phase, intro_sent = EXCLUDED.intro_sent,
    started_at = COALESCE(wa_conversations.started_at, EXCLUDED.started_at),
    last_user_msg_at = EXCLUDED.last_user_msg_at,
    last_assistant_msg_at = EXCLUDED.last_assistant_msg_at,
    last_activity_at = EXCLUDED.last_activity_at, debriefed_at = EXCLUDED.debriefed_at,
    user_turn_count = EXCLUDED.user_turn_count, n_messages = EXCLUDED.n_messages,
    n_ratings = EXCLUDED.n_ratings, initial_rating = EXCLUDED.initial_rating,
    latest_rating = EXCLUDED.latest_rating, n_referrals = EXCLUDED.n_referrals,
    ad_source_id = EXCLUDED.ad_source_id, ad_source_type = EXCLUDED.ad_source_type,
    ctwa_clid = EXCLUDED.ctwa_clid, synced_at = now();
"""

INSERT_MSG = """
INSERT INTO wa_messages (ts, phone_hash, turn_index, role, n_chars, variant)
VALUES %s ON CONFLICT DO NOTHING;
"""

INSERT_RATING = """
INSERT INTO wa_ratings (ts, phone_hash, message_index, score, variant)
VALUES %s ON CONFLICT DO NOTHING;
"""

INSERT_RT = """
INSERT INTO rt_metrics (
    logged_at, active_5m, active_30m, awaiting_rating,
    phase_initial, phase_normal, phase_checkin, phase_ended,
    total_conversations, started_last_hour, debriefed_last_hour
)
SELECT
    now(),
    count(*) FILTER (WHERE phase <> 'ended' AND last_activity_at > now() - interval '5 minutes'),
    count(*) FILTER (WHERE phase <> 'ended' AND last_activity_at > now() - interval '30 minutes'),
    count(*) FILTER (WHERE phase IN ('awaiting_initial_rating', 'awaiting_check_in_rating') AND intro_sent),
    count(*) FILTER (WHERE phase = 'awaiting_initial_rating'),
    count(*) FILTER (WHERE phase = 'normal'),
    count(*) FILTER (WHERE phase = 'awaiting_check_in_rating'),
    count(*) FILTER (WHERE phase = 'ended'),
    count(*),
    count(*) FILTER (WHERE started_at > now() - interval '1 hour'),
    count(*) FILTER (WHERE debriefed_at > now() - interval '1 hour')
FROM wa_conversations;
"""


def get_watermark(cur) -> dt.datetime | None:
    cur.execute("SELECT value FROM poller_state WHERE key = %s", (WATERMARK_KEY,))
    row = cur.fetchone()
    return dt.datetime.fromisoformat(row[0]) if row and row[0] else None


def set_watermark(cur, ts: dt.datetime) -> None:
    cur.execute(
        "INSERT INTO poller_state (key, value) VALUES (%s, %s) "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
        (WATERMARK_KEY, ts.isoformat()),
    )


# ----------------------------------------------------------------------------
# one tick
# ----------------------------------------------------------------------------
def fetch_changed_docs(fs_client, since: dt.datetime | None):
    coll = fs_client.collection("conversations")
    if since is None:
        return list(coll.stream())
    q = coll.where(filter=FieldFilter("updated_at", ">", since - WATERMARK_SLACK))
    return list(q.stream())


def tick(fs_client, pg_conn, backfill: bool = False) -> dict:
    stats = {"docs": 0, "messages": 0, "ratings": 0}
    with pg_conn:
        with pg_conn.cursor() as cur:
            since = None if backfill else get_watermark(cur)
            docs = fetch_changed_docs(fs_client, since)
            newest = since
            for doc in docs:
                d = doc.to_dict() or {}
                conv, msg_rows, rating_rows = flatten(doc.id, d)
                cur.execute(UPSERT_CONV, conv)
                if msg_rows:
                    psycopg2.extras.execute_values(cur, INSERT_MSG, msg_rows, page_size=500)
                if rating_rows:
                    psycopg2.extras.execute_values(cur, INSERT_RATING, rating_rows, page_size=500)
                stats["docs"] += 1
                stats["messages"] += len(msg_rows)
                stats["ratings"] += len(rating_rows)
                ua = conv["last_activity_at"]
                if ua and (newest is None or ua > newest):
                    newest = ua
            if newest:
                set_watermark(cur, newest)
            cur.execute(INSERT_RT)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run a single tick and exit")
    ap.add_argument("--backfill", action="store_true", help="ignore the watermark on the first tick")
    args = ap.parse_args()

    if _LOADED_ENV_FILES:
        log.info("loaded env files: %s", ", ".join(str(p) for p in _LOADED_ENV_FILES))
    else:
        log.info("no .env files found; using shell environment only")
    if not HASH_SALT:
        log.warning("DASHBOARD_HASH_SALT is empty; phone hashes are unsalted")
    if not (os.getenv("FIREBASE_CREDS_PATH") or os.getenv("FIREBASE_CREDS_JSON")):
        log.error(
            "No Firebase credentials. Set FIREBASE_CREDS_PATH or FIREBASE_CREDS_JSON in "
            "dashboard/.env or in .env.%s (see dashboard/.env.schema).",
            os.getenv("APP_ENV", "local"),
        )
        sys.exit(2)

    fs_client = firebase.init_firestore()
    pg_conn = psycopg2.connect(PG_DSN)
    log.info("connected; poll interval %.0fs", POLL_INTERVAL)

    backfill = args.backfill
    while True:
        started = time.monotonic()
        try:
            stats = tick(fs_client, pg_conn, backfill=backfill)
            log.info("tick ok: %s", stats)
            backfill = False
        except Exception:
            log.exception("tick failed")
            try:
                pg_conn.rollback()
            except Exception:
                pg_conn = psycopg2.connect(PG_DSN)
        if args.once:
            break
        time.sleep(max(0.0, POLL_INTERVAL - (time.monotonic() - started)))


if __name__ == "__main__":
    main()
