import { requireEmployeeNavTab } from "@/lib/employee-nav";

export default async function ToolsLayout({ children }: { children: React.ReactNode }) {
  await requireEmployeeNavTab("tools");
  return children;
}
