---
name: Integrate Token-Sentry
description: Instructs the AI agent on how to configure OpenAI SDKs or Agentic Frameworks (LangGraph, CrewAI, AutoGen) to route through the local Token-Sentry API Gateway, including session memory, fallback providers, and analytics.
---

# Token-Sentry Integration Guidelines

When the user asks to integrate, use, or route their code through **Token-Sentry**, follow these exact instructions:

## 1. Verify Prerequisites

Inform the user that the Token-Sentry Docker stack must be running locally:
```bash
docker-compose up -d
```
The default proxy port is **`8000`**. The analytics dashboard runs on port **`3000`** (started separately with `cd dashboard && npm run dev`).

## 2. Python OpenAI SDK Configuration

Whenever you write or modify a Python script that uses the `openai` SDK, override the `base_url` to point to the local gateway. The `api_key` is not needed — Token-Sentry authenticates upstream using its own `.env` keys.

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"  # Token-Sentry handles upstream auth
)
```

## 3. Passing the Session ID (Chat Apps — Stateful Mode)

If the user is building a **Chat Application** where the LLM needs to remember previous turns, they MUST pass an `X-Session-ID` header. Token-Sentry will:
- Load the full conversation history from Redis
- Recall the top-5 semantically relevant past chunks from ChromaDB
- Automatically compress the history when it crosses the token watermark

```python
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": user_input}],
    stream=True,
    extra_headers={
        "X-Session-ID": "unique-user-or-session-id"
    }
)
for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")
```

## 4. Agentic Frameworks (Passthrough Mode)

If the user is building an Agent with **LangGraph**, **CrewAI**, **AutoGen**, or **AutoGPT**, these frameworks manage their own conversational state.

- **DO NOT** pass an `X-Session-ID` header
- Token-Sentry will operate in **Passthrough Mode** — it only compresses the incoming payload if it's too large, then forwards it unchanged
- The agent framework handles all memory management

**LangChain / LangGraph:**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    openai_api_base="http://localhost:8000/v1",
    openai_api_key="not-needed"
)
```

**Raw OpenAI SDK (agent mode):**
```python
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

# No X-Session-ID — agent manages its own state
response = client.chat.completions.create(
    model="gpt-4o",  # automatically mapped to llama-3.3-70b-versatile
    messages=agent_state["messages"],
)
```

## 5. Model Name Mapping

Token-Sentry automatically maps OpenAI model names to the configured provider models. Clients can use OpenAI names and they will be silently routed:

| Client requests | Token-Sentry routes to |
|---|---|
| `gpt-4o` | `PRIMARY_MAIN_MODEL` (e.g. llama-3.3-70b-versatile) |
| `gpt-4o-mini` | `PRIMARY_SUMMARIZER_MODEL` (e.g. llama-3.1-8b-instant) |
| `gpt-3.5-turbo` | `PRIMARY_SUMMARIZER_MODEL` |
| Exact model name | Passed through unchanged |

## 6. Provider Fallbacks

Token-Sentry automatically fails over to the fallback provider (configured in `.env`) if the primary returns a rate-limit error. **This is transparent to the client** — no code changes needed.

To configure providers in `.env`:
```env
PRIMARY_PROVIDER_URL=https://api.groq.com/openai/v1
PRIMARY_API_KEY=gsk_...
PRIMARY_MAIN_MODEL=llama-3.3-70b-versatile

FALLBACK_PROVIDER_URL=https://integrate.api.nvidia.com/v1
FALLBACK_API_KEY=nvapi-...
FALLBACK_MAIN_MODEL=meta/llama-3.3-70b-instruct
```

## 7. Checking Metrics & Health

```python
import requests

# Health check
health = requests.get("http://localhost:8000/health").json()
print(health)  # {"status": "ok", "model": "llama-3.3-70b-versatile", ...}

# Live analytics
metrics = requests.get("http://localhost:8000/api/metrics").json()
print(f"Tokens saved: {metrics['tokens_saved']}")
print(f"Cost saved:   ${metrics['cost_saved_usd']}")
print(f"Fallbacks:    {metrics['fallback_events']}")
```

## 8. Response Headers to Inspect

Every response from Token-Sentry includes these headers:

| Header | Values | Meaning |
|---|---|---|
| `X-Intent` | `simple` or `complex` | Which model was actually used |
| `X-Compressed` | `true` or `false` | Whether history was compressed |
| `X-Mode` | `stateful` or `passthrough` | Which operating mode was used |
| `X-Session-ID` | session ID string | The session that was used |
