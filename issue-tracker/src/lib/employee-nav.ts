import { auth } from "@/auth";
import {
  employeeNavAllows,
  employeeNavAllowsAny,
  mergeEmployeeNavAccess,
  parseEmployeeNavAccessJson,
  type EmployeeNavTabId,
} from "@/lib/employee-nav-shared";
import { prisma } from "@/lib/prisma";
import { isPrivilegedAdmin } from "@/lib/roles";
import { redirect } from "next/navigation";

const SETTINGS_ID = "default";

export type EmployeeNavAccessRowResult =
  | { ok: true; id: string; employeeNavAccess: unknown }
  | { ok: false; id: string; employeeNavAccess: unknown };

/**
 * Loads or creates the singleton AppSettings row. If the table is missing (migration not applied),
 * returns ok: false and empty JSON so the admin UI can still render.
 */
export async function getEmployeeNavAccessRow(): Promise<EmployeeNavAccessRowResult> {
  try {
    let row = await prisma.appSettings.findUnique({ where: { id: SETTINGS_ID } });
    if (!row) {
      row = await prisma.appSettings.create({
        data: { id: SETTINGS_ID, employeeNavAccess: {} },
      });
    }
    return { ok: true, id: row.id, employeeNavAccess: row.employeeNavAccess };
  } catch (err) {
    console.error(
      "[employee-nav] AppSettings table missing or unreadable. Run: npx prisma migrate deploy",
      err,
    );
    return { ok: false, id: SETTINGS_ID, employeeNavAccess: {} };
  }
}

export async function getEmployeeNavAccessMap(): Promise<Record<EmployeeNavTabId, boolean>> {
  const row = await getEmployeeNavAccessRow();
  const partial = parseEmployeeNavAccessJson(row.employeeNavAccess);
  return mergeEmployeeNavAccess(partial);
}

export async function getNavAccessForSessionUser(
  role: string | null | undefined,
): Promise<Record<EmployeeNavTabId, boolean>> {
  if (isPrivilegedAdmin(role)) {
    return mergeEmployeeNavAccess({});
  }
  return getEmployeeNavAccessMap();
}

export async function requireEmployeeNavTab(tab: EmployeeNavTabId) {
  const session = await auth();
  if (!session?.user) redirect("/login");
  if (isPrivilegedAdmin(session.user.role)) return;
  const map = await getEmployeeNavAccessMap();
  if (!employeeNavAllows(map, tab)) redirect("/account");
}

export async function requireEmployeeNavAnyOf(tabs: readonly EmployeeNavTabId[]) {
  const session = await auth();
  if (!session?.user) redirect("/login");
  if (isPrivilegedAdmin(session.user.role)) return;
  const map = await getEmployeeNavAccessMap();
  if (!employeeNavAllowsAny(map, tabs)) redirect("/account");
}
