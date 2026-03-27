import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import { ensureHubMetaHydrated, ensureStarRecordsHydrated, isWorkflowStarredByUser, PersistenceError, starWorkflowByUser } from "@/lib/workflow-store";

export async function POST(request: NextRequest, context: { params: Promise<{ workflowId: string }> }) {
  const user = getGithubUser(request);
  if (!user) {
    return NextResponse.json({ error: "GitHub login required to star workflows. Please log in first." }, { status: 401 });
  }

  await Promise.all([ensureHubMetaHydrated(), ensureStarRecordsHydrated()]);

  const { workflowId } = await context.params;
  let result = null;
  try {
    result = await starWorkflowByUser(workflowId, user.login);
  } catch (error) {
    if (error instanceof PersistenceError) {
      return NextResponse.json({ error: error.message }, { status: 503 });
    }
    return NextResponse.json({ error: "Failed to update star status" }, { status: 500 });
  }
  if (result === null) {
    return NextResponse.json({ error: "Workflow not found" }, { status: 404 });
  }
  return NextResponse.json({ stars: result.stars, starred: result.starred });
}

export async function GET(request: NextRequest, context: { params: Promise<{ workflowId: string }> }) {
  const user = getGithubUser(request);
  if (!user) {
    return NextResponse.json({ starred: false });
  }

  await ensureStarRecordsHydrated();

  const { workflowId } = await context.params;
  const starred = isWorkflowStarredByUser(workflowId, user.login);
  return NextResponse.json({ starred });
}
