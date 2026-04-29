/** Regular admin: archive, approvals, etc. */
export const ROLE_ADMIN = "ADMIN";
/** Full admin + can change others’ roles (except demoting peer super admins). */
export const ROLE_SUPER_ADMIN = "SUPER_ADMIN";
export const ROLE_EMPLOYEE = "EMPLOYEE";

export const ASSIGNABLE_ROLES = [ROLE_EMPLOYEE, ROLE_ADMIN, ROLE_SUPER_ADMIN] as const;
export type AssignableRole = (typeof ASSIGNABLE_ROLES)[number];

export function isPrivilegedAdmin(role: string | null | undefined): boolean {
  return role === ROLE_ADMIN || role === ROLE_SUPER_ADMIN;
}

export function isSuperAdmin(role: string | null | undefined): boolean {
  return role === ROLE_SUPER_ADMIN;
}

export function parseAssignableRole(v: string): AssignableRole | null {
  if (v === ROLE_EMPLOYEE || v === ROLE_ADMIN || v === ROLE_SUPER_ADMIN) return v;
  return null;
}
