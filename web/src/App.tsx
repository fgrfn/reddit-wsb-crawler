import { Routes, Route, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import Layout from "@/components/Layout";
import Dashboard from "@/pages/Dashboard";
import Alerts from "@/pages/Alerts";
import Config from "@/pages/Config";
import Logs from "@/pages/Logs";
import Setup from "@/pages/Setup";

export default function App() {
  const [configured, setConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    fetch("/api/config/status")
      .then((r) => r.json())
      .then((d) => setConfigured(d.configured))
      .catch(() => setConfigured(false));
  }, []);

  if (configured === null) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-zinc-500 text-sm">Lädt...</div>
      </div>
    );
  }

  if (!configured) {
    return (
      <Routes>
        <Route path="/setup" element={<Setup onDone={() => setConfigured(true)} />} />
        <Route path="*" element={<Navigate to="/setup" replace />} />
      </Routes>
    );
  }

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/config" element={<Config />} />
        <Route path="/logs" element={<Logs />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
