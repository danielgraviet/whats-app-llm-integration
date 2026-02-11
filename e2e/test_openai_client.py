"""
E2E test for OpenAI client.

Run from project root:
    uv run pytest e2e/ -v -s
"""

import pytest

from integrations.openai_client import get_ai_response


@pytest.mark.asyncio
async def test_simple_message():
    messages = [{"role": "user", "content": "Say hello in exactly 5 words."}]

    print("Sending test message to OpenAI...")
    response = await get_ai_response(messages)
    print(f"Response: {response}")
