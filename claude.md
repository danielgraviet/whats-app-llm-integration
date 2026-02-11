# Claude Code Guidelines

## About the Developer

Junior engineer focused on learning. Prefers understanding concepts before implementation.

## Communication Style

- **Explain before coding** - Always explain the reasoning and tradeoffs before writing any code. Ask "want me to make these changes, or do you want to try it?" after explaining.
- **Ask clarifying questions** - Gather context before starting work. Don't assume.
- **Use tables for comparisons** - When explaining tradeoffs or options, use markdown tables.
- **Keep explanations concise** - Use bullet points, code snippets, and clear headers. Avoid walls of text.

## Code Preferences

- Let the user implement things themselves when possible after explaining
- Show "before and after" code snippets when explaining fixes
- Reference specific line numbers when discussing existing code
- Explain the "why" not just the "what"

## Project Structure

```
python-whatsapp/
├── main.py              # FastAPI routes only
├── config.py            # Centralized settings
├── database/
│   ├── firebase.py      # Firestore operations
│   └── models.py        # Pydantic models
├── integrations/
│   └── openai_client.py # LLM API calls
└── services/            # Business logic (future)
```

## Tech Stack

- FastAPI + uvicorn
- Firebase Firestore
- OpenAI API
- WhatsApp Business API (Meta)

## Key Patterns

- Module-level client initialization for API clients (OpenAI, Firestore)
- Background tasks for async processing (webhook responds instantly, AI processes after)
- Config pulled from `settings` object, not scattered `os.getenv()` calls
