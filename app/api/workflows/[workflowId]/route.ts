import { NextResponse } from "next/server";

import { ensureHubMetaHydrated, getWorkflowById } from "@/lib/workflow-store";

export async function GET(_: Request, context: { params: Promise<{ workflowId: string }> }) {
  await ensureHubMetaHydrated();

  const { workflowId } = await context.params;
  const workflow = getWorkflowById(workflowId);
  if (!workflow) {
    return NextResponse.json({ error: "Workflow not found" }, { status: 404 });
  }
  return NextResponse.json(workflow);
}
