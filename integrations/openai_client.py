import openai
import io

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

async def transcribe_audio(audio_bytes: bytes) -> str:
    # is it smart to add a try catch block here? or should that be done elsewhere. I was thinking we try creating this new text, and if not default to "error"
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = "audio.ogg"
    response = await client.audio.transcriptions.create(
        model='whisper-1',
        file=audio_file
    )
    return response.text