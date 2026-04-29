/**
 * Safe for `"use client"` — no Prisma or Node-only imports.
 */

/** Main nav areas whose visibility can be restricted for the EMPLOYEE role. */
export const EMPLOYEE_NAV_TAB_IDS = [
  "dashboard",
  "kanban",
  "issues",
  "projects",
  "work-records",
  "reports",
  "customers",
  "inventory",
  "logs",
  "tools",
  "archive",
] as const;

export type EmployeeNavTabId = (typeof EMPLOYEE_NAV_TAB_IDS)[number];

export const TABS_ISSUE_DATA: readonly EmployeeNavTabId[] = [
  "issues",
  "kanban",
  "dashboard",
  "archive",
];

export const TABS_PROJECT_DETAIL: readonly EmployeeNavTabId[] = [
  "projects",
  "issues",
  "kanban",
  "dashboard",
  "archive",
];

export const TABS_CUSTOMER_DETAIL: readonly EmployeeNavTabId[] = [
  "customers",
  "projects",
  "issues",
  "kanban",
  "dashboard",
  "archive",
];

/** User list API: assignees, reports, etc. */
export const TABS_USERS_LIST: readonly EmployeeNavTabId[] = [
  "issues",
  "kanban",
  "dashboard",
  "archive",
  "work-records",
  "reports",
  "projects",
  "customers",
];

export const TABS_DASHBOARD_ONLY: readonly EmployeeNavTabId[] = ["dashboard"];

export const TABS_WORK_RECORDS_PAGE: readonly EmployeeNavTabId[] = ["work-records"];

export const TABS_REPORTS: readonly EmployeeNavTabId[] = ["reports"];

export const TABS_PRODUCTS_CATALOG: readonly EmployeeNavTabId[] = ["inventory", "projects"];

export const TABS_LOGS: readonly EmployeeNavTabId[] = ["logs"];

export const TABS_INVENTORY: readonly EmployeeNavTabId[] = ["inventory"];

/** Public calibration / processor RMA queue (Pending Requests). */
export const TABS_PENDING_CUSTOMER_REQUESTS: readonly EmployeeNavTabId[] = [
  "issues",
  "reports",
  "customers",
  "dashboard",
  "kanban",
  "archive",
];

function isRecord(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/** Raw JSON from DB → only known keys, values coerced to boolean. */
export function parseEmployeeNavAccessJson(
  raw: unknown,
): Partial<Record<EmployeeNavTabId, boolean>> {
  if (!isRecord(raw)) return {};
  const out: Partial<Record<EmployeeNavTabId, boolean>> = {};
  for (const id of EMPLOYEE_NAV_TAB_IDS) {
    if (id in raw) out[id] = Boolean(raw[id]);
  }
  return out;
}

/** Merged map: missing or partial DB → all tabs allowed unless explicitly false. */
export function mergeEmployeeNavAccess(
  partial: Partial<Record<EmployeeNavTabId, boolean>>,
): Record<EmployeeNavTabId, boolean> {
  const out = {} as Record<EmployeeNavTabId, boolean>;
  for (const id of EMPLOYEE_NAV_TAB_IDS) {
    out[id] = partial[id] !== false;
  }
  return out;
}

export function employeeNavAllows(
  map: Record<EmployeeNavTabId, boolean>,
  tab: EmployeeNavTabId,
): boolean {
  return map[tab] !== false;
}

export function employeeNavAllowsAny(
  map: Record<EmployeeNavTabId, boolean>,
  tabs: readonly EmployeeNavTabId[],
): boolean {
  return tabs.some((t) => employeeNavAllows(map, t));
}
