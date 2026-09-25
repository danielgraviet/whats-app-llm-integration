"""Conversation browser: a small server that fronts Firestore for the HTML UI.

Run from the project root:

    python browser/server.py            # real data, reads browser/.env then .env.<APP_ENV>
    python browser/server.py --demo     # fake data, no credentials needed (UI preview)

The browser (index.html, served at /) never talks to Firestore or OpenAI;
every request goes through this process, which holds the credentials.

Endpoints (all behind HTTP Basic auth unless --demo or BROWSER_ALLOW_NO_AUTH=1):
    GET  /                       the UI
    GET  /api/status             counts and cache freshness
    GET  /api/conversations?q=   summaries for every conversation (q = keyword search
                                 over transcripts, accent- and case-insensitive; all
                                 whitespace-separated terms must match)
    GET  /api/conversations/{id} full document: transcript, ratings, metadata, raw first message
    POST /api/translate          {"texts": [...]} -> {"translations": [...]} via OpenAI;
                                 cached in memory only, nothing is written anywhere
    POST /api/refresh            force a full reload from Firestore
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import logging
import os
import random
import secrets
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

BROWSER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BROWSER_DIR.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("browser")


# ----------------------------------------------------------------------------
# configuration
# ----------------------------------------------------------------------------
def load_env_files() -> list[Path]:
    """browser/.env first, then the app's .env.<APP_ENV>; shell vars win over both."""
    loaded = []
    for path in [
        Path(os.getenv("BROWSER_ENV_FILE") or BROWSER_DIR / ".env"),
        PROJECT_ROOT / f".env.{os.getenv('APP_ENV', 'local')}",
    ]:
        if path.is_file():
            load_dotenv(path, override=False)
            loaded.append(path)
    return loaded


_LOADED_ENV_FILES = load_env_files()
sys.path.insert(0, str(PROJECT_ROOT))

PORT = int(os.getenv("BROWSER_PORT", "8090"))
HOST = os.getenv("BROWSER_HOST", "0.0.0.0")
PASSWORD = os.getenv("BROWSER_PASSWORD", "")
USERNAME = os.getenv("BROWSER_USER", "research")
ALLOW_NO_AUTH = os.getenv("BROWSER_ALLOW_NO_AUTH", "").lower() in ("1", "true", "yes")
HASH_SALT = os.getenv("DASHBOARD_HASH_SALT", "")
SHOW_PHONE = os.getenv("BROWSER_SHOW_PHONE", "").lower() in ("1", "true", "yes")
REFRESH_SECONDS = float(os.getenv("BROWSER_REFRESH_SECONDS", "30"))
ABANDON_HOURS = float(os.getenv("BROWSER_ABANDON_HOURS", "24"))
TRANSLATE_MODEL = os.getenv("TRANSLATE_MODEL", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def phone_hash(phone: str) -> str:
    """Same scheme as dashboard/export_to_postgres.py so ids match Grafana."""
    return hashlib.sha256((HASH_SALT + phone).encode()).hexdigest()[:16]


def normalize(text: str) -> str:
    """Lower-case and strip accents so 'urna' matches 'Urna' and 'eleicao' matches 'eleição'."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", (text or "").lower()) if not unicodedata.combining(c)
    )


def _utc(ts: Any) -> dt.datetime | None:
    if ts is None or ts == "":
        return None
    if isinstance(ts, (int, float)):
        return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc)
    if isinstance(ts, str):
        try:
            return dt.datetime.fromtimestamp(int(ts), tz=dt.timezone.utc)
        except ValueError:
            try:
                d = dt.datetime.fromisoformat(ts)
                return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)
            except ValueError:
                return None
    if isinstance(ts, dt.datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=dt.timezone.utc)
    return None


def _iso(ts: dt.datetime | None) -> str | None:
    return ts.isoformat() if ts else None


def _jsonable(v: Any) -> Any:
    if isinstance(v, dt.datetime):
        return _iso(_utc(v))
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def outcome_of(phase: str, intro_sent: bool, last_activity: dt.datetime | None, now: dt.datetime) -> str:
    if phase == "ended":
        return "completed"
    if not intro_sent or phase == "awaiting_initial_rating":
        return "never rated"
    if last_activity and last_activity < now - dt.timedelta(hours=ABANDON_HOURS):
        return "abandoned"
    return "in progress"


# ----------------------------------------------------------------------------
# conversation model built from a Firestore document
# ----------------------------------------------------------------------------
class Conv:
    def __init__(self, phone: str, d: dict):
        self.phone = phone
        self.id = phone_hash(phone)
        self.raw = d
        history = d.get("history") or []
        self.messages = []
        for i, m in enumerate(history):
            self.messages.append({
                "index": i,
                "role": m.get("role"),
                "content": m.get("content") or "",
                "timestamp": _iso(_utc(m.get("timestamp"))),
            })
        self.ratings = sorted(
            [{"score": r.get("score"), "message_index": r.get("message_index"), "timestamp": _iso(_utc(r.get("timestamp")))}
             for r in (d.get("feeling_array") or []) if r.get("score") is not None],
            key=lambda r: ((r["message_index"] or 0), r["timestamp"] or ""),
        )
        self.search_text = normalize(" ".join(m["content"] for m in self.messages))
        raw_first = d.get("first_message_raw") or {}
        msg_ts = [m["timestamp"] for m in self.messages if m["timestamp"]]
        self.started_at = _utc(raw_first.get("timestamp")) or (_utc(min(msg_ts)) if msg_ts else _utc(d.get("updated_at")))
        self.last_activity_at = _utc(d.get("updated_at"))
        self.debriefed_at = _utc(d.get("debriefed_at"))
        self.phase = d.get("conversation_phase") or "unknown"
        self.intro_sent = bool(d.get("intro_sent"))
        pv = d.get("prompt_variant") or ""
        self.variant = pv.split("_prompt_", 1)[1] if "_prompt_" in pv else pv
        referrals = d.get("referrals") or []
        first_ref = (referrals[0].get("referral") if referrals else raw_first.get("referral")) or {}
        self.ad_source_id = first_ref.get("source_id")
        self.ctwa_clid = first_ref.get("ctwa_clid")
        self.n_referrals = len(referrals)
        self.profile_name = ((d.get("first_contacts_raw") or [{}])[0].get("profile") or {}).get("name")

    def summary(self, now: dt.datetime) -> dict:
        initial = next((r["score"] for r in self.ratings if r["message_index"] == 0), None)
        if initial is None and self.ratings:
            initial = self.ratings[0]["score"]
        latest = self.ratings[-1]["score"] if self.ratings else None
        n_chars = sum(len(m["content"]) for m in self.messages)
        user_chars = sum(len(m["content"]) for m in self.messages if m["role"] == "user")
        duration_min = None
        if self.started_at and self.last_activity_at:
            duration_min = round((self.last_activity_at - self.started_at).total_seconds() / 60, 1)
        s = {
            "id": self.id,
            "variant": self.variant,
            "prompt_variant": self.raw.get("prompt_variant"),
            "language": self.raw.get("language"),
            "phase": self.phase,
            "outcome": outcome_of(self.phase, self.intro_sent, self.last_activity_at, now),
            "intro_sent": self.intro_sent,
            "started_at": _iso(self.started_at),
            "last_activity_at": _iso(self.last_activity_at),
            "debriefed_at": _iso(self.debriefed_at),
            "user_turn_count": int(self.raw.get("user_turn_count") or 0),
            "n_messages": len(self.messages),
            "n_chars": n_chars,
            "user_chars": user_chars,
            "duration_min": duration_min,
            "n_ratings": len(self.ratings),
            "initial_rating": initial,
            "latest_rating": latest,
            "rating_change": (latest - initial) if (initial is not None and latest is not None) else None,
            "ad_source_id": self.ad_source_id,
            "ctwa_clid": self.ctwa_clid,
            "n_referrals": self.n_referrals,
        }
        if SHOW_PHONE:
            s["phone"] = self.phone
            s["profile_name"] = self.profile_name
        return s

    def detail(self, now: dt.datetime) -> dict:
        d = self.summary(now)
        d["messages"] = self.messages
        d["ratings"] = self.ratings
        d["first_message_raw"] = _jsonable(self.raw.get("first_message_raw") or {})
        d["referrals"] = _jsonable(self.raw.get("referrals") or [])
        d["pending_ai_response"] = self.raw.get("pending_ai_response") or ""
        if SHOW_PHONE:
            d["first_contacts_raw"] = _jsonable(self.raw.get("first_contacts_raw") or [])
        else:
            # strip the sender's number and profile from the raw payload
            fm = dict(d["first_message_raw"])
            fm.pop("from", None)
            d["first_message_raw"] = fm
        return d

    def matches(self, terms: list[str]) -> bool:
        hay = self.search_text + " " + normalize(f"{self.id} {self.variant} {self.ad_source_id or ''} {self.phase}")
        return all(t in hay for t in terms)

    def snippet(self, terms: list[str], width: int = 90) -> str | None:
        for m in self.messages:
            n = normalize(m["content"])
            for t in terms:
                i = n.find(t)
                if i >= 0:
                    a = max(0, i - width // 2)
                    return ("…" if a else "") + m["content"][a : a + width] + ("…" if a + width < len(m["content"]) else "")
        return None


# ----------------------------------------------------------------------------
# data sources
# ----------------------------------------------------------------------------
class FirestoreSource:
    def __init__(self):
        from database import firebase  # the app's own initialiser, reads FIREBASE_CREDS_*
        self.client = firebase.init_firestore()

    def load(self, since: dt.datetime | None) -> list[tuple[str, dict]]:
        from google.cloud.firestore_v1.base_query import FieldFilter
        coll = self.client.collection("conversations")
        q = coll if since is None else coll.where(filter=FieldFilter("updated_at", ">", since - dt.timedelta(seconds=5)))
        return [(doc.id, doc.to_dict() or {}) for doc in q.stream()]


class DemoSource:
    """Fake conversations so the UI can be previewed without credentials."""

    PT_USER = ["Eu acho que as urnas não são confiáveis.", "Nunca vi uma auditoria de verdade.", "Meu tio trabalhou na eleição e disse que é seguro.",
               "Não sei, tenho dúvidas sobre o software.", "Como eles garantem que ninguém mexe nos dados?", "Talvez com papel seria melhor.",
               "Entendi, faz sentido.", "Obrigado pela conversa.", "A urna eletrônica é rápida, isso é bom."]
    PT_BOT = ["O que te faz pensar isso?", "Pode me contar mais sobre essa experiência?", "Como você acha que outras pessoas veem essa questão?",
              "O que te ajudaria a confiar mais?", "Entendo. E o que você já ouviu sobre as auditorias?", "Obrigado por compartilhar isso."]
    VARIANTS = ["A_control_condition", "B_motivational_learning", "C_perspective", "D_christmas_dinner", "E_critical_thinking"]

    def __init__(self, n: int = 60, seed: int = 7):
        rnd = random.Random(seed)
        now = dt.datetime.now(dt.timezone.utc)
        self.docs = []
        for i in range(n):
            phone = f"5511{rnd.randint(900000000, 999999999)}"
            variant = rnd.choice(self.VARIANTS)
            start = now - dt.timedelta(minutes=rnd.randint(3, 60 * 24 * 10))
            turns = rnd.choice([0, 0, 1, 2, 3, 4, 5, 6, 7, 8, 8, 8])
            history, t = [], start + dt.timedelta(minutes=1)
            for k in range(turns):
                history.append({"role": "user", "content": rnd.choice(self.PT_USER), "timestamp": t})
                history.append({"role": "assistant", "content": rnd.choice(self.PT_BOT), "timestamp": t + dt.timedelta(seconds=4)})
                t += dt.timedelta(minutes=rnd.randint(1, 6))
            ratings = []
            intro_sent = turns > 0 or rnd.random() > 0.3
            if turns > 0:
                ratings.append({"score": rnd.randint(1, 10), "message_index": 0, "timestamp": start + dt.timedelta(seconds=40)})
                for mi in (3, 6):
                    if turns >= mi:
                        ratings.append({"score": max(1, min(10, ratings[0]["score"] + rnd.randint(-2, 3))), "message_index": mi, "timestamp": start + dt.timedelta(minutes=mi * 3)})
            phase = "ended" if turns >= 8 else ("awaiting_initial_rating" if turns == 0 else rnd.choice(["normal", "normal", "awaiting_check_in_rating"]))
            last = history[-1]["timestamp"] if history else start
            ref = {"source_type": "ad", "source_id": f"AD_{rnd.randint(1, 3)}", "ctwa_clid": f"clid{i}", "headline": "Converse sobre as urnas"} if rnd.random() > 0.2 else None
            d = {"history": history, "updated_at": last, "language": "PT", "prompt_variant": f"PT_prompt_{variant}", "conversation_phase": phase,
                 "feeling_array": ratings, "user_turn_count": turns, "intro_sent": intro_sent, "pending_ai_response": "",
                 "debriefed_at": last if phase == "ended" else None,
                 "first_message_raw": {"from": phone, "id": f"wamid.demo{i}", "timestamp": str(int(start.timestamp())), "type": "text", "text": {"body": "oi"}, **({"referral": ref} if ref else {})},
                 "first_contacts_raw": [{"profile": {"name": "Demo"}, "wa_id": phone}],
                 "referrals": [{"message_id": f"wamid.demo{i}", "message_timestamp": str(int(start.timestamp())), "referral": ref}] if ref else []}
            self.docs.append((phone, d))

    def load(self, since):
        if since is None:
            return list(self.docs)
        return [(p, d) for p, d in self.docs if _utc(d["updated_at"]) > since - dt.timedelta(seconds=5)]


# ----------------------------------------------------------------------------
# in-memory store with incremental refresh
# ----------------------------------------------------------------------------
class Store:
    def __init__(self, source):
        self.source = source
        self.convs: dict[str, Conv] = {}
        self.watermark: dt.datetime | None = None
        self.last_refresh: dt.datetime | None = None
        self.last_error: str | None = None
        self.lock = asyncio.Lock()

    async def refresh(self, full: bool = False) -> int:
        async with self.lock:
            since = None if full else self.watermark
            try:
                rows = await asyncio.to_thread(self.source.load, since)
            except Exception as e:  # keep serving the old cache
                self.last_error = f"{type(e).__name__}: {e}"
                log.exception("refresh failed")
                return 0
            if full:
                self.convs = {}
            for phone, d in rows:
                c = Conv(phone, d)
                self.convs[c.id] = c
                if c.last_activity_at and (self.watermark is None or c.last_activity_at > self.watermark):
                    self.watermark = c.last_activity_at
            self.last_refresh = dt.datetime.now(dt.timezone.utc)
            self.last_error = None
            if rows:
                log.info("refresh: %d document(s) updated, %d total", len(rows), len(self.convs))
            return len(rows)


# ----------------------------------------------------------------------------
# translation (OpenAI, cached in memory only)
# ----------------------------------------------------------------------------
class Translator:
    SYSTEM = ("You translate WhatsApp messages from Brazilian Portuguese to natural English. "
              "Return only the translation, no quotes, no commentary. Keep line breaks. "
              "If the text is already English, return it unchanged.")

    def __init__(self, api_key: str, model: str, demo: bool):
        self.cache: dict[str, str] = {}
        self.demo = demo
        self.model = model
        self.client = None
        if api_key and not demo:
            import openai
            self.client = openai.AsyncOpenAI(api_key=api_key)
        self.sem = asyncio.Semaphore(8)

    async def one(self, text: str) -> str:
        key = hashlib.sha1(text.encode()).hexdigest()
        if key in self.cache:
            return self.cache[key]
        if not text.strip():
            return text
        if self.demo or self.client is None:
            out = f"[EN demo] {text}"
        else:
            async with self.sem:
                r = await self.client.chat.completions.create(
                    model=self.model, temperature=0,
                    messages=[{"role": "system", "content": self.SYSTEM}, {"role": "user", "content": text}],
                )
            out = (r.choices[0].message.content or "").strip()
        self.cache[key] = out
        return out

    async def many(self, texts: list[str]) -> list[str]:
        return list(await asyncio.gather(*(self.one(t) for t in texts)))


# ----------------------------------------------------------------------------
# app
# ----------------------------------------------------------------------------
app = FastAPI(title="WhatsApp conversation browser", docs_url=None, redoc_url=None)
security = HTTPBasic(auto_error=False)
STORE: Store | None = None
TRANSLATOR: Translator | None = None
DEMO = False


def require_auth(request: Request, creds: HTTPBasicCredentials | None = Depends(security)):
    if DEMO or ALLOW_NO_AUTH or not PASSWORD:
        return
    ok = creds is not None and secrets.compare_digest(creds.username, USERNAME) and secrets.compare_digest(creds.password, PASSWORD)
    if not ok:
        raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": 'Basic realm="conversation browser"'})


@app.get("/", dependencies=[Depends(require_auth)])
def index():
    return FileResponse(BROWSER_DIR / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/status", dependencies=[Depends(require_auth)])
def status():
    now = dt.datetime.now(dt.timezone.utc)
    counts: dict[str, int] = {}
    for c in STORE.convs.values():
        o = outcome_of(c.phase, c.intro_sent, c.last_activity_at, now)
        counts[o] = counts.get(o, 0) + 1
    return {"total": len(STORE.convs), "by_outcome": counts, "last_refresh": _iso(STORE.last_refresh),
            "last_error": STORE.last_error, "demo": DEMO, "show_phone": SHOW_PHONE,
            "translate_available": TRANSLATOR.client is not None or DEMO, "abandon_hours": ABANDON_HOURS,
            "refresh_seconds": REFRESH_SECONDS}


@app.get("/api/conversations", dependencies=[Depends(require_auth)])
def list_conversations(q: str = ""):
    now = dt.datetime.now(dt.timezone.utc)
    terms = [t for t in normalize(q).split() if t]
    out = []
    for c in STORE.convs.values():
        if terms and not c.matches(terms):
            continue
        s = c.summary(now)
        if terms:
            s["snippet"] = c.snippet(terms)
        out.append(s)
    out.sort(key=lambda s: s["started_at"] or "", reverse=True)
    return {"count": len(out), "total": len(STORE.convs), "q": q, "conversations": out}


@app.get("/api/conversations/{conv_id}", dependencies=[Depends(require_auth)])
def get_conversation(conv_id: str):
    c = STORE.convs.get(conv_id)
    if not c:
        raise HTTPException(404, "conversation not found")
    return c.detail(dt.datetime.now(dt.timezone.utc))


class TranslateBody(BaseModel):
    texts: list[str]


@app.post("/api/translate", dependencies=[Depends(require_auth)])
async def translate(body: TranslateBody):
    if TRANSLATOR.client is None and not DEMO:
        raise HTTPException(501, "Translation unavailable: set OPENAI_API_KEY in browser/.env")
    if len(body.texts) > 200:
        raise HTTPException(413, "too many texts in one request (max 200)")
    try:
        return {"translations": await TRANSLATOR.many(body.texts)}
    except Exception as e:
        log.exception("translation failed")
        raise HTTPException(502, f"translation failed: {type(e).__name__}")


@app.post("/api/refresh", dependencies=[Depends(require_auth)])
async def refresh():
    n = await STORE.refresh(full=True)
    return {"reloaded": n, "total": len(STORE.convs), "last_error": STORE.last_error}


async def _refresh_loop():
    while True:
        await asyncio.sleep(REFRESH_SECONDS)
        await STORE.refresh()


@app.on_event("startup")
async def _startup():
    n = await STORE.refresh(full=True)
    log.info("loaded %d conversation(s)%s", n, " (demo data)" if DEMO else "")
    asyncio.create_task(_refresh_loop())


def configure(demo: bool):
    global STORE, TRANSLATOR, DEMO
    DEMO = demo
    if _LOADED_ENV_FILES:
        log.info("loaded env files: %s", ", ".join(map(str, _LOADED_ENV_FILES)))
    if demo:
        STORE = Store(DemoSource())
    else:
        if not (os.getenv("FIREBASE_CREDS_PATH") or os.getenv("FIREBASE_CREDS_JSON")):
            log.error("No Firebase credentials: set FIREBASE_CREDS_PATH or FIREBASE_CREDS_JSON in browser/.env (or run with --demo)")
            sys.exit(2)
        if not PASSWORD and not ALLOW_NO_AUTH:
            log.error("BROWSER_PASSWORD is not set. Transcripts are sensitive; set a password in browser/.env "
                      "or set BROWSER_ALLOW_NO_AUTH=1 if the server is only reachable locally.")
            sys.exit(2)
        STORE = Store(FirestoreSource())
    TRANSLATOR = Translator(OPENAI_API_KEY, TRANSLATE_MODEL, demo)
    if not demo and not OPENAI_API_KEY:
        log.warning("OPENAI_API_KEY not set: the Translate button will be disabled")
    if not HASH_SALT:
        log.warning("DASHBOARD_HASH_SALT is empty; ids will not match the Grafana dashboard unless it is empty there too")


def main():
    ap = argparse.ArgumentParser(description="WhatsApp conversation browser")
    ap.add_argument("--demo", action="store_true", help="serve generated fake data (no credentials needed)")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default=HOST)
    args = ap.parse_args()
    configure(args.demo)
    log.info("serving on http://%s:%d  (auth: %s)", args.host, args.port,
             "off (demo)" if args.demo else ("off (BROWSER_ALLOW_NO_AUTH)" if ALLOW_NO_AUTH else f"basic, user '{USERNAME}'"))
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
