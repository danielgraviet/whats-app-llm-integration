"""Shared fixtures: in-memory Firestore, canned LLM, web-study defaults.

Run from the project root:  python -m pytest tests -q
No credentials or network needed.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Web-study defaults (same as webchat/app.py) and no real clients.
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("TRUST_RATING_MIN", "0")
os.environ.setdefault("TRUST_RATING_MAX", "100")
os.environ.setdefault("TRUST_CHECK_INTERVAL", "6")
os.environ.setdefault("DEBRIEF_AFTER_TURNS", "6")
os.environ.setdefault("CONTINUE_AFTER_DEBRIEF", "true")
os.environ.setdefault("FIRESTORE_COLLECTION", "test_conversations")

from webchat.fake_firestore import install_transactional_shim  # noqa: E402
install_transactional_shim()

import pytest  # noqa: E402

from integrations import openai_client  # noqa: E402
from webchat.fake_firestore import FakeFirestore  # noqa: E402


@pytest.fixture(autouse=True)
def canned_llm(monkeypatch):
    seen = []

    async def fake(messages, system_prompt):
        seen.append(system_prompt)
        return "resposta do modelo"

    monkeypatch.setattr(openai_client, "get_ai_response", fake)
    return seen


@pytest.fixture
def client():
    return FakeFirestore()
