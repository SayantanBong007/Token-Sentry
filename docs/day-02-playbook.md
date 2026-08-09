# 📓 Token-Sentry Playbook — Day 2
### Date: 2026-08-07 | Topic: Session Memory + Context Compression

---

## 🎯 What Was the Goal Today?

Day 1 gave us a **stateless proxy** — it forwarded messages but forgot everything.

Day 2 makes Token-Sentry **smart**:
1. **Remember conversations** in Redis (for chat apps)
2. **Compress old history** when conversations get too long (for both chat + agents)
3. **Support agentic systems** (LangGraph, CrewAI, AutoGen) without interfering with their own state

---

## 🧠 The Core Problem We're Solving

### Without memory (Day 1 behaviour):
```
Turn 1:  You: "My name is Sayantan"       → Groq replies
Turn 10: You: "What's my name?"           → Groq: "I don't know" ❌
```

Every request was treated as a brand new conversation. Groq had no idea
what was said before.

### With memory (Day 2):
```
Turn 1:  You: "My name is Sayantan"
         → saved to Redis ✅

Turn 10: You: "What's my name?"
         → loaded 10 turns from Redis
         → sent all 10 to Groq
         → Groq: "Your name is Sayantan" ✅
```

### When conversations get TOO long:
```
Turn 50: 8,000 tokens in history — over our 4,000 limit
         → compress turns 1-47 into a summary card
         → send [summary + last 3 raw turns] to Groq
         → Groq still knows the whole context ✅ (just in condensed form)
```

---

## 🏗️ Two Operating Modes

This is the most important concept in Day 2.

### Mode 1: STATEFUL (Chat Apps)
**Triggered by:** `X-Session-ID` header in the request

Token-Sentry is the memory manager. It stores everything in Redis.

```
Your App  ──── POST /v1/chat/completions ────►  Token-Sentry
               X-Session-ID: chat-abc123             │
                                                     │ load history from Redis
                                                     │ append new message
                                                     │ compress if over limit
                                                     ▼
                                                   Groq API
                                                     │
                                              save reply to Redis
                                                     │
               ◄─────────────── response ────────────┘
```

### Mode 2: PASSTHROUGH (Agentic Systems)
**Triggered by:** No `X-Session-ID` header

The agent (LangGraph, CrewAI, etc.) manages its own state.
Token-Sentry just compresses if needed and forwards.

```
LangGraph ──── POST /v1/chat/completions ────►  Token-Sentry
               (no session ID)                       │
               messages: [FULL STATE HERE]           │ compress if over limit
                                                     ▼
                                                   Groq API
                                                     │
               ◄─────────────── response ────────────┘
               (LangGraph updates its own state)
```

**Why NOT store state for agents?**
LangGraph already has its own state management system. If Token-Sentry
ALSO tried to store history, you'd have two memory systems conflicting with
each other. We respect the agent's authority over its own state.

---

## 📁 What Files Did We Add/Change?

```
Token-Sentry/
│
└── src/
    ├── proxy/
    │   └── router.py            ← UPDATED: mode detection + memory wiring
    └── memory/                  ← NEW PACKAGE
        ├── __init__.py          ← makes it a Python package
        ├── session_store.py     ← Redis: save/load conversation history
        └── compressor.py        ← Groq: summarize old messages into a card
```

---

## 🗂️ New File Breakdown

---

### 📄 `src/memory/session_store.py` — The Memory Bank

**What it does:** Stores and retrieves conversation history in Redis.

**How data is stored in Redis:**
```
Key:    "session:chat-abc123"
Value:  '[{"role":"user","content":"Hi"},{"role":"assistant","content":"Hello!"},...]'
TTL:    24 hours (auto-deleted after a day of inactivity)
```

**The four operations:**
```python
# Load a session (returns [] if new session or Redis is down)
history = await load_session("chat-abc123")

# Save a session (overwrites, resets TTL)
await save_session("chat-abc123", messages)

# Clear a session (delete from Redis)
await clear_session("chat-abc123")
```

**Graceful degradation:**
If Redis is not running, all functions return empty results.
The proxy still works — it just can't remember past turns.
No crash, no 500 error — just memory-less operation.

```python
async def _get_client() -> aioredis.Redis | None:
    try:
        client = aioredis.from_url(settings.redis_url)
        await client.ping()        # ← test if Redis is alive
        return client
    except Exception:
        logger.warning("Redis unavailable. Running without session memory.")
        return None                # ← returns None, all functions skip gracefully
```

---

### 📄 `src/memory/compressor.py` — The Summarizer

**What it does:** When a conversation hits the RED watermark, this module
compresses the old (cold) part into a compact summary card.

**The hot buffer concept:**
```
Full history (10 turns, HOT_BUFFER_TURNS = 3):

[t1][t2][t3][t4][t5][t6][t7]  |  [t8][t9][t10]
─────────────────────────────     ──────────────
    COLD HISTORY                     HOT BUFFER
 (compress into summary)           (keep raw intact)
```

We NEVER compress the most recent messages. The hot buffer is the
active part of the conversation — compressing it would feel jarring to the user.

**The resulting structure:**
```
Before compression:
[t1][t2][t3][t4][t5][t6][t7][t8][t9][t10]
~8,000 tokens

After compression:
[📋 SUMMARY CARD][t8][t9][t10]
~600 tokens
```

**The summary card looks like:**
```
{"role": "system", "content":
  "📋 Conversation Summary (earlier context — 7 messages compressed):
   • User is Sayantan, building an AI proxy called Token-Sentry
   • Decided to use Groq instead of Google Gemini (quota issues)
   • Successfully tested the proxy with Llama 3.3 70B
   • Discussed two modes: stateful (chat) and passthrough (agents)
   [Compressed from 7 messages]"}
```

**The compression call:**
```python
async def _summarize(messages: list[dict]) -> str:
    response = _summarizer_client.chat.completions.create(
        model=settings.groq_summarizer_model,  # llama-3.1-8b-instant (fast)
        messages=[{
            "role": "user",
            "content": COMPRESSION_PROMPT + formatted_conversation
        }],
        temperature=0.2,    # low = factual, not creative
        max_tokens=512,     # summaries stay short
    )
    return response.choices[0].message.content
```

We use `temperature=0.2` (very low) so the summary is factual, not embellished.

---

### 📄 `src/proxy/router.py` — Updated Request Handler

The router now has the full Day 2 flow. Here's the decision tree:

```
Incoming request
      │
      ├─ Has X-Session-ID?
      │        │
      │       YES → STATEFUL MODE
      │              ├─ Load history from Redis
      │              ├─ Append new messages to history
      │              ├─ Count tokens on full history
      │              ├─ If RED → compress_history()
      │              ├─ Call Groq
      │              ├─ Append reply to history
      │              └─ Save to Redis
      │
      └─ No session ID → PASSTHROUGH MODE
                         ├─ Use messages from request as-is
                         ├─ Count tokens
                         ├─ If RED → compress_history()
                         └─ Call Groq (no Redis involved)
```

**Response headers tell you what mode was used:**
```
X-Session-ID: chat-abc123   ← your session ID (or auto-generated trace)
X-Mode: stateful            ← "stateful" or "passthrough"
X-Compressed: false         ← "true" if compression was applied this turn
```

---

## 🧠 Concepts Learned Today

### Concept 1: What is Redis?

Redis is an **in-memory database** — extremely fast because it stores data in RAM,
not on disk. It's perfect for session data.

```
Normal database (PostgreSQL):
  Save → write to disk → slow (milliseconds)
  Read → read from disk → slow (milliseconds)

Redis:
  Save → write to RAM → instant (microseconds)
  Read → read from RAM → instant (microseconds)
```

The tradeoff: Redis data CAN be lost if the machine crashes (unless you enable
persistence). For session memory, this is acceptable — worst case, the user
just starts a fresh conversation.

### Concept 2: What is TTL (Time-To-Live)?

When we save to Redis, we set `TTL = 86400 seconds (24 hours)`.
This means the data is automatically deleted after 24 hours of no activity.

```python
await client.setex(key, SESSION_TTL_SECONDS, json.dumps(messages))
#                        ↑
#                  24 hours = 86400 seconds
```

Without TTL, old sessions would pile up in Redis forever and eventually fill up memory.
TTL gives us automatic cleanup for free.

### Concept 3: What is an Async Generator?

`stream_groq_response()` uses `yield` instead of `return`.
This makes it an **async generator** — it produces values one at a time:

```python
async def stream_groq_response(...):
    for chunk in groq_stream:
        yield f"data: {chunk}\n\n"   # ← produces one chunk at a time
    yield "data: [DONE]\n\n"
```

FastAPI's `StreamingResponse` consumes this generator and sends each yielded
value to the client immediately — without waiting for the full response.

### Concept 4: What is Compression (in this context)?

We're not compressing files with ZIP. We're compressing **semantic content** —
asking an AI to summarize a conversation into its key points.

```
Original: 5000 tokens of conversation
Summary:  300 tokens of bullet points

Reduction: 94% fewer tokens, ~95% of the important information retained
```

The AI that reads the summary later (Groq) can still answer questions about
earlier parts of the conversation — it just doesn't have word-for-word accuracy.
This is acceptable for most use cases.

---

## 🪵 What the Logs Look Like Now

### First turn (no history yet):
```
INFO | Incoming request | mode: stateful | session: chat-abc123
INFO | Session loaded   | history_turns: 0
INFO | Token count measured | input_tokens: 12
DEBUG| 🟢 Token count healthy
INFO | Calling Groq (blocking)
INFO | Session saved | total_turns: 2
INFO | Request completed | input: 12 | output: 8 | total: 20
```

### After 50 turns (watermark hit):
```
INFO  | Incoming request | mode: stateful | session: chat-abc123
INFO  | Session loaded   | history_turns: 100
INFO  | Token count measured | input_tokens: 4200
WARN  | 🔴 Watermark breached — compressing history | tokens: 4200
INFO  | Starting compression | cold_turns: 97 | hot_turns: 3
INFO  | Compression complete | before: 4200 | after: 430 | reduction: 89%
INFO  | Compression applied  | tokens_after: 430 | turns_after: 4
INFO  | Session saved | total_turns: 5
INFO  | Request completed | compressed: true
```

### Passthrough mode (agent):
```
INFO | Incoming request | mode: passthrough | session: pass-f3a9b2c1
INFO | Token count measured | input_tokens: 3100
INFO | 🟡 LOW WATERMARK — approaching threshold
INFO | Calling Groq (blocking)
INFO | Request completed | mode: passthrough | compressed: false
```

---

## 🐳 Running in Docker (The Easy Way)

To avoid installing Redis manually, we've containerized Token-Sentry.
With one command, Docker starts THREE services that talk to each other:

1. **`token-sentry-app`**: Your FastAPI proxy
2. **`token-sentry-redis`**: The Redis database (alpine)
3. **`token-sentry-redisinsight`**: A visual GUI for Redis

### How to use Docker:

1. Open a terminal in your project folder
2. Run this to build and start everything in the background:
   ```powershell
   docker compose up -d --build
   ```
3. Your endpoints are now live at:
   - Proxy API: `http://localhost:8000/v1/chat/completions`
   - Redis GUI: `http://localhost:5540`

### Connecting to RedisInsight (GUI)
1. Open `http://localhost:5540` in your browser
2. Click **"Add Redis Database"**
3. Fill in the connection settings:
   - **Host:** `redis`  *(this is the Docker service name, not localhost!)*
   - **Port:** `6379`
4. Click **Test Connection** (should be green) and **Add Database**.
5. You can now visually browse your `session:*` keys!

---

## 🧪 How to Test Day 2

### Test 1 — Multi-turn memory (stateful)

Send two requests with the **same session ID**:
```powershell
# Turn 1 — introduce yourself
curl -X POST http://localhost:8000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "X-Session-ID: memory-test-01" `
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"My name is Sayantan and I am building Token-Sentry."}],"stream":false}'

# Turn 2 — ask something that requires memory
curl -X POST http://localhost:8000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "X-Session-ID: memory-test-01" `
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"What is my name and what am I building?"}],"stream":false}'
```
Expected: Turn 2 correctly answers "Sayantan" and "Token-Sentry" ✅

### Test 2 — Passthrough mode (no session ID)

```powershell
curl -X POST http://localhost:8000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"system","content":"You are a helpful assistant."},{"role":"user","content":"Hello!"}],"stream":false}'
```
Check response header — should see `X-Mode: passthrough`.

### Test 3 — Different sessions are isolated

```powershell
# Session A remembers "dog"
curl ... -H "X-Session-ID: session-A" -d '{"messages":[{"role":"user","content":"My pet is a dog named Bruno."}]}'

# Session B remembers "cat"
curl ... -H "X-Session-ID: session-B" -d '{"messages":[{"role":"user","content":"My pet is a cat named Luna."}]}'

# Ask session A — should say "dog"
curl ... -H "X-Session-ID: session-A" -d '{"messages":[{"role":"user","content":"What is my pet?"}]}'
```
Expected: Session A says "Bruno the dog", Session B is completely separate ✅

---

## ✅ End of Day Checklist

- [x] Redis session store written
- [x] Compression engine written (hot buffer + cold summary)
- [x] Router updated with mode detection
- [x] Stateful flow: load → append → count → compress → call → save
- [x] Passthrough flow: count → compress if needed → call
- [x] Response headers added (X-Mode, X-Compressed)
- [ ] Redis installed and running locally  ← you need this for stateful mode
- [ ] Multi-turn memory test passed
- [ ] Session isolation test passed

---

## ❓ Questions to Think About

1. Why do we keep the hot buffer raw (uncompressed)?
   *(Hint: what would feel weird if we compressed the last 3 turns too?)*

2. What happens if compression fails (Groq is down mid-request)?
   *(Hint: look at the fallback in `_summarize()`)*

3. Why does stateful streaming use blocking internally?
   *(Hint: what do we need to do AFTER getting the response in stateful mode?)*

4. Could a LangGraph agent use stateful mode?
   *(Hint: what would happen if both LangGraph AND Token-Sentry tried to manage the same history?)*
