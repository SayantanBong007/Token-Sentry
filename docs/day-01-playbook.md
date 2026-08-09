# 📓 Token-Sentry Playbook — Day 1
### Date: 2026-08-06 | Topic: Setting Up the Project (Groq Edition)

---

## 🎯 What Was the Goal Today?

Build the **skeleton** of Token-Sentry — just enough so we can:
1. Start a web server on our laptop
2. Send it a message (in the same format ChatGPT uses)
3. See it forward that message to **Groq AI** (free, blazing fast, Llama models)
4. See the reply stream back word-by-word
5. See **logs** of what happened (token count, which model, latency, etc.)

Nothing complex. Just: message goes IN → Groq responds → message comes OUT.

```
You (any app)  ──── POST /v1/chat/completions ────►  Token-Sentry
                        (OpenAI format)                   │
                                                          ▼
                                                       Groq API
                                                   (Llama 3.3 70B)
               ◄──────────── reply streams back ──────────┘
```

---

## 🛠️ Why Groq Instead of Google Gemini?

| | Google Gemini (old) | Groq (new) |
|---|---|---|
| Free tier | Very limited, daily cap | 14,400 req/day, 30 req/min |
| Speed | Moderate | **Fastest inference on the planet** |
| Token counting | Requires a network API call | **Local** (tiktoken, instant) |
| Message format | Different from OpenAI (needs conversion) | **Same as OpenAI** (no conversion!) |
| API key | `AIza...` from AI Studio | `gsk_...` from console.groq.com |
| Models | Gemini | Llama 3.3 70B, Mistral, Gemma, etc. |

---

## 📁 What Files Did We Create?

```
Token-Sentry/
│
├── .env.example        ← Template for secret keys (never commit real keys!)
├── .env                ← YOUR real secrets (gitignored — only on your machine)
├── .gitignore          ← Tells Git what NOT to upload
├── requirements.txt    ← List of Python packages needed
│
└── src/                ← All source code lives here
    ├── main.py                      ← The front door. Starts the server.
    ├── config.py                    ← Reads settings from your .env file
    ├── proxy/
    │   ├── router.py                ← Handles incoming chat requests
    │   ├── transformer.py           ← Maps model names + builds responses
    │   └── streaming.py             ← Streams the AI reply word-by-word
    └── token_engine/
        ├── counter.py               ← Counts tokens locally using tiktoken
        └── watermark.py             ← Checks if we've crossed the token limit
```

---

## 🗂️ File-by-File Breakdown — What Does Each File Actually Do?

---

### 📄 `.env` — Your Secrets File

This file holds your private configuration values — API keys, model names, port numbers.
**It never gets uploaded to GitHub.**

```ini
GROQ_API_KEY=gsk_...              ← your Groq key (like a password)
GROQ_MAIN_MODEL=llama-3.3-70b-versatile  ← the AI model to use
GROQ_SUMMARIZER_MODEL=llama-3.1-8b-instant  ← fast model for summaries
TOKEN_HIGH_WATERMARK=4000         ← compress conversations after this many tokens
HOT_BUFFER_TURNS=3                ← keep the last 3 messages uncompressed
REDIS_URL=redis://localhost:6379
PORT=8000
```

Think of `.env` like the **settings panel on the back of a machine** — you don't open it up
and hardcode values inside the code, you just adjust the dials on the outside.

---

### 📄 `requirements.txt` — Shopping List for Python

Before you can run the project, Python needs to know which libraries to install.
`requirements.txt` is that list.

```
fastapi         ← creates the web server
uvicorn         ← runs the web server
groq            ← talks to Groq AI (Llama, Mixtral, Gemma)
tiktoken        ← counts tokens locally (no API call needed)
httpx           ← sends HTTP requests
redis           ← stores session data (Phase 2)
python-dotenv   ← reads your .env file
pydantic        ← validates data shapes
structlog       ← structured logging
```

You install everything in one command: `pip install -r requirements.txt`

---

### 📄 `src/config.py` — The Settings Reader

**What it does:** Reads everything from `.env` and makes it available to all other files
as a single object called `settings`.

```python
class Settings(BaseSettings):
    groq_api_key: str              # REQUIRED — app crashes if missing
    groq_main_model: str           # defaults to "llama-3.3-70b-versatile"
    groq_summarizer_model: str     # defaults to "llama-3.1-8b-instant"
    token_high_watermark: int      # defaults to 4000 tokens
    hot_buffer_turns: int          # defaults to 3 turns
    ...

settings = Settings()  # ← create ONE shared instance
```

**Why it matters:** Every other file does `from src.config import settings` to get these values.
You change a setting once (in `.env`) and all files see the new value automatically.
No magic strings scattered across 5 files.

**Key concept — Pydantic validation:**
If `GROQ_API_KEY` is missing from your `.env`, Pydantic raises a clear error at startup:
`ValidationError: groq_api_key field required`
Instead of a mysterious crash 5 steps later.

---

### 📄 `src/main.py` — The Front Door

**What it does:** Creates the FastAPI app, sets up logging, and registers all routes.
This is the file you run to start the whole server.

```python
app = FastAPI(title="Token-Sentry", version="0.2.0")

# Register routes (the actual endpoints)
app.include_router(proxy_router)

# Health check — so you can confirm the server is alive
@app.get("/health")
async def health_check():
    return {"status": "ok", "backend": "groq", "model": settings.groq_main_model}
```

**The startup banner (lifespan function):**
```python
@asynccontextmanager
async def lifespan(app):
    logger.info("🛡️  Token-Sentry starting up")
    logger.info(f"   Backend    : Groq")
    logger.info(f"   Main model : {settings.groq_main_model}")
    logger.info(f"   Watermark  : {settings.token_high_watermark} tokens")
    yield  # ← server runs here
    logger.info("🛡️  Token-Sentry shutting down")
```
Everything before `yield` = runs on startup.
Everything after `yield` = runs on shutdown.

**Logging setup:**
`main.py` configures two log destinations at once — your terminal AND `logs/sentry.log`.
The log file is **cleared every restart** (so it always shows only the current session).

---

### 📄 `src/proxy/router.py` — The Request Handler

**What it does:** Defines the main endpoint `POST /v1/chat/completions`.
Every incoming message hits this function first.

```python
@router.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatCompletionRequest):
    ...
```

**The request shape it accepts (standard OpenAI format):**
```json
{
  "model": "llama-3.3-70b-versatile",
  "messages": [
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false
}
```

**What it does step-by-step:**

```
Step 1: Read the X-Session-ID header (or generate one)
        └─ session_id = "test-01" (you provide) or "auto-a3f9b..." (generated)

Step 2: Count tokens in the messages
        └─ calls counter.py → instant local count via tiktoken (no API call!)

Step 3: Check the watermark
        └─ calls watermark.py → returns GREEN / YELLOW / RED

Step 4: Map the model name
        └─ calls transformer.py → "gpt-4o" becomes "llama-3.3-70b-versatile"

Step 5: Forward to Groq
        └─ if stream=True  → calls streaming.py → words stream back live
           if stream=False → calls streaming.py → full reply returned at once
```

**The ChatCompletionRequest model (data validation):**
```python
class ChatCompletionRequest(BaseModel):
    model: str = "llama-3.3-70b-versatile"  # optional, has a default
    messages: list[Message]                   # REQUIRED
    stream: bool = False                      # optional, defaults to no streaming
    temperature: float = 0.7                  # how creative/random the reply is
    max_tokens: int | None = None             # optional output limit
```
Pydantic automatically validates this — if `messages` is missing, you get a 422 error immediately.

---

### 📄 `src/proxy/transformer.py` — The Model Name Mapper

**What it does:** Maps OpenAI model names to Groq model names.

> ⚡ **This is much simpler than the old Gemini version.**
> With Gemini, we had to convert the entire message format (OpenAI → Gemini format).
> With Groq, **the message format is identical to OpenAI** — so no conversion needed!
> This file is now just about model name mapping.

**The model name mapper:**
```python
MODEL_MAP = {
    "gpt-4o":        "llama-3.3-70b-versatile",  # client asks for GPT-4 → Llama 70B
    "gpt-4o-mini":   "llama-3.1-8b-instant",      # mini → fast 8B model
    "gpt-3.5-turbo": "llama-3.1-8b-instant",      # old GPT → 8B
    # Groq model names pass through unchanged
    "llama-3.3-70b-versatile": "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768":      "mixtral-8x7b-32768",
}
```

This means **any OpenAI-compatible app can point at Token-Sentry** and it just works.
The app asks for `gpt-4o` and silently gets Llama 70B — it never knows.

**The response builders:**
`build_openai_response()` and `build_openai_chunk()` take Groq's output and wrap it
in OpenAI's response format so the client gets exactly what it expects.

---

### 📄 `src/proxy/streaming.py` — The Streaming Engine

**What it does:** Calls Groq and streams the response back word-by-word using SSE (Server-Sent Events).

**What SSE looks like over the wire:**
```
data: {"choices":[{"delta":{"content":"Hello"},...}]}

data: {"choices":[{"delta":{"content":" there"},...}]}

data: {"choices":[{"delta":{"content":"!"},...}]}

data: [DONE]
```
Each `data:` line = one word (or a few tokens). The client renders them as they arrive —
exactly like ChatGPT typing in real time.

**The Groq client (created once, reused):**
```python
_groq_client = Groq(api_key=settings.groq_api_key)
```
One client shared across all requests — efficient, no reconnecting.

**The streaming generator:**
```python
async def stream_groq_response(messages, model_name, session_id, ...):
    # Call Groq with streaming ON
    # Note: messages pass through unchanged — Groq uses OpenAI format!
    stream = _groq_client.chat.completions.create(
        model=model_name,
        messages=messages,   # ← no conversion needed
        stream=True,
    )

    for chunk in stream:
        chunk_text = chunk.choices[0].delta.content or ""
        if chunk_text:
            sse_chunk = build_openai_chunk(chunk_text, model_name)
            yield f"data: {json.dumps(sse_chunk)}\n\n"  # ← sent to client immediately

    yield "data: [DONE]\n\n"
```

The `yield` keyword makes this an **async generator** — FastAPI streams each line
to the client the moment it's produced.

**Blocking mode (`call_groq_blocking`):**
When `stream=False`, the function calls Groq and waits for the full response.
Groq also returns the exact token usage in its response object, so we don't even
need to call counter.py again for the output — we just read `response.usage.completion_tokens`.

---

### 📄 `src/token_engine/counter.py` — The Token Counter

**What it does:** Before sending anything to Groq, counts approximately how many tokens
are in the messages.

> ⚡ **Big upgrade from the Gemini version.**
> Before: we had to make a FREE API call to Google to count tokens (network, latency, quota).
> Now: we use **tiktoken** — it runs entirely on your machine, takes microseconds, and
> uses zero API quota.

**What is tiktoken?**
tiktoken is OpenAI's official tokenizer library. It converts text → tokens using the same
algorithm the models use internally. We use the `cl100k_base` encoding (same as GPT-4),
which is a close approximation for Llama and Mixtral models too (±5%).

**The key code:**
```python
_encoding = tiktoken.get_encoding("cl100k_base")

def count_tokens_in_messages(messages):
    total = 0
    for msg in messages:
        total += 4  # small overhead per message (role + formatting tokens)
        total += len(_encoding.encode(msg["content"]))  # actual content tokens
    return total
```

**Why 4 overhead per message?**
Every message in a conversation takes a few extra tokens for the role label
(`"user"`, `"assistant"`) and the separators that wrap it. We add 4 as a constant
approximation — it's very close to the real overhead.

**Fallback estimate:**
If tiktoken fails for any reason:
```python
except Exception:
    return len(all_text) // 4  # rough: 4 chars ≈ 1 token
```
The request still goes through — just with a less accurate count.

---

### 📄 `src/token_engine/watermark.py` — The Token Gauge

**What it does:** Takes the token count from `counter.py` and says:
"Are we safe, getting close, or over the limit?"

```python
HIGH_WATERMARK = 4000   # from .env
LOW_WATERMARK  = 3000   # automatically 75% of HIGH

def check_watermark(token_count, session_id) -> str:
    if token_count >= HIGH_WATERMARK:
        return WatermarkStatus.RED     # 🔴 "COMPRESS NOW"
    elif token_count >= LOW_WATERMARK:
        return WatermarkStatus.YELLOW  # 🟡 "getting close, watch it"
    else:
        return WatermarkStatus.GREEN   # 🟢 "all good"
```

Like a fuel gauge on a car:

```
Token count:
   0 ──────────────── 3000 ──────── 4000 ─────────► ∞
   |                    |              |
   GREEN ✅          YELLOW ⚠️       RED 🔴
   (safe)           (watch it)    (COMPRESS NOW!)
```

**Current behavior (Phase 1):**
When RED is returned, `router.py` logs a warning but still sends the full payload to Groq.
**In Phase 2**, RED will trigger compression — summarizing old messages before sending.

This file is **model-agnostic** — it doesn't care whether we're using Groq, Gemini, or
any other AI. It just works with numbers.

---

## 🧠 What Did We Learn Today?

### Concept 1: What is FastAPI?

FastAPI is a Python library that creates a **web server**.
Think of it like building a restaurant:
- FastAPI = the restaurant building
- An "endpoint" = a window where customers place orders
- `/v1/chat/completions` = our one window that accepts chat messages

```
You (client)  ──── POST /v1/chat/completions ────►  Token-Sentry (FastAPI)
                        (your message)
              ◄───────────────────────────────────  reply streams back
```

### Concept 2: What is an Environment Variable?

Your Groq API key is a **secret**. You never paste it in code files
because code files get uploaded to GitHub where anyone can see them.

Instead:
```
.env file (private, only on YOUR machine):
  GROQ_API_KEY=gsk_...your-key...

Your code reads it like this:
  from src.config import settings
  key = settings.groq_api_key  ← reads from .env, not hardcoded
```

The `.gitignore` file tells Git: "NEVER upload `.env`". ✅

### Concept 3: What is Streaming?

Normal API call:
```
You ask → Wait 3 seconds → Get full answer at once
```

Streaming:
```
You ask → Words appear one-by-one as Groq generates them
         "Hello" ... "there" ... "how" ... "are" ... "you?"
```

This is exactly how ChatGPT works — you see words appear in real time.
Technically this uses a protocol called **SSE (Server-Sent Events)**.

### Concept 4: What is Token Counting?

Groq charges per "token" (roughly ¾ of a word = 1 token).
Instead of asking Groq to count them (which uses quota), we use **tiktoken**
— a local library that counts tokens instantly on your machine for free.

```python
import tiktoken
encoding = tiktoken.get_encoding("cl100k_base")

text = "Hello, how are you today?"
tokens = encoding.encode(text)
print(len(tokens))  # → 7 tokens
```

We use this count to decide: "Is this conversation getting too big?"

### Concept 5: What is the HIGH WATERMARK?

Like a dam with a water level sensor:

```
Token count:
   0 ──────────────── 3000 ──────── 4000 ─────────► ∞
   |                    |              |
   GREEN ✅          YELLOW ⚠️       RED 🔴
   (safe)           (watch it)    (COMPRESS NOW!)
```

In Phase 2, when we hit RED, we'll compress old messages.
For now (Phase 1), we just LOG it and continue.

---

## 🪵 How Logging Works

The app writes two kinds of output:
1. **Console (terminal)** — you see it while the app runs
2. **Log file** — written to `logs/sentry.log` so you can review it

The log file is **cleared every time you restart the app**.
This way logs = only THIS session, nothing stale from yesterday.

### Reading the log:
```
2026-08-06 | INFO     | Token-Sentry starting up
2026-08-06 | INFO     | Backend: Groq | Main model: llama-3.3-70b-versatile
2026-08-06 | INFO     | Incoming request | session: test-001 | messages: 1
2026-08-06 | INFO     | Token count measured | input_tokens: 9
2026-08-06 | DEBUG    | 🟢 Token count healthy | tokens: 9 | limit: 4000
2026-08-06 | INFO     | Starting Groq stream | model: llama-3.3-70b-versatile
2026-08-06 | INFO     | Groq stream completed | chunks: 6 | output_tokens: 12
```

Each line = one thing that happened, in order, with the time.

---

## ✅ End of Day Checklist

- [x] Project folder created
- [x] Virtual environment set up (.venv)
- [x] All packages installed (`groq`, `tiktoken`, `fastapi`, etc.)
- [x] Config system working (reads from .env)
- [x] Token counter written (local tiktoken — no API call)
- [x] Watermark checker written
- [x] Model name mapper written (OpenAI names → Groq names)
- [x] Streaming engine written (Groq SDK)
- [x] Main router written
- [x] File logging added
- [ ] `.env` filled with real Groq API key  ← **YOU DO THIS**
- [ ] Server started for the first time     ← **NEXT STEP**

---

## 🚀 To Start the Server (Do This Now)

### Step 1 — Get your Groq API key (free, 2 minutes)
1. Go to **https://console.groq.com/keys**
2. Sign in with Google or GitHub
3. Click **"Create API Key"**
4. Copy the key (starts with `gsk_...`)
5. Open `D:\AGENTIC AI\Token-Sentry\.env`
6. Replace `your-groq-api-key-here` with your real key
7. Save the file

### Step 2 — Start the server
```powershell
cd "D:\AGENTIC AI\Token-Sentry"
.venv\Scripts\uvicorn src.main:app --reload --port 8000
```

You should see:
```
🛡️  Token-Sentry starting up
   Backend      : Groq
   Main model   : llama-3.3-70b-versatile
   Listening on : http://0.0.0.0:8000
```

### Step 3 — Send a test request
```powershell
curl -X POST http://localhost:8000/v1/chat/completions `
  -H "Content-Type: application/json" `
  -H "X-Session-ID: test-01" `
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"Say hello in 5 words."}],"stream":false}'
```

---

## ❓ Questions to Think About

Before Day 2, try to answer these in your head:

1. Why do we no longer need a format converter between OpenAI and Groq?
   *(Hint: what format does Groq use?)*

2. What is the advantage of counting tokens locally with tiktoken instead of calling an API?
   *(Hint: think about quota, speed, and cost)*

3. What happens if we just send all 50 messages of a chat history every time?
   *(Hint: token limits + Groq's rate limits)*

4. Why is the log file cleared on startup?
   *(Hint: debugging is easier when you only see TODAY's logs)*
