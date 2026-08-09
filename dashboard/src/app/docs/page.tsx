"use client";

import Link from "next/link";
import { useState } from "react";
import "../globals.css";
import "./docs.css";

const SECTIONS = [
  { id: "overview",    label: "Overview" },
  { id: "quickstart",  label: "Quick Start" },
  { id: "api",         label: "API Reference" },
  { id: "providers",   label: "Providers" },
  { id: "memory",      label: "Memory Engine" },
  { id: "routing",     label: "Intent Routing" },
  { id: "dashboard",   label: "Dashboard" },
  { id: "env",         label: "Configuration" },
];

function CodeBlock({ code, lang = "bash" }: { code: string; lang?: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code.trim());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="code-block">
      <div className="code-header">
        <span className="code-lang">{lang}</span>
        <button className="copy-btn" onClick={copy}>{copied ? "✓ Copied" : "Copy"}</button>
      </div>
      <pre><code>{code.trim()}</code></pre>
    </div>
  );
}

function Badge({ text, color = "green" }: { text: string; color?: string }) {
  return <span className={`badge badge-${color}`}>{text}</span>;
}

function Endpoint({ method, path, desc }: { method: string; path: string; desc: string }) {
  const color = method === "GET" ? "blue" : method === "POST" ? "green" : "amber";
  return (
    <div className="endpoint-row">
      <span className={`method-badge method-${color}`}>{method}</span>
      <code className="endpoint-path">{path}</code>
      <span className="endpoint-desc">{desc}</span>
    </div>
  );
}

export default function Docs() {
  const [activeSection, setActiveSection] = useState("overview");

  const scrollTo = (id: string) => {
    setActiveSection(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="docs-app">
      {/* ── Top Nav ── */}
      <nav className="docs-topnav">
        <div className="docs-topnav-inner">
          <div className="docs-brand">🛡️ Token-Sentry <span className="docs-brand-tag">Docs</span></div>
          <div className="docs-topnav-links">
            <Link href="/" className="topnav-link">← Dashboard</Link>
            <a href="https://github.com/SayantanBong007/Token-Sentry" target="_blank" className="topnav-link">GitHub ↗</a>
          </div>
        </div>
      </nav>

      <div className="docs-layout">
        {/* ── Sidebar ── */}
        <aside className="docs-sidebar">
          <div className="sidebar-label">On this page</div>
          <ul className="sidebar-list">
            {SECTIONS.map((s) => (
              <li key={s.id}>
                <button
                  className={`sidebar-link${activeSection === s.id ? " active" : ""}`}
                  onClick={() => scrollTo(s.id)}
                >
                  {s.label}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        {/* ── Content ── */}
        <main className="docs-content">

          {/* ── Overview ── */}
          <section id="overview">
            <h1 className="docs-h1">Token-Sentry Documentation</h1>
            <p className="docs-lead">
              Token-Sentry is an intelligent, OpenAI-compatible API gateway that sits between your application
              and any LLM provider. It automatically compresses conversation history, routes simple
              requests to cheaper models, and silently falls back to a secondary provider if the primary
              hits a rate limit.
            </p>

            <div className="feature-grid">
              {[
                { icon: "🗜️", title: "Context Compression", desc: "Automatically summarizes old conversation turns when the token watermark is crossed, saving up to 80% of context tokens." },
                { icon: "🧠", title: "Intent Routing",      desc: "Classifies each request as SIMPLE or COMPLEX and routes it to the cheapest model that can handle it." },
                { icon: "⚡", title: "Provider Fallbacks",  desc: "If the primary provider (e.g. Groq) returns a 429, Token-Sentry instantly retries on the fallback (e.g. NVIDIA NIM) without breaking the stream." },
                { icon: "🔍", title: "Vector Memory",       desc: "Old messages are chunked, embedded, and stored in ChromaDB so the model can recall them semantically even after compression." },
              ].map((f) => (
                <div className="feature-card" key={f.title}>
                  <div className="feature-icon">{f.icon}</div>
                  <div className="feature-title">{f.title}</div>
                  <div className="feature-desc">{f.desc}</div>
                </div>
              ))}
            </div>
          </section>

          <div className="docs-divider" />

          {/* ── Quick Start ── */}
          <section id="quickstart">
            <h2 className="docs-h2">⚡ Quick Start</h2>
            <p className="docs-p">Get Token-Sentry running in under 2 minutes.</p>

            <div className="step-list">
              <div className="step">
                <div className="step-num">1</div>
                <div className="step-body">
                  <div className="step-title">Clone the repository</div>
                  <CodeBlock lang="bash" code={`git clone https://github.com/SayantanBong007/Token-Sentry.git
cd Token-Sentry`} />
                </div>
              </div>

              <div className="step">
                <div className="step-num">2</div>
                <div className="step-body">
                  <div className="step-title">Configure your providers in <code>.env</code></div>
                  <CodeBlock lang="bash" code={`# Primary Provider (Groq)
PRIMARY_PROVIDER_URL=https://api.groq.com/openai/v1
PRIMARY_API_KEY=gsk_your_groq_key_here
PRIMARY_MAIN_MODEL=llama-3.3-70b-versatile
PRIMARY_SUMMARIZER_MODEL=llama-3.1-8b-instant

# Fallback Provider (NVIDIA NIM)
FALLBACK_PROVIDER_URL=https://integrate.api.nvidia.com/v1
FALLBACK_API_KEY=nvapi-your_nvidia_key_here
FALLBACK_MAIN_MODEL=meta/llama-3.3-70b-instruct
FALLBACK_SUMMARIZER_MODEL=meta/llama-3.1-8b-instruct`} />
                </div>
              </div>

              <div className="step">
                <div className="step-num">3</div>
                <div className="step-body">
                  <div className="step-title">Start the Docker stack</div>
                  <CodeBlock lang="bash" code="docker-compose up -d --build" />
                </div>
              </div>

              <div className="step">
                <div className="step-num">4</div>
                <div className="step-body">
                  <div className="step-title">Send your first request</div>
                  <CodeBlock lang="python" code={`from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="not-needed"
)

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": "Hello!"}],
    extra_headers={"X-Session-ID": "my-session"}
)
print(response.choices[0].message.content)`} />
                </div>
              </div>
            </div>
          </section>

          <div className="docs-divider" />

          {/* ── API Reference ── */}
          <section id="api">
            <h2 className="docs-h2">📡 API Reference</h2>
            <p className="docs-p">
              Token-Sentry exposes a fully <strong>OpenAI-compatible</strong> REST API.
              Any client that works with OpenAI works with Token-Sentry — just change <code>base_url</code>.
            </p>

            <div className="endpoint-table">
              <Endpoint method="POST" path="/v1/chat/completions" desc="Main chat endpoint. Accepts the OpenAI request format." />
              <Endpoint method="GET"  path="/health"              desc="Health check. Returns gateway status and active model config." />
              <Endpoint method="GET"  path="/api/metrics"         desc="Real-time analytics — tokens saved, routing stats, fallback counts." />
              <Endpoint method="GET"  path="/"                    desc="Gateway info and provider summary." />
              <Endpoint method="GET"  path="/docs"                desc="FastAPI auto-generated Swagger docs." />
            </div>

            <h3 className="docs-h3">Special Headers</h3>
            <div className="table-wrapper">
              <table className="docs-table">
                <thead><tr><th>Header</th><th>Required</th><th>Description</th></tr></thead>
                <tbody>
                  <tr>
                    <td><code>X-Session-ID</code></td>
                    <td><Badge text="Optional" color="blue" /></td>
                    <td>When present, enables <strong>Stateful Mode</strong>. Token-Sentry stores and manages conversation history in Redis. Omit it for Passthrough/Agent mode.</td>
                  </tr>
                  <tr>
                    <td><code>Content-Type</code></td>
                    <td><Badge text="Required" color="green" /></td>
                    <td>Must be <code>application/json</code>.</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <h3 className="docs-h3">Streaming Example (cURL)</h3>
            <CodeBlock lang="bash" code={`curl -X POST http://localhost:8000/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -H "X-Session-ID: my-session-123" \\
  -d '{
    "model": "llama-3.3-70b-versatile",
    "messages": [{"role": "user", "content": "Explain quantum computing"}],
    "stream": true
  }'`} />

            <h3 className="docs-h3">Python (Agentic / No Memory)</h3>
            <CodeBlock lang="python" code={`from openai import OpenAI

# No X-Session-ID = passthrough mode (agents manage their own memory)
client = OpenAI(base_url="http://localhost:8000/v1", api_key="not-needed")

response = client.chat.completions.create(
    model="gpt-4o",  # mapped automatically to llama-3.3-70b-versatile
    messages=[{"role": "user", "content": "Analyze this code..."}],
    stream=True,
)
for chunk in response:
    print(chunk.choices[0].delta.content or "", end="")`} />

            <h3 className="docs-h3">Node.js</h3>
            <CodeBlock lang="typescript" code={`import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "http://localhost:8000/v1",
  apiKey: "not-needed",
});

const response = await client.chat.completions.create({
  model: "llama-3.3-70b-versatile",
  messages: [{ role: "user", content: "Hello!" }],
  // @ts-ignore — OpenAI SDK passes extra_headers through
  headers: { "X-Session-ID": "node-session-1" },
});
console.log(response.choices[0].message.content);`} />
          </section>

          <div className="docs-divider" />

          {/* ── Providers ── */}
          <section id="providers">
            <h2 className="docs-h2">🔌 Providers</h2>
            <p className="docs-p">
              Token-Sentry uses the <strong>OpenAI SDK</strong> with a custom <code>base_url</code> to talk
              to any OpenAI-compatible provider. <code>max_retries=0</code> is set on the primary client so
              that rate-limit errors are caught <em>immediately</em> by our own fallback logic — no 30-second waits.
            </p>

            <div className="table-wrapper">
              <table className="docs-table">
                <thead><tr><th>Provider</th><th>base_url</th><th>Role</th><th>Notes</th></tr></thead>
                <tbody>
                  <tr>
                    <td>Groq</td>
                    <td><code>api.groq.com/openai/v1</code></td>
                    <td><Badge text="Primary" color="green" /></td>
                    <td>Fastest inference. Free tier available.</td>
                  </tr>
                  <tr>
                    <td>NVIDIA NIM</td>
                    <td><code>integrate.api.nvidia.com/v1</code></td>
                    <td><Badge text="Fallback" color="blue" /></td>
                    <td>Use <code>meta/</code> prefix for model names.</td>
                  </tr>
                  <tr>
                    <td>OpenRouter</td>
                    <td><code>openrouter.ai/api/v1</code></td>
                    <td><Badge text="Fallback" color="blue" /></td>
                    <td>Access 100+ models via one API key.</td>
                  </tr>
                  <tr>
                    <td>Together AI</td>
                    <td><code>api.together.xyz/v1</code></td>
                    <td><Badge text="Fallback" color="blue" /></td>
                    <td>Drop-in replacement for OpenRouter.</td>
                  </tr>
                  <tr>
                    <td>OpenAI</td>
                    <td><code>api.openai.com/v1</code></td>
                    <td><Badge text="Any" color="amber" /></td>
                    <td>Can be used as primary or fallback.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <div className="docs-divider" />

          {/* ── Memory ── */}
          <section id="memory">
            <h2 className="docs-h2">🧠 Memory Engine</h2>
            <p className="docs-p">
              Token-Sentry has a two-tier memory system. When a session is in Stateful Mode
              (i.e. requests include an <code>X-Session-ID</code>), the gateway manages memory automatically.
            </p>

            <div className="tier-list">
              <div className="tier">
                <div className="tier-header">
                  <span className="tier-icon">🔥</span>
                  <div>
                    <div className="tier-name">Hot Memory (Redis)</div>
                    <Badge text="Recent turns" color="green" />
                  </div>
                </div>
                <p className="docs-p">The last <strong>N turns</strong> (default: 3) of conversation are stored verbatim in Redis. These are always injected into every request so the model has fresh context.</p>
              </div>

              <div className="tier">
                <div className="tier-header">
                  <span className="tier-icon">❄️</span>
                  <div>
                    <div className="tier-name">Cold Memory (ChromaDB)</div>
                    <Badge text="Compressed history" color="blue" />
                  </div>
                </div>
                <p className="docs-p">When the total token count exceeds the <code>TOKEN_HIGH_WATERMARK</code>, old messages are summarized by the fast model, chunked into 500-character overlapping segments, and stored as vector embeddings. When a new question arrives, the top 5 most semantically relevant chunks are recalled and injected as a System Memory Card.</p>
              </div>
            </div>

            <h3 className="docs-h3">Flow Diagram</h3>
            <CodeBlock lang="text" code={`User Request
     │
     ▼
[Load Session from Redis]
     │
     ▼
[Recall Top-5 Chunks from ChromaDB] (semantic search)
     │
     ▼
[Count Tokens]
     │
     ├── Under watermark? ──────────────▶ Forward to LLM
     │
     └── Over watermark?
              │
              ▼
         [Compress History]
         - Summarize cold turns with fast model
         - Chunk & embed into ChromaDB
         - Keep only hot buffer + summary card
              │
              ▼
         [Forward compressed payload to LLM]`} />
          </section>

          <div className="docs-divider" />

          {/* ── Routing ── */}
          <section id="routing">
            <h2 className="docs-h2">🧭 Intent Routing</h2>
            <p className="docs-p">
              Every incoming request (when <code>ENABLE_INTENT_ROUTING=true</code>) is first classified
              as <strong>SIMPLE</strong> or <strong>COMPLEX</strong> by the fast summarizer model.
            </p>
            <div className="table-wrapper">
              <table className="docs-table">
                <thead><tr><th>Intent</th><th>Model Used</th><th>Examples</th></tr></thead>
                <tbody>
                  <tr>
                    <td><Badge text="SIMPLE" color="green" /></td>
                    <td><code>PRIMARY_SUMMARIZER_MODEL</code></td>
                    <td>"What is 2+2?", "Say hello", "What day is it?"</td>
                  </tr>
                  <tr>
                    <td><Badge text="COMPLEX" color="amber" /></td>
                    <td><code>PRIMARY_MAIN_MODEL</code></td>
                    <td>"Write a full REST API", "Explain quantum physics", "Debug this code"</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <div className="docs-divider" />

          {/* ── Dashboard ── */}
          <section id="dashboard">
            <h2 className="docs-h2">📊 Analytics Dashboard</h2>
            <p className="docs-p">A Next.js dashboard is included at <code>/dashboard</code>. Run it with:</p>
            <CodeBlock lang="bash" code={`cd dashboard
npm install
npm run dev
# Open http://localhost:3000`} />
            <p className="docs-p" style={{ marginTop: "1rem" }}>The dashboard live-polls <code>GET /api/metrics</code> every 3 seconds and displays:</p>
            <ul className="docs-list">
              <li>Tokens Saved & Estimated Cost Saved</li>
              <li>Total Requests Served & Compression Runs</li>
              <li>Intent Routing Breakdown (bar chart + efficiency ring)</li>
              <li>Provider Health (Primary / Fallback status)</li>
              <li>System Configuration at a glance</li>
              <li>Live Activity Feed (last 15 events with timestamps)</li>
            </ul>
          </section>

          <div className="docs-divider" />

          {/* ── Env ── */}
          <section id="env">
            <h2 className="docs-h2">⚙️ Configuration Reference</h2>
            <div className="table-wrapper">
              <table className="docs-table">
                <thead><tr><th>Variable</th><th>Default</th><th>Description</th></tr></thead>
                <tbody>
                  {[
                    ["PRIMARY_PROVIDER_URL",    "https://api.groq.com/openai/v1", "Base URL for the primary LLM provider"],
                    ["PRIMARY_API_KEY",         "—",                              "API key for the primary provider"],
                    ["PRIMARY_MAIN_MODEL",      "llama-3.3-70b-versatile",        "Main model for complex requests"],
                    ["PRIMARY_SUMMARIZER_MODEL","llama-3.1-8b-instant",           "Fast model for simple requests & compression"],
                    ["FALLBACK_PROVIDER_URL",   "https://integrate.api.nvidia.com/v1","Base URL for the fallback provider"],
                    ["FALLBACK_API_KEY",        "—",                              "API key for the fallback provider"],
                    ["FALLBACK_MAIN_MODEL",     "meta/llama-3.3-70b-instruct",    "Fallback main model"],
                    ["TOKEN_HIGH_WATERMARK",    "4000",                           "Token count that triggers context compression"],
                    ["HOT_BUFFER_TURNS",        "3",                              "Number of recent turns kept verbatim in Redis"],
                    ["ENABLE_INTENT_ROUTING",   "true",                           "Enable/disable intent-based model routing"],
                    ["REDIS_URL",               "redis://redis:6379",             "Redis connection URL"],
                    ["LOG_LEVEL",               "INFO",                           "Logging level (DEBUG, INFO, WARNING, ERROR)"],
                    ["ENV",                     "development",                    "Environment name"],
                    ["PORT",                    "8000",                           "Port the gateway listens on"],
                  ].map(([key, def, desc]) => (
                    <tr key={key}>
                      <td><code>{key}</code></td>
                      <td><code className="muted">{def}</code></td>
                      <td>{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

        </main>
      </div>
    </div>
  );
}
