import { NextResponse } from "next/server";

import { exportWorkflowZip } from "@/lib/import-export";
import { ensureHubMetaHydrated } from "@/lib/workflow-store";

export async function GET(_: Request, context: { params: Promise<{ workflowId: string }> }) {
  await ensureHubMetaHydrated();

  const { workflowId } = await context.params;
  const exported = exportWorkflowZip(workflowId);
  if (!exported) {
    return NextResponse.json({ error: "Workflow not found" }, { status: 404 });
  }

  const body = Uint8Array.from(exported.buffer);
  return new NextResponse(body, {
    headers: {
      "content-type": "application/zip",
      "content-disposition": `attachment; filename="${exported.filename}"`
    }
  });
}
