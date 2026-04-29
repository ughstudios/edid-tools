export default function IssuesPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">Issues</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Issue tracking stays separate from processor repair tracking.
        </p>
      </header>
      <section className="panel-surface rounded-xl p-4">
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Use the Repairs tab for processor RMA and repair work. The repairs workflow mirrors an issue list with status,
          assignment, company context, and editable notes.
        </p>
      </section>
    </div>
  );
}
