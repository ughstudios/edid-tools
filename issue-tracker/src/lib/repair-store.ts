import { prisma } from "@/lib/prisma";
import { SEEDED_REPAIRS, type RepairRow, type RepairStatus, normalizeStatus } from "@/lib/repairs";

type DbRepairRow = {
  id: string;
  quantity: number;
  model: string;
  repair_type: string;
  company: string;
  rma_number: string;
  rma_form_url: string;
  assigned_to: string;
  repaired_by: string;
  status: string;
  notes: string;
  created_at: Date;
  updated_at: Date;
};

const seedKey = "processor-repair-seed-2026-04-29";

function toRepairRow(row: DbRepairRow): RepairRow {
  return {
    id: row.id,
    quantity: row.quantity,
    model: row.model,
    repairType: row.repair_type,
    company: row.company,
    rmaNumber: row.rma_number,
    rmaFormUrl: row.rma_form_url,
    assignedTo: row.assigned_to,
    repairedBy: row.repaired_by,
    status: normalizeStatus(row.status),
    notes: row.notes,
    createdAt: row.created_at.toISOString(),
    updatedAt: row.updated_at.toISOString(),
  };
}

export async function ensureRepairTables() {
  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS processor_repairs (
      id TEXT PRIMARY KEY,
      quantity INTEGER NOT NULL DEFAULT 1,
      model TEXT NOT NULL DEFAULT '',
      repair_type TEXT NOT NULL DEFAULT '',
      company TEXT NOT NULL DEFAULT '',
      rma_number TEXT NOT NULL DEFAULT '',
      rma_form_url TEXT NOT NULL DEFAULT '',
      assigned_to TEXT NOT NULL DEFAULT '',
      repaired_by TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'OPEN',
      notes TEXT NOT NULL DEFAULT '',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);

  await prisma.$executeRawUnsafe(`
    CREATE TABLE IF NOT EXISTS app_seed_markers (
      seed_key TEXT PRIMARY KEY,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
  `);
}

export async function seedRepairsOnce() {
  await ensureRepairTables();
  const markers = await prisma.$queryRawUnsafe<Array<{ seed_key: string }>>(
    `SELECT seed_key FROM app_seed_markers WHERE seed_key = $1 LIMIT 1`,
    seedKey,
  );
  if (markers.length > 0) return;

  for (const row of SEEDED_REPAIRS) {
    await prisma.$executeRawUnsafe(
      `
      INSERT INTO processor_repairs (
        id, quantity, model, repair_type, company, rma_number, rma_form_url,
        assigned_to, repaired_by, status, notes, created_at, updated_at
      )
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
      ON CONFLICT (id) DO NOTHING
      `,
      row.id,
      row.quantity,
      row.model,
      row.repairType,
      row.company,
      row.rmaNumber,
      row.rmaFormUrl,
      row.assignedTo,
      row.repairedBy,
      row.status,
      row.notes,
      row.createdAt,
      row.updatedAt,
    );
  }

  await prisma.$executeRawUnsafe(
    `INSERT INTO app_seed_markers (seed_key) VALUES ($1) ON CONFLICT (seed_key) DO NOTHING`,
    seedKey,
  );
}

export async function listRepairs(): Promise<RepairRow[]> {
  await seedRepairsOnce();
  const rows = await prisma.$queryRawUnsafe<DbRepairRow[]>(`
    SELECT *
    FROM processor_repairs
    ORDER BY created_at ASC, id ASC
  `);
  return rows.map(toRepairRow);
}

export async function createRepair(row: RepairRow): Promise<RepairRow> {
  await ensureRepairTables();
  const inserted = await prisma.$queryRawUnsafe<DbRepairRow[]>(
    `
    INSERT INTO processor_repairs (
      id, quantity, model, repair_type, company, rma_number, rma_form_url,
      assigned_to, repaired_by, status, notes
    )
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    RETURNING *
    `,
    row.id,
    row.quantity,
    row.model,
    row.repairType,
    row.company,
    row.rmaNumber,
    row.rmaFormUrl,
    row.assignedTo,
    row.repairedBy,
    row.status,
    row.notes,
  );
  return toRepairRow(inserted[0]);
}

export async function updateRepair(id: string, patch: Partial<RepairRow>): Promise<RepairRow | null> {
  await ensureRepairTables();
  const current = await prisma.$queryRawUnsafe<DbRepairRow[]>(`SELECT * FROM processor_repairs WHERE id = $1 LIMIT 1`, id);
  if (current.length === 0) return null;
  const row = toRepairRow(current[0]);
  const next = { ...row, ...patch, status: patch.status ? normalizeStatus(patch.status) : row.status };

  const updated = await prisma.$queryRawUnsafe<DbRepairRow[]>(
    `
    UPDATE processor_repairs
    SET quantity = $2,
        model = $3,
        repair_type = $4,
        company = $5,
        rma_number = $6,
        rma_form_url = $7,
        assigned_to = $8,
        repaired_by = $9,
        status = $10,
        notes = $11,
        updated_at = NOW()
    WHERE id = $1
    RETURNING *
    `,
    id,
    Math.max(0, Math.trunc(next.quantity || 0)),
    next.model,
    next.repairType,
    next.company,
    next.rmaNumber,
    next.rmaFormUrl,
    next.assignedTo,
    next.repairedBy,
    next.status,
    next.notes,
  );
  return toRepairRow(updated[0]);
}

export async function deleteRepair(id: string) {
  await ensureRepairTables();
  await prisma.$executeRawUnsafe(`DELETE FROM processor_repairs WHERE id = $1`, id);
}

export function isRepairStatus(value: unknown): value is RepairStatus {
  return value === "OPEN" || value === "IN_PROGRESS" || value === "DONE";
}
