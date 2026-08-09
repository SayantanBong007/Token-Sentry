"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import "./globals.css";

interface ActivityEvent {
  ts: number;
  event: string;
  amount: number;
}

interface Metrics {
  tokens_saved?: number;
  requests_served?: number;
  fallback_events?: number;
  cost_saved_usd?: number;
  simple_intents_routed?: number;
  complex_intents_routed?: number;
  compression_runs?: number;
  routing_efficiency_pct?: number;
  tokens_groq?: number;
  tokens_nim?: number;
  avg_latency_ms?: number;
  activity_log?: ActivityEvent[];
}

const EVENT_META: Record<string, { label: string; icon: string; color: string }> = {
  tokens_saved:          { label: "Tokens Compressed",    icon: "🗜️",  color: "var(--primary)" },
  requests_served:       { label: "Request Served",       icon: "📡",  color: "var(--secondary)" },
  fallback_events:       { label: "Provider Fallback",    icon: "⚡",  color: "var(--warning)" },
  simple_intents_routed: { label: "Routed to Fast Model", icon: "🏎️", color: "var(--primary)" },
  compression_runs:      { label: "Compression Run",      icon: "🧠",  color: "var(--accent)" },
};

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 5)  return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [, setNow] = useState(Date.now());

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/metrics");
        if (!res.ok) throw new Error();
        const data = await res.json();
        setMetrics(data);
        setOnline(true);
      } catch {
        setOnline(false);
      }
    };

    fetchMetrics();
    const poll = setInterval(fetchMetrics, 3000);
    const tick = setInterval(() => setNow(Date.now()), 10000);
    return () => { clearInterval(poll); clearInterval(tick); };
  }, []);

  const m = metrics ?? {};
  const requests      = m.requests_served ?? 0;
  const simple        = m.simple_intents_routed ?? 0;
  const complex       = m.complex_intents_routed ?? 0;
  const fallbacks     = m.fallback_events ?? 0;
  const tokensSaved   = m.tokens_saved ?? 0;
  const costSaved     = m.cost_saved_usd ?? 0;
  const compressions  = m.compression_runs ?? 0;
  const tokensGroq    = m.tokens_groq ?? 0;
  const tokensNim     = m.tokens_nim ?? 0;
  const avgLatency    = m.avg_latency_ms ?? 0;
  const activity      = m.activity_log ?? [];

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-left">
          <h1>🛡️ Token-Sentry Dashboard</h1>
          <p>Real-time AI Proxy Analytics & Intelligence</p>
        </div>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <div className={`status-badge ${online === false ? "offline" : ""}`}>
            <div className={`status-dot ${online === false ? "offline" : ""}`} />
            {online === null ? "Connecting..." : online ? "Gateway Online" : "Gateway Offline"}
          </div>
          <Link href="/docs" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Docs ↗</Link>
        </div>
      </header>

      {/* ── Architecture Visualizer ── */}
      <div className="viz-panel">
        <div className="viz-title">🔍 Live Request Pipeline</div>
        <div className="flow-container">
          <div className="flow-node">
            <span className="node-icon">💻</span>
            <div className="node-title">Client App</div>
            <div className="node-desc">AI Agents (ArchFox)</div>
          </div>
          
          <div className="flow-arrow">→</div>
          
          <div className="flow-node" style={{ borderColor: 'var(--primary)', boxShadow: '0 0 15px var(--primary-glow)' }}>
            <span className="node-icon">🛡️</span>
            <div className="node-title">Token-Sentry</div>
            <div className="node-desc">Map-Reduce & Routing</div>
          </div>
          
          <div className="flow-arrow">→</div>
          
          <div className="flow-node">
            <span className="node-icon">☁️</span>
            <div className="node-title">Provider API</div>
            <div className="node-desc">Groq / NIM</div>
          </div>
        </div>
      </div>

      {/* ── KPI Grid ── */}
      <div className="kpi-grid">
        <div className="kpi-card" style={{ "--color": "var(--primary)", "--color-glow": "var(--primary-glow)" } as React.CSSProperties}>
          <div className="kpi-header">
            <div className="kpi-icon" style={{ color: "var(--primary)" }}>🗜️</div>
            <div className="kpi-label">Tokens Saved</div>
          </div>
          <div className="kpi-value">{tokensSaved.toLocaleString()}</div>
          <div className="kpi-desc">Number of context tokens avoided by summarizing huge histories & payloads.</div>
        </div>

        <div className="kpi-card" style={{ "--color": "var(--primary)", "--color-glow": "var(--primary-glow)" } as React.CSSProperties}>
          <div className="kpi-header">
            <div className="kpi-icon" style={{ color: "var(--primary)" }}>💰</div>
            <div className="kpi-label">Cost Saved</div>
          </div>
          <div className="kpi-value">${costSaved.toFixed(4)}</div>
          <div className="kpi-desc">Calculated at a rate of roughly $0.79 per 1M tokens saved from the main model.</div>
        </div>

        <div className="kpi-card" style={{ "--color": "var(--accent)", "--color-glow": "var(--accent-glow)" } as React.CSSProperties}>
          <div className="kpi-header">
            <div className="kpi-icon" style={{ color: "var(--accent)" }}>🧠</div>
            <div className="kpi-label">Compression Runs</div>
          </div>
          <div className="kpi-value">{compressions.toLocaleString()}</div>
          <div className="kpi-desc">Times Token-Sentry actively map-reduced or summarized context.</div>
        </div>

        <div className="kpi-card" style={{ "--color": "var(--secondary)", "--color-glow": "var(--secondary-glow)" } as React.CSSProperties}>
          <div className="kpi-header">
            <div className="kpi-icon" style={{ color: "var(--secondary)" }}>⏱️</div>
            <div className="kpi-label">Average Latency</div>
          </div>
          <div className="kpi-value">{avgLatency > 0 ? `${avgLatency}ms` : "-"}</div>
          <div className="kpi-desc">Total average latency across all routed model requests.</div>
        </div>

        <div className="kpi-card" style={{ "--color": "var(--accent)", "--color-glow": "var(--accent-glow)" } as React.CSSProperties}>
          <div className="kpi-header">
            <div className="kpi-icon" style={{ color: "var(--accent)" }}>📡</div>
            <div className="kpi-label">Total Requests</div>
          </div>
          <div className="kpi-value">{requests.toLocaleString()}</div>
          <div className="kpi-desc">Total number of API interactions handled by the Sentry gateway.</div>
        </div>
      </div>

      {/* ── Two-column row ── */}
      <div className="two-col">
        {/* Intent & Routing */}
        <div className="panel">
          <div className="panel-title">🏎️ Traffic Routing & Fallbacks</div>
          <div className="bar-row">
            <div className="bar-meta">
              <span className="bar-label">Routed to Cheap Model (Simple Intents)</span>
              <span className="bar-count">{simple}</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill green" style={{ width: requests ? `${(simple / requests) * 100}%` : "0%" }} />
            </div>
          </div>

          <div className="bar-row">
            <div className="bar-meta">
              <span className="bar-label">Routed to Main Model (Complex Intents)</span>
              <span className="bar-count">{complex}</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill blue" style={{ width: requests ? `${(complex / requests) * 100}%` : "0%" }} />
            </div>
          </div>

          <div className="bar-row">
            <div className="bar-meta">
              <span className="bar-label">Rate-Limit Fallbacks (NVIDIA NIM)</span>
              <span className="bar-count" style={{ color: "var(--warning)" }}>{fallbacks}</span>
            </div>
            <div className="bar-track">
              <div className="bar-fill amber" style={{ width: requests ? `${Math.min((fallbacks / requests) * 100, 100)}%` : "0%" }} />
            </div>
          </div>
          
          <div style={{ marginTop: "2rem", borderTop: "1px dashed var(--border)", paddingTop: "1.5rem" }}>
            <div className="panel-title">📊 Token Distribution by Provider</div>
            <div className="bar-row">
              <div className="bar-meta">
                <span className="bar-label">Groq Llama 3.1 8B</span>
                <span className="bar-count">{tokensGroq.toLocaleString()} tokens</span>
              </div>
              <div className="bar-track">
                <div className="bar-fill green" style={{ width: (tokensGroq + tokensNim) ? `${(tokensGroq / (tokensGroq + tokensNim)) * 100}%` : "0%" }} />
              </div>
            </div>
            
            <div className="bar-row">
              <div className="bar-meta">
                <span className="bar-label">NVIDIA NIM (Fallback)</span>
                <span className="bar-count" style={{ color: "var(--warning)" }}>{tokensNim.toLocaleString()} tokens</span>
              </div>
              <div className="bar-track">
                <div className="bar-fill amber" style={{ width: (tokensGroq + tokensNim) ? `${(tokensNim / (tokensGroq + tokensNim)) * 100}%` : "0%" }} />
              </div>
            </div>
          </div>
          
          <div style={{ marginTop: "2rem", borderTop: "1px dashed var(--border)", paddingTop: "1.5rem" }}>
            <div className="panel-title">🔌 Active Providers</div>
            <div className="provider-row">
              <div className="provider-info">
                <div className="status-dot" style={{ background: "var(--primary)", boxShadow: "0 0 10px var(--primary)" }} />
                <div>
                  <div className="provider-name">Groq Llama 3.1 8B</div>
                  <div className="provider-url">api.groq.com/openai/v1</div>
                </div>
              </div>
              <span className="provider-badge active">PRIMARY</span>
            </div>
            <div className="provider-row">
              <div className="provider-info">
                <div className="status-dot" style={{ background: "var(--warning)", boxShadow: "0 0 10px var(--warning)", animation: "none" }} />
                <div>
                  <div className="provider-name">NVIDIA NIM Llama 3.1 8B</div>
                  <div className="provider-url">integrate.api.nvidia.com/v1</div>
                </div>
              </div>
              <span className={`provider-badge ${fallbacks > 0 ? "triggered" : "standby"}`}>
                {fallbacks > 0 ? `${fallbacks}x TRIGGERED` : "STANDBY"}
              </span>
            </div>
          </div>
        </div>

        {/* Activity & Config */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          <div className="panel" style={{ flex: 1 }}>
            <div className="panel-title">📋 Live Activity Log</div>
            {activity.length === 0 ? (
              <div className="no-data">No activity yet. Start sending requests to Token-Sentry!</div>
            ) : (
              <div className="activity-list">
                {activity.map((evt, i) => {
                  const meta = EVENT_META[evt.event] ?? { label: evt.event, icon: "•", color: "var(--text-muted)" };
                  return (
                    <div className="activity-item" key={i}>
                      <div className="activity-icon-box" style={{ color: meta.color, borderColor: meta.color }}>
                        {meta.icon}
                      </div>
                      <div className="activity-body">
                        <div className="activity-title" style={{ color: meta.color }}>{meta.label}</div>
                        <div className="activity-time">{timeAgo(evt.ts)}</div>
                      </div>
                      {evt.amount > 0 && (
                        <div className="activity-val" style={{ color: meta.color }}>+{evt.amount.toLocaleString()}</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
          
          <div className="panel">
            <div className="panel-title">⚙️ Gateway Config</div>
            <div className="config-grid">
              <div className="config-item">
                <div className="config-label">Compression Trigger</div>
                <div className="config-val">4,000 Tokens</div>
              </div>
              <div className="config-item">
                <div className="config-label">Map-Reduce Chunk</div>
                <div className="config-val">12,000 Chars</div>
              </div>
              <div className="config-item">
                <div className="config-label">Hot Buffer</div>
                <div className="config-val">Last 3 Turns</div>
              </div>
              <div className="config-item">
                <div className="config-label">Failover Mode</div>
                <div className="config-val">Instant / 0 Retry</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
