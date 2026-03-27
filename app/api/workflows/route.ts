import { NextRequest, NextResponse } from "next/server";

import { ensureHubMetaHydrated, listWorkflows } from "@/lib/workflow-store";

export async function GET(request: NextRequest) {
  await ensureHubMetaHydrated();

  const search = request.nextUrl.searchParams.get("search") ?? "";
  const category = request.nextUrl.searchParams.get("category") ?? "";
  const tag = request.nextUrl.searchParams.get("tag") ?? "";

  const data = listWorkflows({ search, category, tag });
  return NextResponse.json(data);
}
