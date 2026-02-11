# this file should be able to take in a user message, which could contain a long conversation history,
# ask the LLM model the question
# return response.

# ideas
# literal prompt template that is interchangable.
# have customizeable system prompts that we can swap out.
# have a config to easly switch models within the open ai ecosystem, temperature, etc.

# how should I handle latentcy? what if a whats app user spams messages quickly?

import openai

from config import settings

client = openai.AsyncOpenAI(
    api_key=settings.OPENAI_API_KEY
)  # model level, initialized once


async def get_ai_response(messages: list[dict], system_prompt: str) -> str:
    """Get response from LLM.

    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."} dicts

    Returns:
        AI-generated response text
    """

    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "system", "content": system_prompt}] + messages,
    )

    return response.choices[0].message.content
