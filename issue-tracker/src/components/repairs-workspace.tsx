"use client";

import {
  REPAIR_SEED_KEY,
  REPAIR_STORAGE_KEY,
  RepairRow,
  RepairStatus,
  groupRepairUnits,
  makeBlankRepair,
  mergeSeedOnce,
  normalizeStatus,
  repairUnitTotal,
} from "@/lib/repairs";
import { useEffect, useMemo, useState } from "react";

type RepairsWorkspaceProps = {
  mode: "table" | "dashboard";
};

const statusLabels: Record<RepairStatus, string> = {
  OPEN: "Open",
  IN_PROGRESS: "In progress",
  DONE: "Done",
};

function readRepairs(): RepairRow[] {
  if (typeof window === "undefined") return [];
  const raw = window.localStorage.getItem(REPAIR_STORAGE_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as RepairRow[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function useRepairs() {
  const [repairs, setRepairs] = useState<RepairRow[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    const current = readRepairs();
    const seedWasApplied = window.localStorage.getItem(REPAIR_SEED_KEY) === "true";
    const seeded = mergeSeedOnce(current, seedWasApplied);
    window.localStorage.setItem(REPAIR_STORAGE_KEY, JSON.stringify(seeded));
    window.localStorage.setItem(REPAIR_SEED_KEY, "true");
    setRepairs(seeded);
    setLoaded(true);
  }, []);

  useEffect(() => {
    if (!loaded) return;
    window.localStorage.setItem(REPAIR_STORAGE_KEY, JSON.stringify(repairs));
  }, [loaded, repairs]);

  function updateRepair(id: string, patch: Partial<RepairRow>) {
    setRepairs((rows) =>
      rows.map((row) =>
        row.id === id
          ? {
              ...row,
              ...patch,
              updatedAt: new Date().toISOString(),
            }
          : row,
      ),
    );
  }

  function addRepair() {
    setRepairs((rows) => [makeBlankRepair(), ...rows]);
  }

  function removeRepair(id: string) {
    const row = repairs.find((repair) => repair.id === id);
    if (!window.confirm(`Delete repair row "${row?.model || id}"?`)) return;
    setRepairs((rows) => rows.filter((repair) => repair.id !== id));
  }

  return { repairs, updateRepair, addRepair, removeRepair, loaded };
}

export function RepairsWorkspace({ mode }: RepairsWorkspaceProps) {
  const { repairs, updateRepair, addRepair, removeRepair, loaded } = useRepairs();
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | RepairStatus>("ALL");

  const employees = useMemo(() => {
    const names = new Set<string>();
    repairs.forEach((row) => {
      if (row.assignedTo.trim()) names.add(row.assignedTo.trim());
      if (row.repairedBy.trim()) names.add(row.repairedBy.trim());
    });
    return [...names].sort((a, b) => a.localeCompare(b));
  }, [repairs]);

  const filteredRepairs = useMemo(() => {
    const q = query.trim().toLowerCase();
    return repairs.filter((row) => {
      if (statusFilter !== "ALL" && row.status !== statusFilter) return false;
      if (!q) return true;
      return [row.model, row.repairType, row.company, row.rmaNumber, row.assignedTo, row.repairedBy, row.notes]
        .join(" ")
        .toLowerCase()
        .includes(q);
    });
  }, [query, repairs, statusFilter]);

  if (!loaded) {
    return <p className="muted">Loading repairs...</p>;
  }

  if (mode === "dashboard") {
    return <RepairsDashboard repairs={repairs} />;
  }

  return (
    <>
      <div className="toolbar">
        <label className="field">
          <span>Search</span>
          <input
            className="input"
            placeholder="Model, company, RMA, employee..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="field">
          <span>Status</span>
          <select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as "ALL" | RepairStatus)}>
            <option value="ALL">All statuses</option>
            <option value="OPEN">Open</option>
            <option value="IN_PROGRESS">In progress</option>
            <option value="DONE">Done</option>
          </select>
        </label>
        <button type="button" className="button" onClick={addRepair}>
          Add repair
        </button>
      </div>

      <datalist id="repair-employees">
        {employees.map((employee) => (
          <option key={employee} value={employee} />
        ))}
      </datalist>

      <div className="table-wrap">
        <table aria-label="Editable repairs table">
          <thead>
            <tr>
              <th>Qty</th>
              <th>Processor</th>
              <th>Repair</th>
              <th>Company</th>
              <th>RMA #</th>
              <th>RMA form</th>
              <th>Assigned to</th>
              <th>Repaired by</th>
              <th>Status</th>
              <th>Notes</th>
              <th>Updated</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filteredRepairs.map((row) => (
              <tr key={row.id}>
                <td className="cell-number">
                  <input
                    className="input"
                    min={0}
                    type="number"
                    value={row.quantity}
                    onChange={(event) => updateRepair(row.id, { quantity: Number.parseInt(event.target.value, 10) || 0 })}
                  />
                </td>
                <td>
                  <input className="input" value={row.model} onChange={(event) => updateRepair(row.id, { model: event.target.value })} />
                </td>
                <td>
                  <input className="input" value={row.repairType} onChange={(event) => updateRepair(row.id, { repairType: event.target.value })} />
                </td>
                <td>
                  <input className="input" value={row.company} onChange={(event) => updateRepair(row.id, { company: event.target.value })} />
                </td>
                <td>
                  <input className="input" value={row.rmaNumber} onChange={(event) => updateRepair(row.id, { rmaNumber: event.target.value })} />
                </td>
                <td>
                  <input
                    className="input"
                    placeholder="https://..."
                    value={row.rmaFormUrl}
                    onChange={(event) => updateRepair(row.id, { rmaFormUrl: event.target.value })}
                  />
                  {row.rmaFormUrl ? (
                    <a className="muted" href={row.rmaFormUrl} target="_blank" rel="noreferrer">
                      Open form
                    </a>
                  ) : null}
                </td>
                <td>
                  <input
                    className="input"
                    list="repair-employees"
                    value={row.assignedTo}
                    onChange={(event) => updateRepair(row.id, { assignedTo: event.target.value })}
                  />
                </td>
                <td>
                  <input
                    className="input"
                    list="repair-employees"
                    value={row.repairedBy}
                    onChange={(event) => updateRepair(row.id, { repairedBy: event.target.value })}
                  />
                </td>
                <td>
                  <select className="input" value={row.status} onChange={(event) => updateRepair(row.id, { status: normalizeStatus(event.target.value) })}>
                    <option value="OPEN">Open</option>
                    <option value="IN_PROGRESS">In progress</option>
                    <option value="DONE">Done</option>
                  </select>
                </td>
                <td>
                  <textarea className="input" rows={2} value={row.notes} onChange={(event) => updateRepair(row.id, { notes: event.target.value })} />
                </td>
                <td className="muted">{new Date(row.updatedAt).toLocaleDateString()}</td>
                <td>
                  <button type="button" className="button danger" onClick={() => removeRepair(row.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function RepairsDashboard({ repairs }: { repairs: RepairRow[] }) {
  const openRepairs = repairs.filter((row) => row.status !== "DONE");
  const completedRepairs = repairs.filter((row) => row.status === "DONE");
  const companyGroups = groupRepairUnits(repairs, "company");
  const assignedGroups = groupRepairUnits(openRepairs, "assignedTo");
  const repairedByGroups = groupRepairUnits(completedRepairs, "repairedBy");

  return (
    <div className="grid">
      <section className="grid cards">
        <Metric label="Repair rows" value={repairs.length} />
        <Metric label="Processor units" value={repairUnitTotal(repairs)} />
        <Metric label="Open units" value={repairUnitTotal(openRepairs)} />
        <Metric label="Completed units" value={repairUnitTotal(completedRepairs)} />
      </section>

      <section className="grid two-col">
        <SummaryPanel title="Repairs by company" rows={companyGroups} empty="No companies assigned yet." />
        <SummaryPanel title="Open repairs by assignee" rows={assignedGroups} empty="No assigned open repairs yet." />
        <SummaryPanel title="Completed repairs by employee" rows={repairedByGroups} empty="No completed repairs yet." />
        <div className="panel">
          <h2>Recent repair rows</h2>
          <ul className="list">
            {[...repairs]
              .sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
              .slice(0, 8)
              .map((row) => (
                <li key={row.id}>
                  <span>
                    {row.quantity} x {row.model || "Unnamed processor"}
                    <br />
                    <span className="muted">{row.company || "No company"} - {row.assignedTo || "Unassigned"}</span>
                  </span>
                  <span className={`status ${row.status.toLowerCase()}`}>{statusLabels[row.status]}</span>
                </li>
              ))}
          </ul>
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <dl className="metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </dl>
  );
}

function SummaryPanel({ title, rows, empty }: { title: string; rows: Array<{ label: string; count: number }>; empty: string }) {
  return (
    <div className="panel">
      <h2>{title}</h2>
      {rows.length === 0 ? (
        <p className="muted">{empty}</p>
      ) : (
        <ul className="list">
          {rows.slice(0, 10).map((row) => (
            <li key={row.label}>
              <span>{row.label}</span>
              <strong>{row.count}</strong>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
