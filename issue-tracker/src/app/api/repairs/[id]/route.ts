import { deleteRepair, updateRepair } from "@/lib/repair-store";
import type { RepairRow } from "@/lib/repairs";
import { NextResponse } from "next/server";

export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const patch = (await request.json()) as Partial<RepairRow>;
  const repair = await updateRepair(id, patch);
  if (!repair) {
    return NextResponse.json({ error: "Repair not found." }, { status: 404 });
  }
  return NextResponse.json({ repair });
}

export async function DELETE(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  await deleteRepair(id);
  return NextResponse.json({ ok: true });
}
