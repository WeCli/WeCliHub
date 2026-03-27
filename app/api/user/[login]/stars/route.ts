import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import type { Workflow } from "@/lib/types";
import { ensureHubMetaHydrated, ensureStarRecordsHydrated, getUserStarredWorkflowIds, getWorkflowById, parseYamlPlanSummary } from "@/lib/workflow-store";

export async function GET(request: NextRequest, context: { params: Promise<{ login: string }> }) {
  const { login } = await context.params;

  // Only allow the current user to see their own stars
  const currentUser = getGithubUser(request);
  if (!currentUser || currentUser.login !== login) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  await Promise.all([ensureHubMetaHydrated(), ensureStarRecordsHydrated()]);

  const starredIds = getUserStarredWorkflowIds(login);
  const workflows: Array<{
    id: string;
    title: string;
    description: string;
    icon: string;
    stars: number;
    forks: number;
    category: string;
    tags: string[];
    source: string;
    steps: number;
    localizations?: Workflow["localizations"];
  }> = [];

  for (const wid of starredIds) {
    const w = getWorkflowById(wid);
    if (w) {
      const summary = parseYamlPlanSummary(w.yaml_content ?? "");
      workflows.push({
        id: w.id,
        title: w.title ?? "Untitled",
        description: w.description ?? "",
        icon: w.icon ?? "📦",
        stars: Number(w.stars ?? 0),
        forks: Number(w.forks ?? 0),
        category: w.category ?? "Community",
        tags: Array.isArray(w.tags) ? w.tags : [],
        source: w.source ?? "community",
        steps: summary.steps,
        localizations: w.localizations
      });
    }
  }

  return NextResponse.json({ login, workflows, total: workflows.length });
}
