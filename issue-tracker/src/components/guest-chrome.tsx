"use client";

import { LanguageToggle } from "@/components/language-toggle";
import { ThemeToggle } from "@/components/theme-toggle";

export function GuestLanguageBar() {
  return (
    <div className="mb-4 flex w-full flex-wrap items-center justify-end gap-4">
      <ThemeToggle />
      <LanguageToggle />
    </div>
  );
}
