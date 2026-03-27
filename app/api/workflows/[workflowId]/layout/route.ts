import { NextResponse } from "next/server";

import { yamlToLayoutData } from "@/lib/layout";
import { ensureHubMetaHydrated, getWorkflowById } from "@/lib/workflow-store";

export async function GET(_: Request, context: { params: Promise<{ workflowId: string }> }) {
  await ensureHubMetaHydrated();

  const { workflowId } = await context.params;
  const workflow = getWorkflowById(workflowId);
  if (!workflow) {
    return NextResponse.json({ error: "Workflow not found" }, { status: 404 });
  }

  const yamlContent = workflow.yaml_content || "";
  const result = yamlToLayoutData(yamlContent);
  if (!result.available) {
    return NextResponse.json({ error: result.error }, { status: 503 });
  }
  if (result.error) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return NextResponse.json(result.data ?? {});
}
