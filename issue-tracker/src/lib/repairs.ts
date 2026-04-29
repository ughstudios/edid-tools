export type RepairStatus = "OPEN" | "IN_PROGRESS" | "DONE";

export type RepairRow = {
  id: string;
  quantity: number;
  model: string;
  repairType: string;
  company: string;
  rmaNumber: string;
  rmaFormUrl: string;
  assignedTo: string;
  repairedBy: string;
  status: RepairStatus;
  notes: string;
  createdAt: string;
  updatedAt: string;
};

export const REPAIR_STORAGE_KEY = "issue-tracker.repairs.v1";
export const REPAIR_SEED_KEY = "issue-tracker.repairs.seeded.processor-list.v1";

const seedDate = "2026-04-29T00:00:00.000Z";

export const SEEDED_REPAIRS: RepairRow[] = [
  seedRepair("2 loose Z4pro", 2, "Z4pro", "Loose processor"),
  seedRepair("1 loose z5", 1, "z5", "Loose processor"),
  seedRepair("2 loose z4(old)", 2, "z4(old)", "Loose processor"),
  seedRepair("1 loose x16", 1, "x16", "Loose processor"),
  seedRepair("2 loose z6", 2, "z6", "Loose processor"),
  seedRepair("1 loose H10fn", 1, "H10fn", "Loose processor"),
  seedRepair("1 loose c7", 1, "c7", "Loose processor"),
  seedRepair("1 loose Z4pro", 1, "Z4pro", "Loose processor"),
  seedRepair("1 x2m", 1, "x2m", "Processor repair"),
  seedRepair("1 h10fn", 1, "h10fn", "Processor repair"),
  seedRepair("2 x4e", 2, "x4e", "Processor repair"),
  seedRepair("1 x16", 1, "x16", "Processor repair"),
  seedRepair("1 z6", 1, "z6", "Processor repair"),
  seedRepair("7 Z4pros", 7, "Z4pros", "Processor repair"),
  seedRepair("1 C3 pro", 1, "C3 pro", "Processor repair"),
  seedRepair("3 h10 fix", 3, "h10", "Fix"),
  seedRepair("Z8", 1, "Z8", "Processor repair"),
];

function seedRepair(id: string, quantity: number, model: string, repairType: string): RepairRow {
  return {
    id: `seed-${id.toLowerCase().replaceAll(/[^a-z0-9]+/g, "-").replaceAll(/^-|-$/g, "")}`,
    quantity,
    model,
    repairType,
    company: "",
    rmaNumber: "",
    rmaFormUrl: "",
    assignedTo: "",
    repairedBy: "",
    status: "OPEN",
    notes: "",
    createdAt: seedDate,
    updatedAt: seedDate,
  };
}

export function makeBlankRepair(): RepairRow {
  const now = new Date().toISOString();
  const id =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `repair-${Date.now()}-${Math.random().toString(16).slice(2)}`;

  return {
    id,
    quantity: 1,
    model: "",
    repairType: "Processor repair",
    company: "",
    rmaNumber: "",
    rmaFormUrl: "",
    assignedTo: "",
    repairedBy: "",
    status: "OPEN",
    notes: "",
    createdAt: now,
    updatedAt: now,
  };
}

export function normalizeStatus(value: string): RepairStatus {
  if (value === "DONE" || value === "IN_PROGRESS") return value;
  return "OPEN";
}

export function mergeSeedOnce(existing: RepairRow[], seedWasApplied: boolean): RepairRow[] {
  if (seedWasApplied) return existing;
  const existingIds = new Set(existing.map((row) => row.id));
  return [...existing, ...SEEDED_REPAIRS.filter((row) => !existingIds.has(row.id))];
}

export function repairUnitTotal(rows: RepairRow[]): number {
  return rows.reduce((sum, row) => sum + Math.max(0, Math.trunc(row.quantity || 0)), 0);
}

export function groupRepairUnits(rows: RepairRow[], key: keyof Pick<RepairRow, "company" | "assignedTo" | "repairedBy" | "status">) {
  const grouped = new Map<string, number>();
  for (const row of rows) {
    const label = String(row[key] || "Unassigned");
    grouped.set(label, (grouped.get(label) ?? 0) + Math.max(0, Math.trunc(row.quantity || 0)));
  }
  return [...grouped.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
}
