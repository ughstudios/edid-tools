export type Locale = "en" | "zh";

export const LOCALE_COOKIE = "app-locale";

/** Nested string maps for translations (JSON-serializable shape). */
export type MessageTree = { readonly [key: string]: string | MessageTree };
