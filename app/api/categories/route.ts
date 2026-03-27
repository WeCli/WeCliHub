import { NextResponse } from "next/server";

import { ensureHubMetaHydrated, listCategories } from "@/lib/workflow-store";

export async function GET() {
  await ensureHubMetaHydrated();
  return NextResponse.json(listCategories());
}
