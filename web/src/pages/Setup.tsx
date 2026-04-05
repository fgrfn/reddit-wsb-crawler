import { useState } from "react";
import { ChevronRight, ChevronLeft, CheckCircle } from "lucide-react";

interface Props {
  onDone: () => void;
}

interface Step {
  title: string;
  description: string;
  fields: { key: string; label: string; type?: string; placeholder: string; help?: string; required?: boolean }[];
}

const STEPS: Step[] = [
  {
    title: "Reddit API",
    description: "Erstelle eine App unter reddit.com/prefs/apps → 'script'.",
    fields: [
      { key: "reddit_client_id", label: "Client ID", placeholder: "abc123xyz", required: true },
      { key: "reddit_client_secret", label: "Client Secret", type: "password", placeholder: "••••••••", required: true },
      { key: "reddit_user_agent", label: "User Agent", placeholder: "python:wsb-crawler:v2 (by /u/deinuser)" },
    ],
  },
  {
    title: "Discord Webhook",
    description: "Discord → Servereinstellungen → Integrationen → Webhooks → Neuer Webhook.",
    fields: [
      {
        key: "discord_webhook_url",
        label: "Webhook URL",
        placeholder: "https://discord.com/api/webhooks/...",
        required: true,
      },
    ],
  },
  {
    title: "Subreddits",
    description: "Welche Subreddits sollen gecrawlt werden?",
    fields: [
      {
        key: "subreddits",
        label: "Subreddits (komma-separiert)",
        placeholder: "wallstreetbets,wallstreetbetsGER",
        help: "Standard: wallstreetbets und wallstreetbetsGER",
      },
      {
        key: "crawl_interval_minutes",
        label: "Crawl-Intervall (Minuten)",
        placeholder: "30",
        help: "Empfehlung: 30 Minuten",
      },
    ],
  },
];

export default function Setup({ onDone }: Props) {
  const [step, setStep] = useState(0);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const current = STEPS[step];
  const isLast = step === STEPS.length - 1;

  const handleNext = async () => {
    if (isLast) {
      setSaving(true);
      setError("");
      try {
        const res = await fetch("/api/config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(values),
        });
        if (!res.ok) throw new Error(await res.text());
        onDone();
      } catch (e) {
        setError(String(e));
      } finally {
        setSaving(false);
      }
    } else {
      setStep((s) => s + 1);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md space-y-6">
        {/* Header */}
        <div className="text-center">
          <div className="text-brand font-bold text-2xl mb-1">WSB-Crawler</div>
          <div className="text-zinc-500 text-sm">Ersteinrichtung</div>
        </div>

        {/* Progress */}
        <div className="flex gap-2">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={`h-1 flex-1 rounded-full transition-colors ${
                i <= step ? "bg-brand" : "bg-zinc-800"
              }`}
            />
          ))}
        </div>

        {/* Card */}
        <div className="card space-y-5">
          <div>
            <h2 className="font-bold text-lg">{current.title}</h2>
            <p className="text-zinc-500 text-sm mt-1">{current.description}</p>
          </div>

          {current.fields.map(({ key, label, type, placeholder, help, required }) => (
            <div key={key}>
              <label className="label">
                {label}
                {required && <span className="text-brand ml-1">*</span>}
              </label>
              <input
                className="input"
                type={type ?? "text"}
                placeholder={placeholder}
                value={values[key] ?? ""}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
              />
              {help && <p className="text-xs text-zinc-600 mt-1">{help}</p>}
            </div>
          ))}

          {error && <p className="text-red-400 text-sm bg-red-400/10 px-3 py-2 rounded-lg">{error}</p>}

          <div className="flex justify-between pt-2">
            <button
              className="btn-ghost"
              onClick={() => setStep((s) => s - 1)}
              disabled={step === 0}
            >
              <ChevronLeft size={16} />
              Zurück
            </button>
            <button className="btn-primary" onClick={handleNext} disabled={saving}>
              {isLast ? (
                <>
                  <CheckCircle size={16} />
                  {saving ? "Speichert…" : "Fertig & Starten"}
                </>
              ) : (
                <>
                  Weiter
                  <ChevronRight size={16} />
                </>
              )}
            </button>
          </div>
        </div>

        <p className="text-center text-zinc-600 text-xs">
          Schritt {step + 1} von {STEPS.length} · Alle Einstellungen später unter Konfiguration änderbar
        </p>
      </div>
    </div>
  );
}
