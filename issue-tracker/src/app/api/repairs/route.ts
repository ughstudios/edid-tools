import { createRepair, listRepairs } from "@/lib/repair-store";
import { makeBlankRepair } from "@/lib/repairs";
import { NextResponse } from "next/server";

export async function GET() {
  const repairs = await listRepairs();
  return NextResponse.json({ repairs });
}

export async function POST() {
  const repair = await createRepair(makeBlankRepair());
  return NextResponse.json({ repair }, { status: 201 });
}
