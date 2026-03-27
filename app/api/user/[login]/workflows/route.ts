import { NextResponse } from "next/server";

import { PRESET_WORKFLOWS } from "@/lib/constants";
import type { Workflow } from "@/lib/types";
import { ensureHubMetaHydrated, loadHubMeta, parseYamlPlanSummary } from "@/lib/workflow-store";

export async function GET(_: Request, context: { params: Promise<{ login: string }> }) {
  await ensureHubMetaHydrated();

  const { login } = await context.params;

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
    published_at?: string;
    steps: number;
    localizations?: Workflow["localizations"];
  }> = [];

  // Check preset workflows for matching author/github_user
  PRESET_WORKFLOWS.forEach((preset) => {
    if (preset.github_user === login || preset.author.toLowerCase() === login.toLowerCase()) {
      const summary = parseYamlPlanSummary(preset.yaml_content);
      workflows.push({
        id: preset.id,
        title: preset.title,
        description: preset.description,
        icon: preset.icon,
        stars: preset.stars,
        forks: preset.forks,
        category: preset.category,
        tags: preset.tags,
        source: "preset",
        steps: summary.steps,
        localizations: preset.localizations
      });
    }
  });

  // Check community (hub_meta) workflows
  const meta = loadHubMeta();
  meta.workflows.forEach((w) => {
    if (w.github_user === login || w.author.toLowerCase() === login.toLowerCase()) {
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
        source: "community",
        published_at: w.published_at,
        steps: summary.steps,
        localizations: w.localizations
      });
    }
  });

  return NextResponse.json({ login, workflows, total: workflows.length });
}
