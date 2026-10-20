"""The web study in a real browser (headless Chrome): the phase-2 flow (two
trust questions with seven buttons, high-trust filter, Encerrar conversa with
the optional exit questions, inactivity) and the Meta Pixel events, recording
every fbq() call.

Needs Playwright and a Chrome/Chromium (skipped otherwise):

    pip install playwright            # then either `playwright install chromium`
    python -m pytest e2e/test_webchat_pixel_browser.py -v -s

A stub `fbq` is installed before any page script runs, so Meta's base code
sees window.fbq already defined and never loads fbevents.js; requests to
facebook domains are blocked as a second guard. Nothing reaches Meta.

The demo server is started on a free port with META_PIXEL_ID=123456.
WEBCHAT_PYTHON selects the interpreter for it (default: this one).
"""
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
STUB = "window.__fb = []; window.fbq = function(){ window.__fb.push(Array.from(arguments)); };"


def start_server(**env_overrides):
    """A demo server on a free port; returns (process, url)."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "META_PIXEL_ID": "123456", "WEBCHAT_DEMO": "1", **env_overrides}
    proc = subprocess.Popen([os.environ.get("WEBCHAT_PYTHON", sys.executable), "webchat/app.py", "--demo", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            urllib.request.urlopen(url + "/health", timeout=1); break
        except Exception:
            time.sleep(0.2)
    else:
        proc.kill(); pytest.fail("demo server did not start")
    return proc, url


@pytest.fixture(scope="module")
def base_url():
    proc, url = start_server()
    yield url
    proc.terminate(); proc.wait(timeout=10)


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = None
        for kw in ({"channel": "chrome"}, {}):
            try:
                b = p.chromium.launch(headless=True, **kw); break
            except Exception:
                continue
        if b is None:
            pytest.skip("no Chrome/Chromium for Playwright")
        yield b
        b.close()


# ---- page driving ---------------------------------------------------------
def wait_idle(page):
    """Wait for the typing indicator to go and the bubble count to stop changing
    (bot replies arrive 350 ms apart)."""
    page.wait_for_function("() => !document.querySelector('.typing')", timeout=20000)
    page.wait_for_function("""() => new Promise(res => {
        const n = () => document.querySelectorAll('.msg, .screen, .sys, #sheet.show').length; const a = n();
        setTimeout(() => res(!document.querySelector('.typing') && n() === a), 900); })""", timeout=20000)


def answer(page, label):
    wait_idle(page)
    page.locator(".screen:not(.done) button", has_text=label).first.click()


def rate(page, system, urnas):
    """Answer the two trust questions in the sheet: tap the numbered button, then Confirmar."""
    wait_idle(page)
    sheet = page.locator("#sheet.show"); sheet.wait_for(timeout=10000)
    for n, value in enumerate((system, urnas), start=1):
        assert sheet.locator(".progress").inner_text().lower() == f"pergunta {n} de 2"
        assert sheet.locator("button.confirm").is_disabled(), "nothing pre-selected"
        sheet.locator(".opts button", has=page.locator(".n", has_text=str(value))).first.click()
        assert sheet.locator("button.confirm").inner_text().startswith("Confirmar: ")
        sheet.locator("button.confirm").click()
    page.wait_for_function("() => !document.querySelector('#sheet.show')", timeout=10000)


def say(page, text):
    wait_idle(page)
    page.fill("#input", text)
    page.press("#input", "Enter")
    wait_idle(page)


def qualify(page):
    page.wait_for_selector(".screen", timeout=10000)
    answer(page, "Sim"); answer(page, "Sim")


def events(page):
    return page.evaluate("window.__fb")


BASE_EVENTS = [["init", "123456"], ["track", "PageView"]]


# ---- tests ------------------------------------------------------------------
def test_full_walk_fires_each_custom_event_once(base_url, browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(STUB)
    ctx.route("**/*facebook*/**", lambda r: r.abort())
    errors = []
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{base_url}/?utm_source=fb&utm_content=skeptical_frame&fbclid=abc", wait_until="networkidle")
    qualify(page)
    rate(page, 3, 4)
    wait_idle(page)
    assert events(page) == BASE_EVENTS, "PageView only, until the first message"

    say(page, "Acho que funciona")
    assert events(page)[2:] == [["trackCustom", "ConversaIniciada", {"criativo": "skeptical_frame"}]]

    # reload mid-conversation from a URL without parameters: PageView again, nothing custom
    page.reload(wait_until="networkidle"); wait_idle(page)
    assert events(page) == BASE_EVENTS
    say(page, "segunda mensagem")
    assert events(page) == BASE_EVENTS, "second message must not re-fire ConversaIniciada"

    for i in range(3, 7):
        say(page, f"mensagem {i}")
    page.wait_for_selector("#sheet.show", timeout=15000); wait_idle(page)
    assert events(page) == BASE_EVENTS, "the check-in prompt itself fires nothing"
    rate(page, 4, 5); wait_idle(page)
    assert events(page)[2:] == [["trackCustom", "PesquisaConcluida", {"criativo": "skeptical_frame"}]], "creative remembered from the first visit"

    page.reload(wait_until="networkidle")
    say(page, "ainda aqui")
    assert events(page) == BASE_EVENTS, "after completion nothing fires again"

    sid = page.evaluate("localStorage.getItem('pesquisa_session_id')")
    keys = page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('fb_')).sort()")
    assert keys == sorted([f"fb_ConversaIniciada_{sid}", f"fb_PesquisaConcluida_{sid}"])

    # a fresh session (?new=1) fires again, with its own creative
    page.goto(f"{base_url}/?new=1&utm_content=open_question", wait_until="networkidle")
    qualify(page); rate(page, 4, 4); say(page, "oi")
    assert events(page)[2:] == [["trackCustom", "ConversaIniciada", {"criativo": "open_question"}]]

    # no utm_content: event without parameters
    page.goto(f"{base_url}/?new=1", wait_until="networkidle")
    qualify(page); rate(page, 4, 4); say(page, "oi")
    assert events(page)[2:] == [["trackCustom", "ConversaIniciada", {}]]

    # screened out: PageView only
    page.goto(f"{base_url}/?new=1&utm_content=voice_matters", wait_until="networkidle")
    page.wait_for_selector(".screen", timeout=10000)
    answer(page, "Não"); page.wait_for_selector(".sys", timeout=10000)
    assert events(page) == BASE_EVENTS

    assert errors == []
    ctx.close()


def test_blocked_pixel_script_does_not_break_the_page(base_url, browser):
    """Ad blocker case: fbevents.js never loads, Meta's own queue stub stands in."""
    ctx = browser.new_context()
    ctx.route("**/*facebook*/**", lambda r: r.abort())
    errors = []
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{base_url}/?utm_content=curiosity_frame", wait_until="networkidle")
    qualify(page); rate(page, 2, 2); say(page, "oi")
    queue = page.evaluate("window.fbq && window.fbq.queue ? window.fbq.queue.map(a => Array.from(a)) : null")
    assert queue is not None and ["trackCustom", "ConversaIniciada", {"criativo": "curiosity_frame"}] in queue
    assert errors == []
    ctx.close()


def test_without_pixel_id_page_has_no_fbq(browser):
    """META_PIXEL_ID empty: no base code at all, custom events are skipped silently."""
    proc, url = start_server(META_PIXEL_ID="")
    try:
        ctx = browser.new_context()
        errors = []
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"{url}/?utm_content=open_question", wait_until="networkidle")
        qualify(page); rate(page, 4, 4); say(page, "oi")
        assert page.evaluate("typeof window.fbq") == "undefined"
        assert errors == []
        ctx.close()
    finally:
        proc.terminate(); proc.wait(timeout=10)


# ---- phase-2 flow ------------------------------------------------------------
def _page(browser, errors):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(STUB); ctx.route("**/*facebook*/**", lambda r: r.abort())
    page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page


def bubbles(page, who="bot"):
    """Bubble texts without the timestamp line."""
    return page.evaluate("""(who) => [...document.querySelectorAll(`.msg.${who}:not(.typing)`)]
        .map(d => { const c = d.cloneNode(true); c.querySelector('.t')?.remove(); return c.textContent; })""", who)


def test_header_questions_filter_and_answers_echo(base_url, browser):
    errors = []; ctx, page = _page(browser, errors)
    page.goto(f"{base_url}/?new=1", wait_until="networkidle")
    assert page.locator("header h1").inner_text() == "Pesquisa acadêmica" and page.title() == "Pesquisa acadêmica"
    assert not page.locator("#end").is_visible(), "no end button before the conversation starts"
    qualify(page); wait_idle(page)
    assert bubbles(page)[-1] == "Antes de começar, responda duas perguntas rápidas."
    sheet = page.locator("#sheet.show"); sheet.wait_for()
    assert page.locator("#input").is_disabled()
    labels = sheet.locator(".opts button .l").all_inner_texts()
    assert labels == ["Não confio nada", "Confio muito pouco", "Confio pouco", "Confio mais ou menos", "Confio muito", "Confio quase totalmente", "Confio totalmente"]
    assert "sistema eleitoral brasileiro como um todo" in sheet.locator(".q").inner_text()
    # change of mind before confirming is allowed; the confirm button names the choice
    tap = lambda n: sheet.locator(".opts button", has=page.locator(".n", has_text=str(n))).first.click()
    tap(3); tap(5)
    assert sheet.locator("button.confirm").inner_text() == "Confirmar: Confio muito"
    sheet.locator("button.confirm").click()
    assert "urnas eletrônicas" in sheet.locator(".q").inner_text()
    # high trust on question 2: closing message, session over
    tap(7); sheet.locator("button.confirm").click()
    wait_idle(page)
    me = bubbles(page, "me")[-1]
    assert "Suas respostas" in me and "1. Confio muito ✓" in me and "2. Confio totalmente ✓" in me
    assert bubbles(page)[-1].startswith("Obrigado pela sua resposta! Nesta etapa")
    assert page.locator("#input").is_disabled() and not page.locator("#end").is_visible()
    assert errors == []; ctx.close()


def test_end_button_exit_rating_and_after_rating(base_url, browser):
    errors = []; ctx, page = _page(browser, errors)
    page.goto(f"{base_url}/?new=1", wait_until="networkidle")
    qualify(page); rate(page, 3, 4); wait_idle(page)
    assert page.locator("#end").is_visible() and page.locator("#end").inner_text() == "Encerrar conversa"
    say(page, "primeira"); say(page, "segunda")
    page.click("#end"); wait_idle(page)
    answer(page, "Continuar conversando"); wait_idle(page)          # changed their mind: nothing happens
    assert page.locator("#input").is_enabled() and page.locator("#end").is_visible()
    page.click("#end"); answer(page, "Sim, encerrar"); wait_idle(page)
    card = page.locator(".screen:not(.done)").last
    assert card.locator(".q").inner_text() == "Antes de sair, você pode responder duas perguntas rápidas? É opcional."
    answer(page, "Responder")
    rate(page, 2, 2); wait_idle(page)
    assert bubbles(page)[-1].startswith("Obrigado por participar desta pesquisa.")
    assert page.locator("#input").is_disabled() and not page.locator("#end").is_visible()
    assert page.locator(".sys").last.inner_text().startswith("Esta conversa foi encerrada")
    # reload: still ended, debrief shown again
    page.goto(f"{base_url}/", wait_until="networkidle"); wait_idle(page)     # resume (no ?new=1)
    assert page.locator("#input").is_disabled() and bubbles(page)[-1].startswith("Obrigado por participar")

    # pressed right after the baseline questions: straight to the debrief, no optional questions
    page.goto(f"{base_url}/?new=1", wait_until="networkidle")
    qualify(page); rate(page, 3, 4); wait_idle(page)
    page.click("#end"); answer(page, "Sim, encerrar"); wait_idle(page)
    assert page.locator(".screen:not(.done)").count() == 0 and bubbles(page)[-1].startswith("Obrigado por participar")

    # Pular e encerrar
    page.goto(f"{base_url}/?new=1", wait_until="networkidle")
    qualify(page); rate(page, 3, 4); say(page, "oi")
    page.click("#end"); answer(page, "Sim, encerrar"); answer(page, "Pular e encerrar"); wait_idle(page)
    assert bubbles(page)[-1].startswith("Obrigado por participar") and page.locator("#input").is_disabled()
    assert errors == []; ctx.close()


def test_check_in_at_six_and_inactivity_timer(browser):
    proc, url = start_server(WEBCHAT_INACTIVITY_MINUTES="0.03")     # 1.8 s
    try:
        errors = []; ctx, page = _page(browser, errors)
        page.goto(f"{url}/?new=1", wait_until="networkidle")
        qualify(page); rate(page, 3, 4)
        for i in range(6):
            say(page, f"mensagem {i}")
        page.wait_for_selector("#sheet.show", timeout=15000); wait_idle(page)
        assert bubbles(page)[-1] == "Antes de continuar, responda mais duas perguntas rápidas."
        assert not page.locator("#end").is_visible(), "no end button while the questions are open"
        rate(page, 4, 5); wait_idle(page)
        assert page.locator("#input").is_enabled() and page.locator("#end").is_visible()
        # idle: the page ends the conversation by itself
        page.wait_for_function("() => document.querySelector('#input').disabled", timeout=15000); wait_idle(page)
        texts = page.locator(".sys").all_inner_texts()
        assert any(t.startswith("A conversa foi encerrada por inatividade") for t in texts)
        assert bubbles(page)[-1].startswith("Obrigado por participar")
        assert errors == []; ctx.close()
    finally:
        proc.terminate(); proc.wait(timeout=10)
