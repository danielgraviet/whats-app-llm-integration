"""
E2E test for OpenAI client.

Run from project root:
    uv run pytest e2e/ -v -s
"""

import pytest

from integrations import openai_client


@pytest.mark.asyncio
async def test_simple_message():
    messages = [{"role": "user", "content": "Say hello in exactly 5 words."}]

    print("Sending test message to OpenAI...")
    response = await openai_client.get_ai_response(messages)
    print(f"Response: {response}")
    
@pytest.mark.asyncio
async def test_audio_message():
    with open("e2e/sample.ogg", "rb") as f:
        audio_bytes = f.read()
    
    transcript = await openai_client.transcribe_audio(audio_bytes)
    print(transcript)
    assert isinstance(transcript, str)
    assert len(transcript) > 0
