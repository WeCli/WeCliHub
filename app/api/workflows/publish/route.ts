import yaml from "js-yaml";
import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import { ensureHubMetaHydrated, PersistenceError, publishWorkflow } from "@/lib/workflow-store";

export async function POST(request: NextRequest) {
  const user = getGithubUser(request);
  if (!user) {
    return NextResponse.json(
      {
        error: "GitHub login required to publish/upload workflows. Please log in first."
      },
      { status: 401 }
    );
  }

  await ensureHubMetaHydrated();

  let data: Record<string, unknown>;
  try {
    data = (await request.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "No data provided" }, { status: 400 });
  }

  if (!data || typeof data !== "object") {
    return NextResponse.json({ error: "No data provided" }, { status: 400 });
  }

  const title = String(data.title ?? "").trim();
  const yamlContent = String(data.yaml_content ?? "").trim();
  if (!title) {
    return NextResponse.json({ error: "Missing required field: title" }, { status: 400 });
  }
  if (!yamlContent) {
    return NextResponse.json({ error: "Missing required field: yaml_content" }, { status: 400 });
  }

  try {
    const parsed = yaml.load(yamlContent);
    if (!parsed || typeof parsed !== "object" || !(parsed as Record<string, unknown>).plan) {
      return NextResponse.json({ error: "YAML must contain 'plan' key" }, { status: 400 });
    }
  } catch (error) {
    return NextResponse.json({ error: `Invalid YAML: ${String(error)}` }, { status: 400 });
  }

  try {
    const result = await publishWorkflow({
      title,
      yaml_content: yamlContent,
      description: String(data.description ?? ""),
      author: String(data.author ?? "Anonymous"),
      category: String(data.category ?? "Community"),
      tags: Array.isArray(data.tags) ? data.tags.map((item) => String(item)) : [],
      icon: String(data.icon ?? "📦"),
      detail: String(data.detail ?? ""),
      githubUserLogin: user.login,
      githubUserName: user.name
    });

    return NextResponse.json({ status: "ok", id: result.id });
  } catch (error) {
    if (error instanceof PersistenceError) {
      return NextResponse.json({ error: error.message }, { status: 503 });
    }
    return NextResponse.json({ error: String(error instanceof Error ? error.message : error) }, { status: 400 });
  }
}
