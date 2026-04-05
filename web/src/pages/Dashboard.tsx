import { useCallback, useEffect, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { TrendingUp, TrendingDown, Minus, Activity, Play } from "lucide-react";

interface Ticker {
  ticker: string;
  total_mentions: number;
  avg_daily: number;
  peak_mentions: number;
  trend: "up" | "down" | "flat";
}

interface Status {
  configured: boolean;
  last_run_at: string | null;
  total_runs: number;
  total_alerts: number;
  tracked_tickers: number;
  is_healthy: boolean;
  crawl_running: boolean;
}

const trendIcon = {
  up: <TrendingUp size={14} className="text-green-400" />,
  down: <TrendingDown size={14} className="text-red-400" />,
  flat: <Minus size={14} className="text-zinc-500" />,
};

export default function Dashboard() {
  const [tickers, setTickers] = useState<Ticker[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [days, setDays] = useState(7);
  const [starting, setStarting] = useState(false);

  const refresh = useCallback(() => {
    fetch(`/api/tickers?days=${days}`)
      .then((r) => r.json())
      .then(setTickers);
    fetch("/api/status")
      .then((r) => r.json())
      .then(setStatus);
  }, [days]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Auto-Refresh während ein Crawl läuft
  useEffect(() => {
    if (!status?.crawl_running) return;
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, [status?.crawl_running, refresh]);

  const startCrawl = async () => {
    setStarting(true);
    try {
      await fetch("/api/crawl", { method: "POST" });
      refresh();
    } finally {
      setStarting(false);
    }
  };

  const crawlActive = starting || Boolean(status?.crawl_running);

  return (
    <div className="space-y-6">
      {/* Lauf-Banner */}
      {crawlActive && (
        <div className="flex items-center gap-3 rounded-lg bg-brand/10 border border-brand/30 px-4 py-3 text-sm text-brand">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-brand opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-brand" />
          </span>
          Crawl läuft — Dashboard aktualisiert sich automatisch…
        </div>
      )}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Dashboard</h1>
        <div className="flex gap-2 items-center">
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1 rounded-lg text-sm transition-colors ${
                days === d
                  ? "bg-brand text-white"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
              }`}
            >
              {d}d
            </button>
          ))}
          <button
            onClick={startCrawl}
            disabled={crawlActive}
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-sm font-medium transition-colors bg-brand text-white hover:bg-brand/80 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Play size={12} />
            {crawlActive ? "Läuft…" : "Lauf starten"}
          </button>
        </div>
      </div>

      {/* Status-Karten */}
      {status && (
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {[
            { label: "Crawl-Runs", value: status.total_runs },
            { label: "Alerts gesamt", value: status.total_alerts },
            { label: "Ticker getrackt", value: status.tracked_tickers },
            {
              label: "Letzter Lauf",
              value: status.last_run_at
                ? new Date(status.last_run_at).toLocaleTimeString("de-DE", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "—",
            },
          ].map(({ label, value }) => (
            <div key={label} className="card">
              <div className="text-zinc-500 text-xs mb-1">{label}</div>
              <div className="text-2xl font-bold">{value}</div>
            </div>
          ))}
        </div>
      )}

      {/* Top-Ticker Chart */}
      <div className="card">
        <h2 className="text-sm font-semibold text-zinc-400 mb-4 flex items-center gap-2">
          <Activity size={14} />
          Top-Ticker (letzte {days} Tage)
        </h2>
        {tickers.length === 0 ? (
          <p className="text-zinc-600 text-sm text-center py-8">
            Noch keine Daten. Starte den ersten Crawl-Lauf.
          </p>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={tickers.slice(0, 15)} layout="vertical" margin={{ left: 10, right: 20 }}>
              <XAxis type="number" tick={{ fill: "#71717a", fontSize: 11 }} />
              <YAxis
                type="category"
                dataKey="ticker"
                tick={{ fill: "#a1a1aa", fontSize: 12 }}
                width={45}
              />
              <Tooltip
                contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
                labelStyle={{ color: "#fff" }}
                formatter={(v: number) => [`${v} Erwähnungen`, ""]}
              />
              <Bar dataKey="total_mentions" radius={[0, 4, 4, 0]}>
                {tickers.map((t, i) => (
                  <Cell
                    key={i}
                    fill={t.trend === "up" ? "#22c55e" : t.trend === "down" ? "#ef4444" : "#FF4500"}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Ticker-Tabelle */}
      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              {["Ticker", "Nennungen", "Ø/Tag", "Peak", "Trend"].map((h) => (
                <th key={h} className="text-left text-zinc-500 font-medium px-4 py-3 text-xs uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {tickers.map((t) => (
              <tr key={t.ticker} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                <td className="px-4 py-3 font-mono font-bold text-white">${t.ticker}</td>
                <td className="px-4 py-3 tabular-nums">{t.total_mentions}</td>
                <td className="px-4 py-3 tabular-nums text-zinc-400">{t.avg_daily}</td>
                <td className="px-4 py-3 tabular-nums text-zinc-400">{t.peak_mentions}</td>
                <td className="px-4 py-3">{trendIcon[t.trend]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
