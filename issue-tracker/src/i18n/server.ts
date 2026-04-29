import { cookies, headers } from "next/headers";
import { createTranslator } from "./create-translator";
import { getDictionary, isLocale } from "./dictionaries";
import type { Locale } from "./types";
import { LOCALE_COOKIE } from "./types";

export async function getLocale(): Promise<Locale> {
  const jar = await cookies();
  const raw = jar.get(LOCALE_COOKIE)?.value;
  if (isLocale(raw)) return raw;

  const headerList = await headers();
  const acceptLanguage = headerList.get("accept-language")?.toLowerCase() ?? "";
  return acceptLanguage.includes("zh") ? "zh" : "en";
}

export async function getServerTranslator() {
  const locale = await getLocale();
  return createTranslator(getDictionary(locale));
}
