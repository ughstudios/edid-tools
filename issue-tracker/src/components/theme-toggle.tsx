"use client";

import { useI18n } from "@/i18n/context";
import { useTheme } from "next-themes";
import { useSyncExternalStore } from "react";

function SunIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z" />
    </svg>
  );
}

function MonitorIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <rect width="20" height="14" x="2" y="3" rx="2" />
      <line x1="8" x2="16" y1="21" y2="21" />
      <line x1="12" x2="12" y1="17" y2="21" />
    </svg>
  );
}

const clientSnapshot = () => true;
const serverSnapshot = () => false;
const emptySubscribe = () => () => {};

export function ThemeToggle({ className = "" }: { className?: string }) {
  const { t } = useI18n();
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(emptySubscribe, clientSnapshot, serverSnapshot);

  const btn = (value: "light" | "dark" | "system", Icon: typeof SunIcon, label: string) => (
    <button
      key={value}
      type="button"
      onClick={() => setTheme(value)}
      title={label}
      aria-label={label}
      aria-pressed={mounted ? theme === value : undefined}
      className={[
        "inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors",
        mounted && theme === value
          ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
          : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700",
      ].join(" ")}
    >
      <Icon className="h-5 w-5" />
    </button>
  );

  return (
    <div
      role="group"
      aria-label={t("theme.label")}
      className={`flex flex-wrap items-center gap-2 ${className}`}
    >
      <MonitorIcon className="h-4 w-4 shrink-0 text-zinc-500 dark:text-zinc-400" aria-hidden />
      <div className="flex gap-1">
        {btn("light", SunIcon, t("theme.light"))}
        {btn("dark", MoonIcon, t("theme.dark"))}
        {btn("system", MonitorIcon, t("theme.system"))}
      </div>
    </div>
  );
}
