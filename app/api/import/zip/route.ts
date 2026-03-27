import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import { importZipBuffer } from "@/lib/import-export";
import type { Agent } from "@/lib/types";
import { ensureHubMetaHydrated, PersistenceError } from "@/lib/workflow-store";

function parseJsonArray(value: FormDataEntryValue | null): unknown[] {
  if (!value || typeof value !== "string") {
    return [];
  }
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

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

  const formData = await request.formData();
  const file = formData.get("file");
  if (!(file instanceof File)) {
    return NextResponse.json({ error: "No file uploaded" }, { status: 400 });
  }

  if (!file.name.endsWith(".zip")) {
    return NextResponse.json({ error: "File must be a .zip" }, { status: 400 });
  }

  const tags = parseJsonArray(formData.get("tags")).map((item) => String(item));
  const extraAgents = parseJsonArray(formData.get("extra_agents")) as Agent[];

  try {
    const buffer = Buffer.from(await file.arrayBuffer());
    const result = await importZipBuffer(buffer, {
      author: String(formData.get("author") ?? "Imported"),
      team_name: String(formData.get("team_name") ?? ""),
      description: String(formData.get("description") ?? ""),
      category: String(formData.get("category") ?? ""),
      tags,
      extra_agents: extraAgents,
      fileName: file.name
    });

    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof PersistenceError) {
      return NextResponse.json({ error: error.message }, { status: 503 });
    }
    const message = error instanceof Error ? error.message : "Invalid or corrupted ZIP file";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
