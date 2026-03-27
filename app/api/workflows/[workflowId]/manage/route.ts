import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import { deleteWorkflow, ensureHubMetaHydrated, ensureStarRecordsHydrated, PersistenceError } from "@/lib/workflow-store";

export async function DELETE(request: NextRequest, context: { params: Promise<{ workflowId: string }> }) {
  const user = getGithubUser(request);
  if (!user) {
    return NextResponse.json({ error: "Login required" }, { status: 401 });
  }

  await Promise.all([ensureHubMetaHydrated(), ensureStarRecordsHydrated()]);

  const { workflowId } = await context.params;
  let success = false;
  try {
    success = await deleteWorkflow(workflowId, user.login);
  } catch (error) {
    if (error instanceof PersistenceError) {
      return NextResponse.json({ error: error.message }, { status: 503 });
    }
    return NextResponse.json({ error: "Failed to delete workflow" }, { status: 500 });
  }

  if (!success) {
    return NextResponse.json(
      { error: "Workflow not found or you don't have permission to delete it" },
      { status: 403 }
    );
  }

  return NextResponse.json({ status: "ok" });
}
