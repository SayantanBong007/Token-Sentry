# Day 3: Intent Routing & Cold Memory

On Day 3, we successfully implemented two major features that transform Token-Sentry into a production-grade, cost-optimized proxy with infinite memory.

## 1. Intent Routing (Cost Saver)

**Goal:** Route simple, conversational queries to a much cheaper model instead of spinning up the massive 70B model for every single request.

- **How it works:** We added an Intent Classifier (`src/routing/intent_classifier.py`) that uses `llama-3.1-8b-instant` to evaluate the user's latest prompt.
- **Routing Logic (`src/proxy/router.py`):**
  - If the prompt is simple (e.g., greetings, factual questions), the router overrides the model and forwards it to the 8B model.
  - If the prompt is complex (e.g., coding, deep logic), it passes through to the requested 70B model.
- **Observability:** Added an `X-Intent: simple/complex` HTTP Header so client applications can observe the routing decision.

## 2. Cold Memory (Vector Database)

**Goal:** Maintain an infinite context window without blowing up token counts or costs.

### How ChromaDB & Semantic Search Works (Deep Dive)
When conversations get incredibly long, you can't just delete old messages, but you also can't keep sending them to the AI (it costs too much and slows things down). We use **ChromaDB**, an embedded vector database, to solve this:

1. **Embeddings (Math Magic):** Instead of storing raw text, Token-Sentry uses `sentence-transformers` to convert your old messages into "vectors" (lists of thousands of numbers). These numbers represent the *meaning* and *context* of the sentence, not just the raw words.
2. **The Vector Space:** ChromaDB plots these vectors in a multi-dimensional graph. Sentences with similar meanings (e.g., "I own a dog" and "My puppy is cute") are plotted physically close to each other in this graph, even if they don't share exact words.
3. **Semantic Retrieval:** When you ask a new question (e.g., "What pets do I have?"), Token-Sentry converts your question into a vector and plots it on the graph. ChromaDB instantly finds the closest surrounding vectors (your old messages) and pulls them out. 
4. **Infinite Memory:** We then take those exact relevant past messages and secretly inject them into the prompt sent to Groq. The AI now magically remembers what you said 3 weeks ago without having to read the entire 3-week conversation history!

### Implementation Details
- **Storage (`src/memory/vector_store.py`):** Integrated `chromadb` (Chroma Vector Database) along with local Sentence Transformers.
- **Archiving (`src/memory/compressor.py`):** When the token watermark is breached (e.g., 4000 tokens), the "cold" (old) messages are converted into semantic vectors and saved to ChromaDB before being compressed out of the active hot memory.
- **Retrieval (`src/proxy/router.py`):** On every incoming request, Token-Sentry queries the vector database for the top 3 most semantically relevant ancient messages and injects them seamlessly into the system prompt: `🧠 Retained Context from Past Interactions: ...`

## Stack Updates

- Added `chromadb` and `sentence-transformers` to `requirements.txt`.
- Pinned `numpy<2.0.0` to resolve compatibility issues with ChromaDB.
- Updated `Dockerfile` to install CPU-only PyTorch and essential build tools, keeping the Docker image optimized.
- Added a `./data:/app/data` volume mount in `docker-compose.yml` to persist the ChromaDB vector database locally across container restarts.

## How to Test

You can test these features directly against your running Docker stack:

### Test Intent Routing
**Simple:**
```powershell
curl.exe -i -X POST http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -H "X-Session-ID: doc-test" -d '{"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Hello!"}]}'
```
*(Check headers for `X-Intent: simple`)*

**Complex:**
```powershell
curl.exe -i -X POST http://localhost:8000/v1/chat/completions -H "Content-Type: application/json" -H "X-Session-ID: doc-test" -d '{"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": "Write a python script for a snake game."}]}'
```
*(Check headers for `X-Intent: complex`)*

### Test Cold Memory
To test Cold Memory quickly without typing 4000 tokens:
1. Temporarily change `TOKEN_HIGH_WATERMARK=100` in `.env`.
2. Restart the container: `docker compose restart token-sentry`
3. Tell the bot: "My favorite color is neon green." (This breaches 100 tokens and is pushed to ChromaDB).
4. Send a few random messages to clear the hot buffer.
5. Ask: "What is my favorite color?"
6. Token-Sentry will perform a semantic search, inject the past context, and answer "Neon green" flawlessly!
