import { useEffect, useState } from "react";

interface AlertEntry {
  id: number;
  ticker: string;
  reason: string;
  mentions: number;
  avg_mentions: number;
  ratio: number;
  price: number | null;
  price_change: number | null;
  sent_at: string;
}

const reasonLabel: Record<string, { label: string; color: string }> = {
  new_ticker: { label: "Neu", color: "bg-blue-500/20 text-blue-400" },
  spike: { label: "Spike", color: "bg-brand/20 text-brand" },
  price_move: { label: "Kurs+Aktivität", color: "bg-amber-500/20 text-amber-400" },
};

export default function Alerts() {
  const [alerts, setAlerts] = useState<AlertEntry[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    const url = filter ? `/api/alerts?ticker=${filter.toUpperCase()}` : "/api/alerts?limit=100";
    fetch(url)
      .then((r) => r.json())
      .then(setAlerts);
  }, [filter]);

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Alert-History</h1>
        <input
          className="input w-40"
          placeholder="Ticker filtern…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      <div className="card overflow-hidden p-0">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-800">
              {["Zeit", "Ticker", "Typ", "Nennungen", "Faktor", "Kurs", "Änderung"].map((h) => (
                <th key={h} className="text-left text-zinc-500 font-medium px-4 py-3 text-xs uppercase tracking-wide">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {alerts.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center text-zinc-600 py-10">
                  Noch keine Alerts
                </td>
              </tr>
            ) : (
              alerts.map((a) => {
                const r = reasonLabel[a.reason] ?? { label: a.reason, color: "bg-zinc-700 text-zinc-300" };
                return (
                  <tr key={a.id} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="px-4 py-3 text-zinc-500 whitespace-nowrap">
                      {new Date(a.sent_at).toLocaleString("de-DE", {
                        day: "2-digit",
                        month: "2-digit",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </td>
                    <td className="px-4 py-3 font-mono font-bold">${a.ticker}</td>
                    <td className="px-4 py-3">
                      <span className={`badge ${r.color}`}>{r.label}</span>
                    </td>
                    <td className="px-4 py-3 tabular-nums">{a.mentions}</td>
                    <td className="px-4 py-3 tabular-nums">{a.ratio.toFixed(1)}x</td>
                    <td className="px-4 py-3 tabular-nums">
                      {a.price ? `$${a.price.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-4 py-3 tabular-nums">
                      {a.price_change !== null ? (
                        <span className={a.price_change >= 0 ? "text-green-400" : "text-red-400"}>
                          {a.price_change >= 0 ? "+" : ""}
                          {a.price_change.toFixed(2)}%
                        </span>
                      ) : (
                        "—"
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
