"use client";

import { useEffect, useState } from "react";

interface Metrics {
  tokens_saved?: number;
  requests_served?: number;
  fallback_events?: number;
  cost_saved_usd?: number;
  simple_intents_routed?: number;
}

export default function Dashboard() {
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        const res = await fetch("http://localhost:8000/api/metrics");
        if (!res.ok) throw new Error("Failed to fetch metrics");
        const data = await res.json();
        setMetrics(data);
      } catch (err) {
        console.error(err);
        setError("Unable to connect to Token-Sentry Gateway.");
      }
    };

    fetchMetrics();
    const interval = setInterval(fetchMetrics, 3000);
    return () => clearInterval(interval);
  }, []);

  if (error) {
    return (
      <main className="container">
        <header>
          <h1>Token-Sentry Analytics</h1>
          <p className="subtitle">Real-time Performance & Savings</p>
        </header>
        <div className="loading" style={{ color: "#ef4444" }}>{error}</div>
      </main>
    );
  }

  if (!metrics) {
    return (
      <main className="container">
        <header>
          <h1>Token-Sentry Analytics</h1>
          <p className="subtitle">Real-time Performance & Savings</p>
        </header>
        <div className="loading">Connecting to Gateway...</div>
      </main>
    );
  }

  return (
    <main className="container">
      <header>
        <h1>Token-Sentry Analytics</h1>
        <p className="subtitle">Real-time Performance & Savings</p>
      </header>

      <div className="grid">
        <div className="card highlight">
          <h3>Total Tokens Saved</h3>
          <div className="value">{metrics.tokens_saved?.toLocaleString() || 0}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>via Context Compression</p>
        </div>

        <div className="card highlight">
          <h3>Cost Saved (Approx)</h3>
          <div className="value">${metrics.cost_saved_usd?.toFixed(4) || "0.0000"}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>based on $0.79 / 1M tokens</p>
        </div>

        <div className="card">
          <h3>Total Requests Served</h3>
          <div className="value">{metrics.requests_served?.toLocaleString() || 0}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>Total API interactions</p>
        </div>

        <div className="card">
          <h3>Simple Intents Routed</h3>
          <div className="value">{metrics.simple_intents_routed?.toLocaleString() || 0}</div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>Offloaded to fast model</p>
        </div>

        <div className="card">
          <h3>Provider Fallbacks</h3>
          <div className="value" style={{ color: metrics.fallback_events ? "#f59e0b" : "var(--text)" }}>
            {metrics.fallback_events?.toLocaleString() || 0}
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>Seamless upstream failovers</p>
        </div>
      </div>
    </main>
  );
}
