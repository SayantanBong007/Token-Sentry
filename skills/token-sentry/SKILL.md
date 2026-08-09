---
name: Integrate Token-Sentry
description: Instructs the AI agent on how to configure OpenAI SDKs or Agentic Frameworks (LangGraph, CrewAI, AutoGen) to route through the local Token-Sentry API Gateway.
---

# Token-Sentry Integration Guidelines

When the user asks to integrate, use, or route their code through **Token-Sentry**, follow these exact instructions:

## 1. Verify Prerequisites
Inform the user that the Token-Sentry Docker stack must be running locally. (Usually via `docker-compose up -d` in the Token-Sentry directory). The default proxy port is `8000`.

## 2. Python OpenAI SDK Configuration
Whenever you write or modify a Python script that uses the `openai` SDK, you must override the `base_url` to point to the local gateway. The API key is ignored because Token-Sentry handles Groq/Gemini authentication upstream using its own `.env` file.

**Do this:**
```python
from openai import OpenAI

# Token-Sentry local gateway
client = OpenAI(
    base_url="http://localhost:8000/v1", 
    api_key="token-sentry-proxy" 
)
```

## 3. Passing the Session ID (Crucial for Infinite Memory)
If the user is building a **Chat Application** where the LLM needs to remember previous turns without resending the whole history, they MUST pass an `X-Session-ID` header in their request.

**Example implementation for chat apps:**
```python
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": user_input}],
    extra_headers={
        "X-Session-ID": "unique-user-or-session-id"
    }
)
```

## 4. Agentic Frameworks (Passthrough Mode)
If the user is building an Agent with **LangGraph**, **CrewAI**, or **AutoGen**, these frameworks manage their own conversational state. 
- **DO NOT** pass an `X-Session-ID` header.
- Token-Sentry will operate in "Passthrough Mode", simply intercepting the large context, compressing it, and returning the result without trying to manage the state.

**Example for Langchain/LangGraph:**
```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    model="llama-3.3-70b-versatile",
    openai_api_base="http://localhost:8000/v1",
    openai_api_key="token-sentry"
)
```
