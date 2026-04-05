import { NavLink } from "react-router-dom";
import { LayoutDashboard, Bell, Settings, ScrollText } from "lucide-react";
import { clsx } from "clsx";
import type { ReactNode } from "react";

const nav = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/alerts", label: "Alerts", icon: Bell },
  { to: "/config", label: "Konfiguration", icon: Settings },
  { to: "/logs", label: "Logs", icon: ScrollText },
];

export default function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="w-56 flex-shrink-0 bg-zinc-900 border-r border-zinc-800 flex flex-col">
        <div className="px-5 py-5 border-b border-zinc-800">
          <span className="text-brand font-bold text-lg tracking-tight">WSB-Crawler</span>
          <span className="ml-2 text-zinc-500 text-xs">v2</span>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors",
                  isActive
                    ? "bg-brand/10 text-brand font-medium"
                    : "text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
