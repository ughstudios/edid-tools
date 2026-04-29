"use client";

import { useI18n } from "@/i18n/context";
import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/login", labelKey: "publicForms.accessTabs.login" as const },
  { href: "/forms", labelKey: "publicForms.accessTabs.forms" as const },
] as const;

export function PublicAccessTabs() {
  const pathname = usePathname();
  const { t } = useI18n();
  return (
    <nav
      aria-label={t("publicForms.accessTabs.ariaLabel")}
      className="mb-4 grid w-full grid-cols-2 gap-1 rounded-lg bg-zinc-100 p-1 dark:bg-zinc-900"
    >
      {TABS.map((tab) => {
        const active =
          tab.href === "/forms"
            ? pathname === "/forms" || pathname.startsWith("/forms/")
            : pathname === tab.href;
        return (
          <Link
            key={tab.href}
            href={tab.href}
            className={[
              "rounded-md px-3 py-2 text-center text-sm font-medium transition-colors",
              active
                ? "bg-white text-zinc-900 shadow-sm dark:bg-zinc-800 dark:text-zinc-100"
                : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-200",
            ].join(" ")}
          >
            {t(tab.labelKey)}
          </Link>
        );
      })}
    </nav>
  );
}
