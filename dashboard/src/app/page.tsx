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
  activity_log?: ActivityEvent[];
}

const EVENT_META: Record<string, { label: string; icon: string; color: string }> = {
  tokens_saved:          { label: "Tokens Saved",        icon: "🗜️",  color: "#22d3a0" },
  requests_served:       { label: "Request Served",       icon: "📡",  color: "#60a5fa" },
  fallback_events:       { label: "Provider Fallback",    icon: "⚡",  color: "#fbbf24" },
  simple_intents_routed: { label: "Routed to Fast Model", icon: "🏎️", color: "#22d3a0" },
  compression_runs:      { label: "Compression Run",      icon: "🔧",  color: "#a78bfa" },
};

function timeAgo(ts: number): string {
  const diff = Math.floor(Date.now() / 1000) - ts;
  if (diff < 5)  return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  return `${Math.floor(diff / 3600)}h ago`;
}

function RingChart({ pct }: { pct: number }) {
  const r = 45;
  const circ = 2 * Math.PI * r;
  const offset = circ - (pct / 100) * circ;
  return (
    <div className="ring-container">
      <svg viewBox="0 0 100 100" width="110" height="110">
        <defs>
          <linearGradient id="ringGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#22d3a0" />
            <stop offset="100%" stopColor="#60a5fa" />
          </linearGradient>
        </defs>
        <circle className="ring-bg"   cx="50" cy="50" r={r} />
        <circle className="ring-fill" cx="50" cy="50" r={r}
          strokeDasharray={circ}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="ring-label">
        <span className="ring-pct">{pct}%</span>
        <span className="ring-sub">efficient</span>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [online, setOnline] = useState<boolean | null>(null);
  const [now, setNow] = useState(Date.now());

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
  const efficiency    = m.routing_efficiency_pct ?? 0;
  const activity      = m.activity_log ?? [];

  return (
    <div className="app">
      {/* ── Header ── */}
      <header className="header">
        <div className="header-left">
          <h1>🛡️ Token-Sentry Dashboard</h1>
          <p>Real-time Analytics & Gateway Intelligence</p>
        </div>
        <div className="status-badge">
          <div className={`status-dot${online === false ? " offline" : ""}`} />
          {online === null ? "Connecting..." : online ? "Gateway Online" : "Gateway Offline"}
        </div>
        <Link href="/docs" style={{ fontSize: "0.85rem", color: "var(--text-muted)", textDecoration: "none", padding: "0.4rem 1rem", border: "1px solid var(--border)", borderRadius: "999px", transition: "color 0.2s" }}>Docs ↗</Link>
      </header>

      {/* ── KPI Cards ── */}
      <div className="kpi-grid">
        <div className="kpi-card" style={{ "--accent": "#22d3a0" } as React.CSSProperties}>
          <span className="kpi-icon">🗜️</span>
          <div className="kpi-label">Tokens Saved</div>
          <div className="kpi-value">{tokensSaved.toLocaleString()}</div>
          <div className="kpi-sub">via context compression</div>
        </div>

        <div className="kpi-card" style={{ "--accent": "#22d3a0" } as React.CSSProperties}>
          <span className="kpi-icon">💰</span>
          <div className="kpi-label">Cost Saved</div>
          <div className="kpi-value">${costSaved.toFixed(4)}</div>
          <div className="kpi-sub">≈ $0.79 per 1M tokens</div>
        </div>

        <div className="kpi-card" style={{ "--accent": "#60a5fa" } as React.CSSProperties}>
          <span className="kpi-icon">📡</span>
          <div className="kpi-label">Requests Served</div>
          <div className="kpi-value">{requests.toLocaleString()}</div>
          <div className="kpi-sub">total API interactions</div>
        </div>

        <div className="kpi-card" style={{ "--accent": "#a78bfa" } as React.CSSProperties}>
          <span className="kpi-icon">🔧</span>
          <div className="kpi-label">Compression Runs</div>
          <div className="kpi-value">{compressions.toLocaleString()}</div>
          <div className="kpi-sub">history compacted</div>
        </div>

        <div className="kpi-card" style={{ "--accent": fallbacks > 0 ? "#fbbf24" : "#64748b" } as React.CSSProperties}>
          <span className="kpi-icon">⚡</span>
          <div className="kpi-label">Provider Fallbacks</div>
          <div className="kpi-value">{fallbacks.toLocaleString()}</div>
          <div className="kpi-sub">seamless failovers</div>
        </div>
      </div>

      {/* ── Two-column row ── */}
      <div className="two-col">
        {/* Intent Routing Breakdown */}
        <div className="panel">
          <div className="panel-title">🧠 Intent Routing Breakdown</div>
          <div className="routing-chart">
            <div className="bar-row">
              <div className="bar-meta">
                <span className="bar-label">Simple → Fast Model</span>
                <span className="bar-count">{simple} reqs</span>
              </div>
              <div className="bar-track">
                <div className="bar-fill green" style={{ width: requests ? `${(simple / requests) * 100}%` : "0%" }} />
              </div>
            </div>

            <div className="bar-row">
              <div className="bar-meta">
                <span className="bar-label">Complex → Main Model</span>
                <span className="bar-count">{complex} reqs</span>
              </div>
              <div className="bar-track">
                <div className="bar-fill blue" style={{ width: requests ? `${(complex / requests) * 100}%` : "0%" }} />
              </div>
            </div>

            <div className="bar-row">
              <div className="bar-meta">
                <span className="bar-label">Fallback Triggered</span>
                <span className="bar-count">{fallbacks} reqs</span>
              </div>
              <div className="bar-track">
                <div className="bar-fill amber" style={{ width: requests ? `${Math.min((fallbacks / requests) * 100, 100)}%` : "0%" }} />
              </div>
            </div>

            <div style={{ marginTop: "1rem", borderTop: "1px solid var(--border)", paddingTop: "1rem" }}>
              <div className="efficiency-wrapper">
                <RingChart pct={efficiency} />
                <div className="ring-stats">
                  <div className="ring-stat-row">
                    <span className="ring-stat-label">Simple routed</span>
                    <span className="ring-stat-val" style={{ color: "#22d3a0" }}>{simple}</span>
                  </div>
                  <div className="ring-stat-row">
                    <span className="ring-stat-label">Complex routed</span>
                    <span className="ring-stat-val" style={{ color: "#60a5fa" }}>{complex}</span>
                  </div>
                  <div className="ring-stat-row">
                    <span className="ring-stat-label">Total requests</span>
                    <span className="ring-stat-val" style={{ color: "var(--text)" }}>{requests}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Provider Health */}
        <div className="panel">
          <div className="panel-title">🔌 Provider Health</div>
          <div className="provider-list">
            <div className="provider-row">
              <div className="provider-info">
                <div className="provider-dot primary" />
                <div>
                  <div className="provider-name">Groq (Primary)</div>
                  <div className="provider-url">api.groq.com/openai/v1</div>
                </div>
              </div>
              <span className="provider-badge active">ACTIVE</span>
            </div>

            <div className="provider-row">
              <div className="provider-info">
                <div className="provider-dot fallback" />
                <div>
                  <div className="provider-name">NVIDIA NIM (Fallback)</div>
                  <div className="provider-url">integrate.api.nvidia.com/v1</div>
                </div>
              </div>
              <span className={`provider-badge ${fallbacks > 0 ? "triggered" : "standby"}`}>
                {fallbacks > 0 ? `${fallbacks}× USED` : "STANDBY"}
              </span>
            </div>
          </div>

          {/* System Config */}
          <div className="panel-title" style={{ marginTop: "1.5rem" }}>⚙️ System Config</div>
          <div className="config-list">
            {[
              { key: "Token Watermark",   val: "4,000 tokens" },
              { key: "Hot Buffer",        val: "3 turns" },
              { key: "SDK Retries",       val: "0 (instant failover)" },
              { key: "Vector Chunks",     val: "500 chars / 50 overlap" },
              { key: "Memory Recall",     val: "Top 5 chunks" },
              { key: "Polling Interval",  val: "3s" },
            ].map(({ key, val }) => (
              <div key={key} className="config-row">
                <span className="config-key">{key}</span>
                <span className="config-value">{val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── Full-width Activity Log ── */}
      <div className="panel">
        <div className="panel-title">📋 Live Activity Feed</div>
        {activity.length === 0 ? (
          <div className="no-activity">No activity yet — fire a request to see events appear here in real-time!</div>
        ) : (
          <div className="activity-list">
            {activity.map((evt, i) => {
              const meta = EVENT_META[evt.event] ?? { label: evt.event, icon: "•", color: "var(--text-muted)" };
              return (
                <div className="activity-item" key={i}>
                  <span className="activity-icon">{meta.icon}</span>
                  <div className="activity-body">
                    <div className="activity-event" style={{ color: meta.color }}>{meta.label}</div>
                    <div className="activity-time">{timeAgo(evt.ts)}</div>
                  </div>
                  {evt.amount > 1 && (
                    <span className="activity-amount" style={{ color: meta.color }}>+{evt.amount.toLocaleString()}</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
