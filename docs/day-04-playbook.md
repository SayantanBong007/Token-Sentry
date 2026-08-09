# 📓 Token-Sentry Playbook — Day 4
### Date: 2026-08-09 | Topic: V2 Enterprise Upgrade — Universal Fallbacks, Semantic Chunking & Analytics Dashboard

---

## 🎯 What Was the Goal Today?

Transform Token-Sentry from a solid personal proxy into a **production-grade, enterprise-ready API gateway** with three major new capabilities:

1. **Universal Provider Fallbacks** — Route to ANY LLM provider (Groq, NVIDIA, OpenRouter, Together) and seamlessly failover between them if the primary hits a rate limit.
2. **Advanced Semantic Chunking** — Stop dumping entire summaries into ChromaDB as single blobs. Chunk them into overlapping 500-character segments and retrieve only the top 5 most relevant ones.
3. **Real-Time Analytics Dashboard** — A Next.js UI that live-polls the API gateway and visualises token savings, routing decisions, fallback events, and system health.

```
BEFORE (Day 3):                       AFTER (Day 4):

  App                                   App
   │                                     │
   ▼                                     ▼
Token-Sentry ─── Groq only ──► LLM  Token-Sentry ──► Primary (Groq)
                                                │      ↕ auto-failover
                                                └──► Fallback (NVIDIA NIM)

                                     ┌─────────────────────────┐
                                     │  Dashboard :3000        │
                                     │  • Tokens Saved         │
                                     │  • Cost Saved $         │
                                     │  • Routing Chart        │
                                     │  • Live Activity Feed   │
                                     └─────────────────────────┘
```

---

## 🔌 Feature 1: Universal Provider Fallbacks

### The Problem We Solved

The original system used the `groq` Python SDK directly. This created two limitations:
1. Token-Sentry could only ever talk to Groq — hard-coded for a single vendor.
2. When Groq's free-tier rate limit was hit (`429 Too Many Requests`), the official OpenAI SDK retried the same provider with exponential backoff — waiting **10 seconds, then 20 seconds** before giving up. This caused 43-second response times.

### The Solution

We replaced the `groq` SDK with the official **`openai` SDK** in every file that talks to an AI provider. The OpenAI SDK supports a custom `base_url` parameter — meaning it can talk to any provider that exposes an OpenAI-compatible API. This includes Groq, NVIDIA NIM, OpenRouter, Together AI, Fireworks, and regular OpenAI itself.

```python
from openai import AsyncOpenAI

# Primary provider (Groq)
_primary_client = AsyncOpenAI(
    base_url=settings.primary_provider_url,   # https://api.groq.com/openai/v1
    api_key=settings.primary_api_key,
    max_retries=0,  # ← CRITICAL: we handle retries ourselves via fallback
)

# Fallback provider (NVIDIA NIM)
_fallback_client = AsyncOpenAI(
    base_url=settings.fallback_provider_url,  # https://integrate.api.nvidia.com/v1
    api_key=settings.fallback_api_key,
    max_retries=0,
)
```

### Why `max_retries=0` is Critical

By default the OpenAI SDK retries on 429 errors with exponential backoff:
```
Attempt 1: Primary fails → Wait 10s → Retry Primary → Wait 20s → Retry Primary → Give up
Total wait: 30+ seconds
```

With `max_retries=0`, Token-Sentry's own `try/except` block catches the first failure immediately and switches to the fallback in under 1 second:
```
Attempt 1: Primary fails → Our handler catches it → Fallback fires → ✅
Total wait: < 1 second
```

### The Fallback Logic (streaming.py)

```python
async def stream_provider_response(messages, model_name, session_id, ...):
    try:
        # Try Primary provider first
        stream = await _primary_client.chat.completions.create(
            model=model_name, messages=messages, stream=True,
        )
    except Exception as e:
        logger.warning(f"Primary failed ({e}) — switching to fallback")
        await increment_metric("fallback_events")
        try:
            # Instantly retry on fallback
            stream = await _fallback_client.chat.completions.create(
                model=settings.fallback_main_model,
                messages=messages, stream=True,
            )
        except Exception as fallback_e:
            # Both providers down — surface a clear error to the client
            yield f"data: {json.dumps({'error': 'All upstream providers failed'})}\n\n"
            return
    
    # Stream response normally once we have a working stream
    async for chunk in stream:
        ...
```

### Configuring Providers in .env

```ini
# Primary Provider (Groq)
PRIMARY_PROVIDER_URL=https://api.groq.com/openai/v1
PRIMARY_API_KEY=gsk_your_key_here
PRIMARY_MAIN_MODEL=llama-3.3-70b-versatile
PRIMARY_SUMMARIZER_MODEL=llama-3.1-8b-instant

# Fallback Provider (NVIDIA NIM)
FALLBACK_PROVIDER_URL=https://integrate.api.nvidia.com/v1
FALLBACK_API_KEY=nvapi-your_key_here
FALLBACK_MAIN_MODEL=meta/llama-3.3-70b-instruct
FALLBACK_SUMMARIZER_MODEL=meta/llama-3.1-8b-instruct
```

> **NVIDIA NIM model name format:** NVIDIA uses `meta/` prefix (e.g., `meta/llama-3.3-70b-instruct`), while OpenRouter uses `meta-llama/` (e.g., `meta-llama/llama-3.3-70b-instruct`). Always check the provider's model list.

### Supported Providers

| Provider | base_url | Key Format | Notes |
|---|---|---|---|
| Groq | `api.groq.com/openai/v1` | `gsk_...` | Fastest inference, free tier |
| NVIDIA NIM | `integrate.api.nvidia.com/v1` | `nvapi-...` | Use `meta/` model prefix |
| OpenRouter | `openrouter.ai/api/v1` | `sk-or-...` | Access 100+ models |
| Together AI | `api.together.xyz/v1` | `...` | Drop-in replacement |
| OpenAI | `api.openai.com/v1` | `sk-...` | Official OpenAI |

---

## 🔍 Feature 2: Advanced Semantic Chunking

### The Problem With Our Old ChromaDB Approach

On Day 3 we implemented Cold Memory — saving old conversation summaries into ChromaDB. But we had a flaw: we inserted each summary as a **single massive document**.

Imagine your conversation history from last week was a 2,000-word block. ChromaDB embedded that entire block as a single vector. When you asked "What was my favorite color?", ChromaDB compared your question to that 2,000-word blob and gave it a single relevance score. If only 10 words of that 2,000-word document were relevant, the score was terrible and it might not be retrieved at all.

### The Fix: Overlapping Chunking

Instead of inserting long text as single documents, we now split it into smaller overlapping chunks:

```
Original text (1,200 chars):
"This is a long conversation about Python. ... We discussed React. ... User likes dark mode. ..."

After chunking (500 chars, 50 char overlap):
Chunk 0: "This is a long conversation about Python. ... [first 500 chars]"
Chunk 1: "[chars 450-950: ...We discussed React...]"   ← 50 char overlap with Chunk 0
Chunk 2: "[chars 900-1200: ...User likes dark mode...]" ← 50 char overlap with Chunk 1
```

The overlap is critical. It prevents a sentence from being cut in half between two chunks, losing its meaning at the seam.

### Implementation (vector_store.py)

```python
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks for better vector search retrieval."""
    if len(text) <= chunk_size:
        return [text]   # short text — no need to chunk
    
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += (chunk_size - overlap)  # slide forward, but overlap by 50 chars
    return chunks

async def save_to_cold_memory(session_id: str, messages: list[dict]):
    for msg in messages:
        content_chunks = chunk_text(msg['content'])
        for i, chunk in enumerate(content_chunks):
            doc = f"{msg['role'].upper()}: {chunk}"
            documents.append(doc)
            metadatas.append({"role": msg['role'], "chunk": i})  # track chunk index
            ids.append(uuid.uuid4().hex)
```

### Retrieval — Top 5 Chunks

We also increased the retrieval count from 3 to **5** chunks. This means the model gets more relevant context without dramatically increasing token costs, since each chunk is only ~500 characters.

```python
async def recall_from_cold_memory(session_id: str, query: str, k: int = 5) -> str:
    results = collection.query(query_texts=[query], n_results=min(k, collection.count()))
    docs = results['documents'][0]
    return "\n".join(docs)  # all 5 relevant chunks joined and injected as context
```

### Why This Matters

| Before (single doc) | After (chunked) |
|---|---|
| 1 embedding per message | Multiple embeddings per message |
| Whole 2,000-word block scored against query | 500-char targeted chunks scored individually |
| Score diluted by irrelevant content | Score concentrated on relevant content |
| Often missed the answer | Consistently retrieves the right snippet |

---

## 📊 Feature 3: Redis Analytics Engine

### Design Philosophy

Instead of adding a heavy time-series database like InfluxDB or Prometheus, we reused our **existing Redis** container to maintain lightweight atomic counters. Redis `INCRBY` is an O(1) operation — it adds a number to a key in microseconds with no locking, no schema, and no data loss.

### Metrics Tracked

| Redis Key | Incremented When |
|---|---|
| `metrics:requests_served` | Every incoming request hits `/v1/chat/completions` |
| `metrics:simple_intents_routed` | Intent classifier returns SIMPLE → cheap model used |
| `metrics:fallback_events` | Primary provider fails → Fallback fires |
| `metrics:tokens_saved` | Compression runs → tokens reduced |
| `metrics:compression_runs` | A compression cycle completes successfully |
| `metrics:activity_log` | A rolling list of last 15 events (for the live feed) |

### tracker.py

```python
async def increment_metric(key: str, amount: int = 1):
    pipe = _redis_client.pipeline()
    pipe.incrby(f"metrics:{key}", amount)
    # Append a timestamped event to the activity log
    event = f"{int(time.time())}:{key}:{amount}"
    pipe.lpush("metrics:activity_log", event)
    pipe.ltrim("metrics:activity_log", 0, 19)  # keep only last 20 events
    await pipe.execute()
```

Using `pipeline()` batches both commands into a single Redis round-trip — more efficient than two separate `await` calls.

### Derived Metrics

The `/api/metrics` endpoint calculates additional derived values on-the-fly before returning:

```python
# Approximate cost saved based on saved tokens
# Llama 70B is ~$0.79 / 1M tokens on the open market
cost_saved_usd = round((tokens_saved / 1_000_000) * 0.79, 6)

# Percentage of requests handled by the cheap model
routing_efficiency_pct = round((simple / requests) * 100) if requests > 0 else 0

# Complex requests = total - simple
complex_intents = requests - simple
```

---

## 🖥️ Feature 4: Next.js Analytics Dashboard

### Why Next.js?

The dashboard needed to:
- Live-poll an API endpoint every few seconds
- Render dynamic SVG charts
- Have a polished, premium look with animations
- Be completely separate from the Python backend (different port, different process)

Next.js 14 with the App Router was the right choice. It handles server-side rendering, client-side interactivity, and TypeScript validation in one framework.

### Dashboard Architecture

```
/dashboard
├── src/app/
│   ├── layout.tsx      ← Sets page <title> and imports globals.css
│   ├── globals.css     ← Full design system (dark mode, glassmorphism, animations)
│   ├── page.tsx        ← Main analytics dashboard (live-polling)
│   └── docs/
│       ├── page.tsx    ← Full documentation page with sidebar navigation
│       └── docs.css    ← Docs-specific styles (sidebar, code blocks, tables)
```

### Live Polling

```typescript
useEffect(() => {
    const fetchMetrics = async () => {
        const res = await fetch("http://localhost:8000/api/metrics");
        const data = await res.json();
        setMetrics(data);
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 3000);  // poll every 3 seconds
    return () => clearInterval(interval);
}, []);
```

### Design System Highlights

- **Dark background:** `#080b10` with subtle radial gradient glows in green and blue
- **Glassmorphic cards:** `backdrop-filter: blur(10px)` with semi-transparent borders
- **Typography:** `Outfit` for UI text, `JetBrains Mono` for numbers and code
- **Micro-animations:** Cards lift on hover with `transform: translateY(-3px)` + `box-shadow` transitions
- **SVG Ring Chart:** Custom-built SVG efficiency ring with `stroke-dashoffset` animation driven by the live routing efficiency percentage

### Dashboard Sections

| Section | Data Source | What It Shows |
|---|---|---|
| KPI Cards (top row) | `/api/metrics` | Tokens Saved, Cost $, Requests, Compressions, Fallbacks |
| Intent Routing Bar Chart | `/api/metrics` | Simple vs Complex vs Fallback distribution |
| Efficiency Ring | Derived from metrics | % of requests sent to cheap model |
| Provider Health | Hardcoded + live fallback count | Groq = Active, NVIDIA = Standby or X× Used |
| System Config | Hardcoded config values | Watermark, buffer size, chunk settings |
| Live Activity Feed | `metrics:activity_log` in Redis | Last 15 events with relative timestamps |

---

## 🗂️ Files Changed Today

```
Token-Sentry/
│
├── .env                          ← PRIMARY_* / FALLBACK_* (replaced GROQ_*)
├── requirements.txt              ← groq==0.9.0 → openai>=1.0.0
│
├── src/
│   ├── config.py                 ← Settings now has primary_* and fallback_* fields
│   ├── main.py                   ← Updated startup banner + /api/metrics endpoint
│   ├── proxy/
│   │   ├── streaming.py          ← Rewritten: AsyncOpenAI + try/except fallback logic
│   │   ├── transformer.py        ← groq_main_model → primary_main_model
│   │   └── router.py             ← Imports increment_metric, tracks requests + routing
│   ├── memory/
│   │   ├── compressor.py         ← AsyncOpenAI, awaits summarizer, tracks compression_runs
│   │   └── vector_store.py       ← Added chunk_text(), k increased to 5
│   ├── routing/
│   │   └── intent_classifier.py  ← AsyncOpenAI replaces AsyncGroq
│   └── metrics/
│       └── tracker.py            ← NEW: Redis analytics engine + activity log
│
└── dashboard/                    ← NEW: Next.js 14 analytics frontend
    └── src/app/
        ├── layout.tsx
        ├── globals.css           ← Full Vanilla CSS design system
        ├── page.tsx              ← Live-polling dashboard with ring chart, bar chart, feed
        └── docs/
            ├── page.tsx          ← Comprehensive documentation with sidebar
            └── docs.css
```

---

## 🧠 Key Concepts Learned Today

### Concept 1: SDK-Level vs Application-Level Retries

The key insight on Day 4: **do not let the SDK handle retries** if you want to implement your own fallback logic.

```
SDK Retries (bad for us):        Token-Sentry Fallbacks (good):
  ↓ Primary fails                  ↓ Primary fails
  ↓ SDK waits 10s                  ↓ Our except block fires immediately
  ↓ SDK retries primary            ↓ Fallback fires
  ↓ SDK waits 20s                  ↓ Response in < 1 second ✅
  ↓ SDK retries primary again
  ↓ 43 seconds wasted ❌
```

By setting `max_retries=0` on both clients, Token-Sentry owns the retry strategy. This is the correct pattern for any proxy that wants true HA (High Availability).

### Concept 2: Vector Chunking vs Vector Stuffing

Embedding large documents as a single vector is a known RAG anti-pattern called "vector stuffing." The embedding model averages the meaning of the entire document into one point in vector space. If a 2,000-word document discusses Python AND cooking AND philosophy, its embedding ends up somewhere in the middle of all three topics — making it a poor match for any specific query.

Small, focused chunks embed precisely. A 500-character chunk about Python embeds in the "Python" region of vector space and scores highly against any Python-related query.

### Concept 3: Redis Pipelines

When you need to run multiple Redis commands in sequence, use a pipeline:

```python
# Slow: Two round-trips to Redis
await redis.incrby("counter", 1)
await redis.lpush("log", "event")

# Fast: One round-trip (batched)
pipe = redis.pipeline()
pipe.incrby("counter", 1)
pipe.lpush("log", "event")
await pipe.execute()
```

Under load, the difference becomes significant. A pipeline batches all commands into a single TCP packet and receives a single response — much more efficient.

### Concept 4: OpenAI SDK as a Universal HTTP Client

The OpenAI SDK is really just a well-typed HTTP client with a few conveniences (streaming, retries, error types). By overriding `base_url`, you can use it to talk to any API that follows the OpenAI schema. This is why the entire industry has converged on the OpenAI API spec — if you implement it, any tool that works with OpenAI works with you.

---

## 🚀 How to Run Today's Stack

### Backend (Docker)
```bash
# Start everything
docker-compose up -d --build

# Check it's healthy
curl http://localhost:8000/health

# Check live metrics
curl http://localhost:8000/api/metrics
```

### Analytics Dashboard (Next.js)
```bash
cd dashboard
npm install       # only needed first time
npm run dev

# Open http://localhost:3000
```

### Run a Multi-Turn Compression Test
```python
import urllib.request, json, time

url = "http://localhost:8000/v1/chat/completions"
headers = {"Content-Type": "application/json", "X-Session-ID": "test-day4"}
block = "This is a moderate conversation block used for testing compression. " * 80

for i in range(1, 7):
    payload = {"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": f"Turn {i}: {block}"}]}
    req = urllib.request.Request(url, headers=headers, data=json.dumps(payload).encode())
    resp = urllib.request.urlopen(req).read()
    print(f"Turn {i}: Done")
    # After turn ~5, check your dashboard — tokens_saved will jump!
```

---

## ✅ End of Day Checklist

- [x] Replaced `groq` SDK with `openai` SDK across all files
- [x] Added `PRIMARY_*` and `FALLBACK_*` provider config to `.env` and `config.py`
- [x] Rewrote `streaming.py` with `try/except` fallback logic and `max_retries=0`
- [x] Updated `intent_classifier.py` and `compressor.py` to use `AsyncOpenAI`
- [x] Implemented `chunk_text()` in `vector_store.py` with 500-char / 50-char overlap
- [x] Increased ChromaDB retrieval from top-3 to top-5 chunks
- [x] Created `src/metrics/tracker.py` with Redis atomic counters + activity log
- [x] Added `GET /api/metrics` endpoint to `main.py`
- [x] Injected `increment_metric()` calls into `router.py`, `compressor.py`, `streaming.py`
- [x] Initialized Next.js 14 dashboard in `/dashboard` (No Tailwind)
- [x] Built full design system in `globals.css` (dark, glassmorphic, animated)
- [x] Built live-polling dashboard with KPI cards, bar chart, ring chart, activity feed
- [x] Built `/docs` page with sticky sidebar, code blocks, API reference, env table
- [x] Fixed NVIDIA NIM URL (`openrouter.ai` → `integrate.api.nvidia.com/v1`)
- [x] Fixed NVIDIA model name format (`meta-llama/` → `meta/`)
- [x] Set `max_retries=0` to eliminate 30-second SDK retry waits
- [x] Verified compression test works (watermark breached, ChromaDB saved, metrics updated)
- [x] Pushed all changes to GitHub

---

## ❓ Questions to Think About Before Day 5

1. The dashboard polls every 3 seconds using `setInterval`. What would be a more efficient alternative for true real-time updates? *(Hint: WebSockets or Server-Sent Events)*

2. Right now, `metrics:activity_log` only keeps the last 20 events. How could you persist a full historical log without running out of Redis memory? *(Hint: time-series bucket or a separate append-only log)*

3. What would happen to the context if Token-Sentry compressed the history but the user asked a question that was only answerable from a very old chunk that ranked 6th in ChromaDB relevance (below our top-5 cutoff)?

4. The `routing_efficiency_pct` shows what % of requests went to the cheap model. Why might a very high percentage (e.g. 95%) actually be *bad* for some users? *(Hint: think about what types of questions get classified as SIMPLE)*
