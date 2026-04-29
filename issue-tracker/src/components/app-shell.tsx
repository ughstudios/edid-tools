"use client";

import type { EmployeeNavTabId } from "@/lib/employee-nav-shared";
import Link from "next/link";
import { ReactNode } from "react";

type AppShellProps = {
  user: {
    id: string;
    name: string;
    email: string;
    role: string;
  };
  onboardingCompleted: boolean;
  navAccess: Record<EmployeeNavTabId, boolean>;
  onLogout: ReactNode;
  children: ReactNode;
};

const navItems: Array<{ id: EmployeeNavTabId | "repairs"; href: string; label: string }> = [
  { id: "dashboard", href: "/dashboard", label: "Dashboard" },
  { id: "issues", href: "/issues", label: "Issues" },
  { id: "repairs", href: "/repairs", label: "Repairs" },
  { id: "projects", href: "/projects", label: "Projects" },
  { id: "customers", href: "/customers", label: "Customers" },
  { id: "tools", href: "/tools", label: "Tools" },
];

export function AppShell({ user, navAccess, onLogout, children }: AppShellProps) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">Project Tracker</div>
        <nav className="nav" aria-label="Main pages">
          {navItems
            .filter((item) => item.id === "repairs" || navAccess[item.id] !== false)
            .map((item) => (
              <Link href={item.href} key={item.href}>
                {item.label}
              </Link>
            ))}
        </nav>
        <div style={{ marginTop: 24 }}>
          <p style={{ margin: "0 0 4px", fontWeight: 700 }}>{user.name}</p>
          <p style={{ color: "#cbd5e1", fontSize: 13, margin: "0 0 12px" }}>{user.email}</p>
          {onLogout}
        </div>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
