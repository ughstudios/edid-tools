import { auth } from "@/auth";
import { AppShell } from "@/components/app-shell";
import { LogoutButton } from "@/components/logout-button";
import { getNavAccessForSessionUser } from "@/lib/employee-nav";
import { prisma } from "@/lib/prisma";
import { redirect } from "next/navigation";

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth();
  if (!session?.user) redirect("/login");

  const navAccess = await getNavAccessForSessionUser(session.user.role);

  const userRow = await prisma.user.findUnique({
    where: { id: session.user.id },
    select: { onboardingCompletedAt: true },
  });
  const onboardingCompleted = userRow?.onboardingCompletedAt != null;

  return (
    <AppShell
      user={{
        id: session.user.id,
        name: session.user.name,
        email: session.user.email,
        role: session.user.role,
      }}
      onboardingCompleted={onboardingCompleted}
      navAccess={navAccess}
      onLogout={<LogoutButton />}
    >
      {children}
    </AppShell>
  );
}

