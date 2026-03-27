import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import { ensureHubMetaHydrated, PersistenceError, updateWorkflow } from "@/lib/workflow-store";

export async function PATCH(request: NextRequest, context: { params: Promise<{ workflowId: string }> }) {
  const user = getGithubUser(request);
  if (!user) {
    return NextResponse.json({ error: "Login required" }, { status: 401 });
  }

  await ensureHubMetaHydrated();

  const { workflowId } = await context.params;

  let data: Record<string, unknown>;
  try {
    data = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "Invalid body" }, { status: 400 });
  }

  try {
    const updated = await updateWorkflow(workflowId, user.login, {
      title: data.title !== undefined ? String(data.title) : undefined,
      description: data.description !== undefined ? String(data.description) : undefined,
      yaml_content: data.yaml_content !== undefined ? String(data.yaml_content) : undefined,
      category: data.category !== undefined ? String(data.category) : undefined,
      tags: Array.isArray(data.tags) ? data.tags.map((t) => String(t)) : undefined,
      icon: data.icon !== undefined ? String(data.icon) : undefined,
      detail: data.detail !== undefined ? String(data.detail) : undefined,
    });

    if (!updated) {
      return NextResponse.json(
        { error: "Workflow not found or you don't have permission to edit it" },
        { status: 403 }
      );
    }

    return NextResponse.json({ status: "ok", workflow: updated });
  } catch (error) {
    if (error instanceof PersistenceError) {
      return NextResponse.json({ error: error.message }, { status: 503 });
    }
    return NextResponse.json({ error: String(error instanceof Error ? error.message : error) }, { status: 400 });
  }
}
