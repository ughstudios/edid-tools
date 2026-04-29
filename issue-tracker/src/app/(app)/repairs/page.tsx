import { RepairsWorkspace } from "@/components/repairs-workspace";

export default function RepairsPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">Repairs</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Processor repair tracking with spreadsheet-style editing, company/RMA links, assignment, and repair ownership.
        </p>
      </header>
      <section className="panel-surface rounded-xl p-4">
        <RepairsWorkspace mode="table" />
      </section>
    </div>
  );
}
