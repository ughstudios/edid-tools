"use server";

import { signIn } from "@/auth";
import { getServerTranslator } from "@/i18n/server";
import { prisma } from "@/lib/prisma";
import { CredentialsSignin } from "next-auth";

type LoginState = { error?: string; ok?: boolean };

export async function loginAction(_prevState: LoginState, formData: FormData) {
  const t = await getServerTranslator();
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const normalizedEmail = email.trim().toLowerCase();

  const user = await prisma.user.findUnique({
    where: { email: normalizedEmail },
    select: { approvalStatus: true },
  });

  if (user && user.approvalStatus !== "APPROVED") {
    return { error: t("errors.login.pendingApproval") };
  }

  try {
    const result = await signIn("credentials", {
      email: normalizedEmail,
      password,
      redirect: false,
      redirectTo: "/",
    });

    const next = typeof result === "string" ? result : "";
    if (!next || next.includes("error=")) {
      return { error: t("errors.login.invalidCredentials") };
    }

    return { ok: true };
  } catch (error) {
    // Server-side signIn with redirect:false uses raw mode; failed credentials throw
    // instead of returning a URL — uncaught, that surfaces as a generic platform error page.
    if (error instanceof CredentialsSignin) {
      return { error: t("errors.login.invalidCredentials") };
    }
    throw error;
  }
}
