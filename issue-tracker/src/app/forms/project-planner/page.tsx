import Link from "next/link";
import { GuestLanguageBar } from "@/components/guest-chrome";
import { ProjectPlannerTools } from "@/components/project-planner-tools";
import { PublicAccessTabs } from "@/components/public-access-tabs";
import { getServerTranslator } from "@/i18n/server";

export default async function ProjectPlannerFormPage() {
  const t = await getServerTranslator();

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 py-4">
      <GuestLanguageBar />
      <PublicAccessTabs />
      <div className="panel-surface rounded-xl p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold">{t("publicForms.pages.projectPlanner.title")}</h1>
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {t("publicForms.pages.projectPlanner.subtitle")}
            </p>
          </div>
          <Link
            href="/forms"
            className="text-sm font-medium text-zinc-700 underline hover:text-zinc-900 dark:text-zinc-300 dark:hover:text-zinc-100"
          >
            {t("publicForms.pages.projectPlanner.back")}
          </Link>
        </div>
        <ProjectPlannerTools />
      </div>
    </main>
  );
}
