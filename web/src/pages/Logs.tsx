import { useEffect, useRef, useState } from "react";

export default function Logs() {
  const [lines, setLines] = useState<string[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const ws = new WebSocket(`ws://${location.host}/api/ws/logs`);
    ws.onmessage = (e) => {
      setLines((prev) => [...prev.slice(-500), e.data]);
    };
    return () => ws.close();
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  const levelColor = (line: string) => {
    if (line.includes("ERROR") || line.includes("CRITICAL")) return "text-red-400";
    if (line.includes("WARNING")) return "text-amber-400";
    if (line.includes("SUCCESS")) return "text-green-400";
    return "text-zinc-300";
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Live-Logs</h1>
        <button className="btn-ghost text-xs" onClick={() => setLines([])}>
          Leeren
        </button>
      </div>
      <div className="card bg-zinc-950 font-mono text-xs h-[calc(100vh-9rem)] overflow-y-auto p-4 space-y-0.5">
        {lines.length === 0 ? (
          <span className="text-zinc-600">Warte auf Log-Einträge…</span>
        ) : (
          lines.map((line, i) => (
            <div key={i} className={levelColor(line)}>
              {line}
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
