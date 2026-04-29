import type { MessageTree } from "./types";

export type TranslateFn = (path: string, vars?: Record<string, string>) => string;

export function createTranslator(messages: MessageTree): TranslateFn {
  return function t(path: string, vars?: Record<string, string>): string {
    const parts = path.split(".");
    let cur: unknown = messages;
    for (const p of parts) {
      if (cur && typeof cur === "object" && p in cur) {
        cur = (cur as MessageTree)[p];
      } else {
        return path;
      }
    }
    let s = typeof cur === "string" ? cur : path;
    if (vars) {
      for (const [k, v] of Object.entries(vars)) {
        s = s.replaceAll(`{${k}}`, v);
      }
    }
    return s;
  };
}
