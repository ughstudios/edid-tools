import { auth } from "@/auth";
import { GuestLanguageBar } from "@/components/guest-chrome";
import { LoginForm } from "@/components/login-form";
import { PublicAccessTabs } from "@/components/public-access-tabs";
import { getServerTranslator } from "@/i18n/server";
import { redirect } from "next/navigation";

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ message?: string | string[] }>;
}) {
  const session = await auth();
  if (session?.user) redirect("/");

  const t = await getServerTranslator();
  const params = await searchParams;
  const raw = params.message;
  const messageKey = Array.isArray(raw) ? raw[0] : raw;
  const bannerMessage =
    messageKey === "email-changed" ? t("login.emailChangedBanner") : undefined;

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-md flex-col px-6 py-4">
      <GuestLanguageBar />
      <PublicAccessTabs />
      <div className="flex flex-1 items-center">
        <div className="panel-surface w-full rounded-xl p-6">
          <h1 className="text-2xl font-semibold">{t("login.title")}</h1>
          <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">{t("login.subtitle")}</p>
          <LoginForm bannerMessage={bannerMessage} />
        </div>
      </div>
    </main>
  );
}
