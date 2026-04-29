"use client";

import { useI18n } from "@/i18n/context";
import type { Locale } from "@/i18n/types";

function GlobeIcon({ className }: { className?: string }) {
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
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  );
}

function EnGlyph({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden>
      <text
        x="12"
        y="16.5"
        textAnchor="middle"
        className="fill-current font-semibold"
        style={{ fontSize: "13px", fontFamily: "system-ui, sans-serif" }}
      >
        A
      </text>
    </svg>
  );
}

function ZhGlyph({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" aria-hidden>
      <text
        x="12"
        y="16.5"
        textAnchor="middle"
        className="fill-current font-semibold"
        style={{
          fontSize: "12px",
          fontFamily: '"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif',
        }}
      >
        中
      </text>
    </svg>
  );
}

export function LanguageToggle({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useI18n();

  const btn = (code: Locale, Glyph: typeof EnGlyph, label: string) => (
    <button
      key={code}
      type="button"
      onClick={() => void setLocale(code)}
      title={label}
      aria-label={label}
      aria-pressed={locale === code}
      className={[
        "inline-flex h-9 w-9 items-center justify-center rounded-lg transition-colors",
        locale === code
          ? "bg-zinc-900 text-white dark:bg-zinc-100 dark:text-zinc-900"
          : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700",
      ].join(" ")}
    >
      <Glyph className="h-5 w-5" />
    </button>
  );

  return (
    <div
      role="group"
      aria-label={t("language.label")}
      className={`flex flex-wrap items-center gap-2 ${className}`}
    >
      <GlobeIcon className="h-4 w-4 shrink-0 text-zinc-500 dark:text-zinc-400" aria-hidden />
      <div className="flex gap-1">
        {btn("en", EnGlyph, t("language.en"))}
        {btn("zh", ZhGlyph, t("language.zh"))}
      </div>
    </div>
  );
}
