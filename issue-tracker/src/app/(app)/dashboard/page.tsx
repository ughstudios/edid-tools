import { RepairsWorkspace } from "@/components/repairs-workspace";

export default function DashboardPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-950 dark:text-zinc-50">Dashboard</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          Overview of active issues and processor repairs by company and employee.
        </p>
      </header>
      <RepairsWorkspace mode="dashboard" />
    </div>
  );
}
