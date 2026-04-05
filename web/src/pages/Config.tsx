import { useEffect, useState } from "react";
import { Save, CheckCircle } from "lucide-react";

interface Field {
  key: string;
  label: string;
  type?: string;
  placeholder?: string;
  help?: string;
}

const SECTIONS: { title: string; fields: Field[] }[] = [
  {
    title: "Reddit API",
    fields: [
      { key: "reddit_client_id", label: "Client ID", placeholder: "abc123" },
      { key: "reddit_client_secret", label: "Client Secret", type: "password", placeholder: "••••••••" },
      { key: "reddit_user_agent", label: "User Agent", placeholder: "python:wsb-crawler:v2 (by /u/deinuser)" },
    ],
  },
  {
    title: "Discord",
    fields: [
      {
        key: "discord_webhook_url",
        label: "Webhook URL",
        placeholder: "https://discord.com/api/webhooks/...",
        help: "Discord → Servereinstellungen → Integrationen → Webhooks",
      },
      { key: "discord_bot_token", label: "Bot Token (optional)", type: "password", placeholder: "Nur für /top, /chart Slash-Commands" },
    ],
  },
  {
    title: "NewsAPI",
    fields: [
      { key: "newsapi_key", label: "API Key", type: "password", placeholder: "Kostenlos auf newsapi.org", help: "Optional — ohne Key keine News-Headlines in Alerts" },
      { key: "newsapi_window_hours", label: "News-Fenster (Stunden)", placeholder: "48" },
    ],
  },
  {
    title: "Subreddits & Crawler",
    fields: [
      { key: "subreddits", label: "Subreddits", placeholder: "wallstreetbets,wallstreetbetsGER", help: "Komma-separiert" },
      { key: "crawl_interval_minutes", label: "Intervall (Minuten)", placeholder: "30" },
      { key: "posts_limit", label: "Posts pro Subreddit", placeholder: "500" },
      { key: "comments_limit", label: "Kommentare pro Post", placeholder: "100" },
    ],
  },
  {
    title: "Alert-Schwellwerte",
    fields: [
      { key: "alert_min_abs", label: "Min. Nennungen (neuer Ticker)", placeholder: "20" },
      { key: "alert_min_delta", label: "Min. Anstieg absolut", placeholder: "10" },
      { key: "alert_ratio", label: "Min. Faktor (z.B. 2.0 = 200%)", placeholder: "2.0" },
      { key: "alert_min_price_move", label: "Min. Kursänderung %", placeholder: "5.0" },
      { key: "alert_max_per_run", label: "Max. Alerts pro Lauf", placeholder: "3" },
      { key: "alert_cooldown_h", label: "Cooldown (Stunden)", placeholder: "4" },
    ],
  },
];

export default function Config() {
  const [values, setValues] = useState<Record<string, string>>({});
  const [setSecrets, setSetSecrets] = useState<Set<string>>(new Set());
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/config")
      .then((r) => r.json())
      .then((data: Record<string, string>) => {
        // Passwort-Felder: ••••••••-Platzhalter aus API NICHT in State laden
        // → Felder bleiben leer; User tippt nur wenn er ändern will
        const secretKeys = new Set(
          SECTIONS.flatMap((s) => s.fields.filter((f) => f.type === "password").map((f) => f.key))
        );
        const cleaned: Record<string, string> = {};
        const alreadySet = new Set<string>();
        for (const [k, v] of Object.entries(data)) {
          if (secretKeys.has(k)) {
            cleaned[k] = "";
            if (v && v !== "") alreadySet.add(k);
          } else {
            cleaned[k] = v ?? "";
          }
        }
        setValues(cleaned);
        setSetSecrets(alreadySet);
      });
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      // Leere Felder nicht senden (unveränderte Secrets bleiben wie sie sind)
      const payload = Object.fromEntries(
        Object.entries(values).filter(([, v]) => v !== "")
      );
      await fetch("/api/config", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Konfiguration</h1>
        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saved ? <CheckCircle size={15} /> : <Save size={15} />}
          {saved ? "Gespeichert" : "Speichern"}
        </button>
      </div>

      {SECTIONS.map(({ title, fields }) => (
        <div key={title} className="card space-y-4">
          <h2 className="font-semibold text-sm text-zinc-300 border-b border-zinc-800 pb-3">{title}</h2>
          {fields.map(({ key, label, type, placeholder, help }) => (
            <div key={key}>
              <label className="label">{label}</label>
              <input
                className="input"
                type={type ?? "text"}
                placeholder={
                  type === "password" && setSecrets.has(key)
                    ? "● gesetzt — leer lassen zum Beibehalten"
                    : placeholder
                }
                value={values[key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              />
              {help && <p className="text-xs text-zinc-600 mt-1">{help}</p>}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
