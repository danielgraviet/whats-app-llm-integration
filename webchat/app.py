"""Web version of the WhatsApp study conversation.

Reuses the WhatsApp deployment's conversation service, prompts, trust-rating
texts, and Firestore document shape unchanged; only the transport differs.
A browser session id plays the role of the phone number, and documents go to
the FIRESTORE_COLLECTION named in webchat/.env (default web_conversations).

Run from the project root:

    python webchat/app.py            # real: Firestore + OpenAI from webchat/.env
    python webchat/app.py --demo     # in-memory store + canned replies, no keys

Endpoints (all relative, so the app works under any nginx prefix):
    GET  /                          the chat page (Portuguese, mobile-first)
    POST /api/session               create or resume a session; body carries page metadata
    GET  /api/session/{id}          current state (history, phase, pending rating prompt)
    POST /api/session/{id}/screening  eligibility answer -> next question / baseline / closing
    POST /api/session/{id}/message  participant text  -> bot replies (+ rating prompt, debrief)
    POST /api/session/{id}/rating   participant 0-100 -> bot replies
    GET  /health                    liveness + commit
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 10):
    sys.exit(f"webchat needs Python 3.10 or newer (this is {sys.version.split()[0]}). "
             "See webchat/README.md, 'Install': use uv to get a managed Python, or install python3.12.")

import argparse
import asyncio
import datetime as dt
import hashlib
import logging
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

WEBCHAT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WEBCHAT_DIR.parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("webchat")


def load_env_files() -> list[Path]:
    loaded = []
    for path in [Path(os.getenv("WEBCHAT_ENV_FILE")) if os.getenv("WEBCHAT_ENV_FILE") else None, WEBCHAT_DIR / ".env", PROJECT_ROOT / f".env.{os.getenv('APP_ENV', 'local')}"]:
        if path is not None and path.is_file():
            load_dotenv(path, override=False); loaded.append(path)
    return loaded


_LOADED = load_env_files()
os.environ.setdefault("FIRESTORE_COLLECTION", "web_conversations")   # never the WhatsApp collection by default
# Study parameters for the web deployment (override in webchat/.env):
os.environ.setdefault("TRUST_RATING_MIN", "0")          # slider scale
os.environ.setdefault("TRUST_RATING_MAX", "100")
os.environ.setdefault("TRUST_CHECK_INTERVAL", "6")      # rating after every 6 user turns
os.environ.setdefault("DEBRIEF_AFTER_TURNS", "6")       # debrief after turn 6 (control: 12), then keep talking
os.environ.setdefault("CONTINUE_AFTER_DEBRIEF", "true")
sys.path.insert(0, str(PROJECT_ROOT))

DEMO = "--demo" in sys.argv or os.getenv("WEBCHAT_DEMO", "").lower() in ("1", "true")
if DEMO:
    from webchat.fake_firestore import install_transactional_shim  # noqa: E402
    install_transactional_shim()
    os.environ.setdefault("OPENAI_API_KEY", "demo")   # the OpenAI client is built at import time; never called in demo

from config import settings  # noqa: E402
from database import firebase  # noqa: E402
from services import conversation_service, trust_service  # noqa: E402
from integrations import openai_client  # noqa: E402

PORT = int(os.getenv("WEBCHAT_PORT", "8100"))
HOST = os.getenv("WEBCHAT_HOST", "127.0.0.1")
IP_SALT = os.getenv("WEBCHAT_IP_SALT", "")
def _git_sha() -> str:
    if os.getenv("GIT_COMMIT_SHA"):
        return os.environ["GIT_COMMIT_SHA"]
    try:
        import subprocess
        return subprocess.run(["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return ""


GIT_SHA = _git_sha()
MAX_MESSAGE_CHARS = int(os.getenv("WEBCHAT_MAX_MESSAGE_CHARS", "2000"))
# Meta Pixel for the Facebook ad campaigns (see webchat/README.md, "Meta Pixel").
# The base code fires PageView on load; the page fires ConversaIniciada on the
# first message and PesquisaConcluida when the post rating is recorded, each
# tagged with the ad's utm_content. Empty = no pixel at all (demo default).
META_PIXEL_ID = os.getenv("META_PIXEL_ID", "" if DEMO else "1276196112839237").strip()
if not re.fullmatch(r"[0-9]*", META_PIXEL_ID):
    sys.exit(f"META_PIXEL_ID must be digits only, got {META_PIXEL_ID!r}")

META_PIXEL_SNIPPET = """<!-- Meta Pixel Code -->
<script>
!function(f,b,e,v,n,t,s)
{if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '%(id)s');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none"
src="https://www.facebook.com/tr?id=%(id)s&ev=PageView&noscript=1"
/></noscript>
<!-- End Meta Pixel Code -->"""
# Developer commands typed as messages, exactly as on WhatsApp:
#   /info            condition, phase, turn count, ratings, system prompt
#   /reset           delete this session's document; the page reloads as a brand-new
#                    participant (new session id, new random condition)
#   /lang en|pt      switch prompt language
DEV_COMMANDS = ("/info", "/reset", "/lang en", "/lang pt")

# Texts used by the page. Everything the participant reads is Portuguese.
UI_TEXT = {
    "title": "Pesquisa sobre as urnas eletrônicas",
    "subtitle": "Universidade do Texas em Austin",
    "placeholder": "Digite sua mensagem",
    "send": "Enviar",
    "rate_button": "Avaliar agora",
    "rate_title": "O quanto você confia que as urnas eletrônicas brasileiras registram e contam corretamente cada voto?",
    "rate_low": "Não confio nem um pouco",
    "rate_high": "Confio totalmente",
    "rate_unit": "%",
    "rate_hint": "Mova a barra para registrar sua resposta",
    "rate_confirm": "Avaliar agora",
    "rate_pending": "Por favor, responda à avaliação acima antes de continuar.",
    "screening_pending": "Por favor, responda à pergunta acima antes de continuar.",
    "screened_out": "Esta sessão foi encerrada.",
    "typing": "digitando…",
    "ended": "Esta conversa foi encerrada. Obrigado por participar.",
    "error": "Desculpe, ocorreu um erro. Tente novamente em instantes.",
    "resume": "Continuando sua conversa anterior.",
    "footer": "Sua participação é voluntária e anônima. Você pode encerrar a conversa a qualquer momento fechando esta página.",
}


# ----------------------------------------------------------------------------
# request models
# ----------------------------------------------------------------------------
class SessionStart(BaseModel):
    session_id: str | None = None                 # resume if given and known
    query: dict[str, str] = Field(default_factory=dict)   # URL query params (utm_*, fbclid, ...)
    referrer: str = ""
    user_agent: str = ""
    language: str = ""
    languages: list[str] = Field(default_factory=list)
    screen: str = ""
    viewport: str = ""
    timezone: str = ""
    page_url: str = ""
    platform: str = ""
    touch: bool | None = None
    cookies_enabled: bool | None = None
    color_depth: int | None = None
    connection: str = ""                            # navigator.connection.effectiveType
    device_memory: float | None = None
    hardware_concurrency: int | None = None
    opened_at: str = ""                             # client clock, ISO
    client_hints: dict[str, str] = Field(default_factory=dict)   # navigator.userAgentData, if any


class ScreeningIn(BaseModel):
    question: str = Field(pattern=r"^q[12]$")
    answer: str = Field(pattern=r"^(sim|nao|nao_sei)$")


class MessageIn(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class RatingIn(BaseModel):
    score: int = Field(ge=settings.TRUST_RATING_MIN, le=settings.TRUST_RATING_MAX)


# ----------------------------------------------------------------------------
# app state
# ----------------------------------------------------------------------------
app = FastAPI(title="webchat", docs_url=None, redoc_url=None)
CLIENT = None
LOCKS: dict[str, asyncio.Lock] = {}


def lock_for(sid: str) -> asyncio.Lock:
    # one in-flight turn per session; the page also disables input while waiting
    return LOCKS.setdefault(sid, asyncio.Lock())


def ip_hash(request: Request) -> str:
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    return hashlib.sha256((IP_SALT + ip).encode()).hexdigest()[:16] if ip else ""


def new_session_id() -> str:
    return "web_" + secrets.token_hex(12)


def build_raw_message(sid: str, text: str, kind: str, meta: SessionStart | None, request: Request | None) -> dict:
    """Mimic Meta's message dict so the shared metadata capture stores it unchanged.
    On the first message it carries a 'referral' built from the ad/UTM parameters."""
    raw: dict[str, Any] = {"id": f"web.{sid}.{int(time.time()*1000)}", "timestamp": str(int(time.time())), "type": kind, "channel": "web"}
    if kind == "text":
        raw["text"] = {"body": text}
    else:
        raw["interactive"] = {"type": "web_screening" if text.startswith("screening_") else "web_rating", "reply_id": text}
    if meta is not None:
        q = {k: v[:500] for k, v in meta.query.items()}
        ref = {k: q[k] for k in q if k.startswith("utm_") or k in ("fbclid", "gclid", "ad_id", "adset_id", "campaign_id", "source_id", "ref")}
        if ref:
            raw["referral"] = {
                "source_type": "web_ad",
                "source_id": q.get("utm_content") or q.get("ad_id") or q.get("utm_campaign") or q.get("source_id") or "web",
                "source_url": meta.page_url[:1000],
                "headline": q.get("utm_campaign", ""),
                "body": q.get("utm_content", ""),
                "ctwa_clid": q.get("fbclid", ""),
                "params": ref,
            }
        raw["web"] = page_meta(meta, request)
    return raw


_HINT_HEADERS = ("sec-ch-ua", "sec-ch-ua-mobile", "sec-ch-ua-platform", "sec-ch-ua-platform-version", "sec-ch-ua-model",
                 "x-forwarded-proto", "via", "cf-ipcountry", "x-country")


def page_meta(meta: SessionStart, request: Request | None) -> dict:
    """Everything the browser and the request tell us about the visit, minus the raw IP."""
    q = {k: v[:500] for k, v in meta.query.items()}
    out = {
        "query": q, "referrer": meta.referrer[:1000], "user_agent": meta.user_agent[:500], "language": meta.language[:50],
        "languages": [l[:20] for l in meta.languages[:10]], "screen": meta.screen[:50], "viewport": meta.viewport[:50],
        "timezone": meta.timezone[:80], "page_url": meta.page_url[:1000], "platform": meta.platform[:80],
        "touch": meta.touch, "cookies_enabled": meta.cookies_enabled, "color_depth": meta.color_depth,
        "connection": meta.connection[:30], "device_memory": meta.device_memory, "hardware_concurrency": meta.hardware_concurrency,
        "opened_at": meta.opened_at[:40], "client_hints": {k[:40]: str(v)[:100] for k, v in list(meta.client_hints.items())[:10]},
    }
    if request is not None:
        out["ip_hash"] = ip_hash(request)
        out["accept_language"] = request.headers.get("accept-language", "")[:200]
        out["headers"] = {h: request.headers[h][:200] for h in _HINT_HEADERS if h in request.headers}
    return out


def contacts_for(meta: SessionStart | None, sid: str) -> list:
    return [{"wa_id": sid, "profile": {"name": ""}, "channel": "web"}] if meta else []


# ----------------------------------------------------------------------------
# response shaping
# ----------------------------------------------------------------------------
def web_text(lang: str, key: str) -> str:
    """Shared study texts, with WhatsApp-specific wording adapted to the slider."""
    t = trust_service.get_trust_prompt(lang, key)
    return (t.replace("Use o botão 'Avaliar Agora' abaixo para atualizar sua pontuação.", "Mova o controle abaixo para atualizar sua pontuação.")
             .replace("Use the 'Rate Now' button below to update your score.", "Move the slider below to update your score.")
             .replace("clique no botão abaixo para responder uma pergunta rápida.", "use o controle abaixo para responder uma pergunta rápida.")
             .replace("please tap the button below to answer one quick question.", "please use the slider below to answer one quick question."))


def screening_payload(key: str, lang: str) -> dict:
    q = next(q for q in trust_service.SCREENING_QUESTIONS if q["key"] == key)
    return {"question": key, "prompt": trust_service.get_trust_prompt(lang, q["text_key"]),
            "options": trust_service.screening_options(q, lang)}


def state_of(sid: str) -> dict:
    doc = CLIENT.collection(firebase.COLLECTION).document(sid).get()
    if not doc.exists:
        raise HTTPException(404, "unknown session")
    d = doc.to_dict()
    phase = d.get("conversation_phase", "awaiting_initial_rating")
    lang = d.get("language") or "PT"
    history = [{"role": m["role"], "content": m["content"]} for m in d.get("history", [])]
    pending_rating = None
    pending_screening = None
    if phase == "awaiting_screening" and d.get("intro_sent"):
        q = trust_service.pending_screening_question(d.get("screening") or {})
        if q:
            pending_screening = screening_payload(q["key"], lang)
    elif phase == "awaiting_initial_rating" and d.get("intro_sent"):
        pending_rating = {"kind": "baseline", "prompt": web_text(lang, "baseline")}
    elif phase == "awaiting_check_in_rating":
        pending_rating = {"kind": "check_in", "prompt": web_text(lang, "check_in")}
    screened_out = phase == "screened_out"
    return {"session_id": sid, "phase": phase, "ended": phase == "ended", "history": history, "language": lang,
            "pending_rating": pending_rating, "pending_screening": pending_screening,
            "screened_out": screened_out,
            "closing": trust_service.get_trust_prompt(lang, "screening_closing") if screened_out else None,
            "intro_text": trust_service.get_trust_prompt(lang, "intro"),
            "user_turn_count": d.get("user_turn_count", 0),
            "ratings": [r.get("score") for r in d.get("feeling_array", [])],
            # so a reload of a finished conversation still shows the debrief (it is not part of history)
            "debrief": trust_service.get_trust_prompt(lang, "debrief") if phase == "ended" else None,
            "debriefed": bool(d.get("debriefed_at")),
            # Ad-attribution fields for the Meta Pixel events (never the session id or any answer):
            # 'completed' flips to true the moment the post rating is stored, which is the
            # research-usable outcome; 'creative' is the ad's utm_content from the first visit.
            "completed": d.get("rating_post") is not None,
            "creative": creative_of(d)}


def creative_of(d: dict) -> str | None:
    """utm_content of the visit that created the session, so a resumed page keeps the ad's creative name."""
    raw = d.get("first_message_raw") or {}
    params = (raw.get("referral") or {}).get("params") or {}
    query = (raw.get("web") or {}).get("query") or {}
    return params.get("utm_content") or query.get("utm_content") or None


def shape(sid: str, bot) -> dict:
    """Turn a BotResponse into what the page renders."""
    out = {"messages": list(bot.text_messages), "rating": None, "screening": None}
    if bot.send_trust_flow:
        out["rating"] = {"kind": bot.trust_flow_prompt_key, "prompt": web_text(bot.trust_flow_language, bot.trust_flow_prompt_key)}
    if bot.send_screening:
        out["screening"] = screening_payload(bot.send_screening, bot.trust_flow_language)
    st = state_of(sid)
    out.update({"phase": st["phase"], "ended": st["ended"], "screened_out": st["screened_out"], "user_turn_count": st["user_turn_count"],
                "completed": st["completed"]})
    return out


# ----------------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------------
def render_index() -> str:
    """index.html with the Meta Pixel base code in <head> (or nothing, when META_PIXEL_ID is empty)."""
    html = (WEBCHAT_DIR / "index.html").read_text(encoding="utf-8")
    pixel = META_PIXEL_SNIPPET % {"id": META_PIXEL_ID} if META_PIXEL_ID else ""
    return html.replace("<!--META_PIXEL-->", pixel, 1)


@app.api_route("/", methods=["GET", "HEAD"])
def index():
    return HTMLResponse(render_index(), headers={"Cache-Control": "no-store"})


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"status": "healthy", "version": GIT_SHA or "unknown", "demo": DEMO, "collection": firebase.COLLECTION,
            "screening_enabled": settings.SCREENING_ENABLED, "meta_pixel": bool(META_PIXEL_ID),
            "rating_scale": [settings.TRUST_RATING_MIN, settings.TRUST_RATING_MAX], "check_in_interval": settings.TRUST_CHECK_INTERVAL,
            "debrief_after_turns": settings.DEBRIEF_AFTER_TURNS, "continue_after_debrief": settings.CONTINUE_AFTER_DEBRIEF}


@app.get("/api/text")
def ui_text():
    return {**UI_TEXT, "rating_min": settings.TRUST_RATING_MIN, "rating_max": settings.TRUST_RATING_MAX}


@app.post("/api/session")
async def start_session(body: SessionStart, request: Request):
    """Create a new session, or resume one the browser remembers.

    A brand-new participant gets the intro + initial rating prompt, exactly
    like the first WhatsApp message: the service assigns a random condition,
    stores the page metadata as the 'first raw message', and returns the intro.
    """
    sid = body.session_id
    if sid and CLIENT.collection(firebase.COLLECTION).document(sid).get().exists:
        firebase.record_visit(CLIENT, sid, page_meta(body, request))
        st = state_of(sid); st["resumed"] = True
        return st
    sid = new_session_id()
    async with lock_for(sid):
        # The document is created here, before any screening, so every visitor
        # is recorded with their ad / page metadata even if they never qualify.
        bot = await conversation_service.handle_incoming_message(
            CLIENT, sid, "[abrir página]", "text",
            raw_message=build_raw_message(sid, "[abrir página]", "text", body, request),
            contacts=contacts_for(body, sid), allow_dev_commands=True)
    firebase.record_visit(CLIENT, sid, page_meta(body, request))
    st = state_of(sid); st["resumed"] = False; st["intro"] = shape(sid, bot)
    log.info("new session %s variant=%s", sid, CLIENT.collection(firebase.COLLECTION).document(sid).get().to_dict().get("prompt_variant"))
    return st


@app.get("/api/session/{sid}")
def get_session(sid: str):
    return state_of(sid)


@app.post("/api/session/{sid}/message")
async def post_message(sid: str, body: MessageIn, request: Request):
    st = state_of(sid)
    text = body.text.strip()
    if text.lower() in DEV_COMMANDS:
        # Developer command: bypass the phase guards; the shared service handles it.
        async with lock_for(sid):
            bot = await conversation_service.handle_incoming_message(
                CLIENT, sid, text, "text", raw_message=None, contacts=[], allow_dev_commands=True)
        if text.lower() == "/reset":
            # the service deleted the document; tell the page to forget the session and reload
            return {"messages": list(bot.text_messages), "rating": None, "phase": "reset", "ended": False, "user_turn_count": 0, "reset": True}
        return shape(sid, bot)
    if st["ended"]:
        return {"messages": [trust_service.get_trust_prompt(st["language"], "conversation_ended")], "rating": None, "screening": None, "phase": "ended", "ended": True, "screened_out": False, "user_turn_count": st["user_turn_count"]}
    if st["screened_out"]:
        return {"messages": [st["closing"]], "rating": None, "screening": None, "phase": "screened_out", "ended": False, "screened_out": True, "user_turn_count": 0}
    if st["pending_screening"]:
        # Text while a screening question is open: re-offer the buttons (the service would say "answer sim/não").
        return {"messages": [], "rating": None, "screening": st["pending_screening"], "phase": st["phase"], "ended": False, "screened_out": False, "user_turn_count": 0}
    if st["pending_rating"]:
        # WhatsApp would answer "use the button"; on the web the widget is right there, so just re-show it.
        return {"messages": [], "rating": st["pending_rating"], "screening": None, "phase": st["phase"], "ended": False, "screened_out": False, "user_turn_count": st["user_turn_count"]}
    async with lock_for(sid):
        try:
            bot = await conversation_service.handle_incoming_message(
                CLIENT, sid, text, "text", raw_message=build_raw_message(sid, text, "text", None, request), contacts=[], allow_dev_commands=True)
        except Exception as e:
            # Typically the model call (API error, bad parameter, outage). Nothing has been
            # stored for this turn, so the participant can simply resend.
            log.error("turn failed for %s: %s: %s", sid, type(e).__name__, str(e)[:300])
            raise HTTPException(503, UI_TEXT["error"])
    return shape(sid, bot)


@app.post("/api/session/{sid}/screening")
async def post_screening(sid: str, body: ScreeningIn, request: Request):
    st = state_of(sid)
    if st["screened_out"]:
        return {"messages": [st["closing"]], "rating": None, "screening": None, "phase": "screened_out", "ended": False, "screened_out": True, "user_turn_count": 0}
    if not st["pending_screening"] or st["pending_screening"]["question"] != body.question:
        raise HTTPException(409, "that screening question is not pending")
    reply_id = f"screening_{body.question}_{body.answer}"
    async with lock_for(sid):
        bot = await conversation_service.handle_incoming_message(
            CLIENT, sid, reply_id, "interactive", raw_message=build_raw_message(sid, reply_id, "interactive", None, request), contacts=[], allow_dev_commands=True)
    return shape(sid, bot)


@app.post("/api/session/{sid}/rating")
async def post_rating(sid: str, body: RatingIn, request: Request):
    st = state_of(sid)
    if st["ended"]:
        return {"messages": [], "rating": None, "screening": None, "phase": "ended", "ended": True, "screened_out": False, "user_turn_count": st["user_turn_count"]}
    if not st["pending_rating"]:
        raise HTTPException(409, "no rating is pending")
    reply_id = f"rating_{body.score}"
    async with lock_for(sid):
        bot = await conversation_service.handle_incoming_message(
            CLIENT, sid, reply_id, "interactive", raw_message=build_raw_message(sid, reply_id, "interactive", None, request), contacts=[], allow_dev_commands=True)
    return shape(sid, bot)


# ----------------------------------------------------------------------------
# startup
# ----------------------------------------------------------------------------
def configure():
    global CLIENT
    if _LOADED:
        log.info("loaded env files: %s", ", ".join(map(str, _LOADED)))
    log.info("Firestore collection: %s", firebase.COLLECTION)
    if DEMO:
        from webchat.fake_firestore import FakeFirestore
        CLIENT = FakeFirestore()

        async def canned(messages, system_prompt):
            await asyncio.sleep(0.6)
            n = sum(1 for m in messages if m["role"] == "user")
            return ["O que te faz pensar isso?", "Pode me contar mais sobre essa experiência?", "Como você acha que outras pessoas veem essa questão?",
                    "O que te ajudaria a confiar mais?", "Entendo. E o que você já ouviu sobre as auditorias?", "Obrigado por compartilhar isso.",
                    "Há algo mais que você gostaria de acrescentar?", "Entendi."][(n - 1) % 8]
        openai_client.get_ai_response = canned
        log.warning("DEMO MODE: in-memory store and canned replies; nothing is saved")
        return
    if firebase.COLLECTION == "conversations":
        log.error("Refusing to run against the WhatsApp collection. Set FIRESTORE_COLLECTION=web_conversations (or another name) in webchat/.env")
        sys.exit(2)
    if not (os.getenv("FIREBASE_CREDS_PATH") or os.getenv("FIREBASE_CREDS_JSON")):
        log.error("No Firebase credentials: set FIREBASE_CREDS_PATH or FIREBASE_CREDS_JSON in webchat/.env"); sys.exit(2)
    if not os.getenv("OPENAI_API_KEY"):
        log.error("OPENAI_API_KEY is not set in webchat/.env"); sys.exit(2)
    CLIENT = firebase.init_firestore()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--host", default=HOST)
    args = ap.parse_args()
    configure()
    log.info("webchat serving on http://%s:%d", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning", proxy_headers=True, forwarded_allow_ips="*")


if __name__ == "__main__":
    main()
