"""Meta Pixel events in a real browser: walk the web study in headless Chrome
and record every fbq() call.

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


@pytest.fixture(scope="module")
def base_url():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "META_PIXEL_ID": "123456", "WEBCHAT_DEMO": "1"}
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
    """The input stays enabled while a turn is in flight, so wait for the typing indicator to
    go and the bubble count to stop changing (bot replies arrive 350 ms apart)."""
    page.wait_for_function("() => !document.querySelector('.typing')", timeout=20000)
    page.wait_for_function("""() => new Promise(res => {
        const n = () => document.querySelectorAll('.msg, .rate, .screen, .sys').length; const a = n();
        setTimeout(() => res(!document.querySelector('.typing') && n() === a), 900); })""", timeout=20000)


def answer(page, label):
    wait_idle(page)
    page.locator(".screen:not(.done) button", has_text=label).first.click()


def rate(page, value):
    wait_idle(page)
    box = page.locator(".rate:not(.done)").last
    box.wait_for(timeout=10000)
    box.locator("input[type=range]").evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles: true})); el.dispatchEvent(new Event('change', {bubbles: true})); }", value)
    box.locator("button.confirm").click()


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
    rate(page, 35)
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
    page.wait_for_selector(".rate:not(.done)", timeout=15000); wait_idle(page)
    assert events(page) == BASE_EVENTS, "the check-in prompt itself fires nothing"
    rate(page, 60); wait_idle(page)
    assert events(page)[2:] == [["trackCustom", "PesquisaConcluida", {"criativo": "skeptical_frame"}]], "creative remembered from the first visit"

    page.reload(wait_until="networkidle")
    say(page, "ainda aqui")
    assert events(page) == BASE_EVENTS, "after completion nothing fires again"

    sid = page.evaluate("localStorage.getItem('pesquisa_session_id')")
    keys = page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('fb_')).sort()")
    assert keys == sorted([f"fb_ConversaIniciada_{sid}", f"fb_PesquisaConcluida_{sid}"])

    # a fresh session (?new=1) fires again, with its own creative
    page.goto(f"{base_url}/?new=1&utm_content=open_question", wait_until="networkidle")
    qualify(page); rate(page, 50); say(page, "oi")
    assert events(page)[2:] == [["trackCustom", "ConversaIniciada", {"criativo": "open_question"}]]

    # no utm_content: event without parameters
    page.goto(f"{base_url}/?new=1", wait_until="networkidle")
    qualify(page); rate(page, 50); say(page, "oi")
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
    qualify(page); rate(page, 20); say(page, "oi")
    queue = page.evaluate("window.fbq && window.fbq.queue ? window.fbq.queue.map(a => Array.from(a)) : null")
    assert queue is not None and ["trackCustom", "ConversaIniciada", {"criativo": "curiosity_frame"}] in queue
    assert errors == []
    ctx.close()


def test_without_pixel_id_page_has_no_fbq(browser):
    """META_PIXEL_ID empty: no base code at all, custom events are skipped silently."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    env = {**os.environ, "META_PIXEL_ID": "", "WEBCHAT_DEMO": "1"}
    proc = subprocess.Popen([os.environ.get("WEBCHAT_PYTHON", sys.executable), "webchat/app.py", "--demo", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1); break
            except Exception:
                time.sleep(0.2)
        ctx = browser.new_context()
        errors = []
        page = ctx.new_page(); page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/?utm_content=open_question", wait_until="networkidle")
        qualify(page); rate(page, 50); say(page, "oi")
        assert page.evaluate("typeof window.fbq") == "undefined"
        assert errors == []
        ctx.close()
    finally:
        proc.terminate(); proc.wait(timeout=10)
