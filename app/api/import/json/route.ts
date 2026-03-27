import AdmZip from "adm-zip";
import { NextRequest, NextResponse } from "next/server";

import { getGithubUser } from "@/lib/auth";
import { importZipBuffer } from "@/lib/import-export";
import { ensureHubMetaHydrated, PersistenceError } from "@/lib/workflow-store";

function detectInnerName(fileName: string): string {
  const base = fileName.toLowerCase().split("/").pop() || fileName.toLowerCase();
  if (base === "internal_agents.json") {
    return "internal_agents.json";
  }
  if (base.includes("expert")) {
    return "oasis_experts.json";
  }
  return "external_agents.json";
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

  let rawBytes: Buffer | null = null;
  let fileName = "upload.json";
  let author = "Imported";

  const contentType = request.headers.get("content-type") || "";
  if (contentType.includes("multipart/form-data")) {
    const formData = await request.formData();
    const file = formData.get("file");
    if (!(file instanceof File)) {
      return NextResponse.json({ error: "No file uploaded" }, { status: 400 });
    }

    rawBytes = Buffer.from(await file.arrayBuffer());
    fileName = file.name;
    author = String(formData.get("author") ?? "Imported");
  } else {
    let body: Record<string, unknown>;
    try {
      body = (await request.json()) as Record<string, unknown>;
    } catch {
      return NextResponse.json({ error: "No file or JSON body provided. Please upload a .zip file instead." }, { status: 400 });
    }

    rawBytes = Buffer.from(JSON.stringify(body), "utf-8");
    fileName = String(body._filename ?? "upload.json");
  }

  const zip = new AdmZip();
  zip.addFile(detectInnerName(fileName), rawBytes);

  try {
    const result = await importZipBuffer(zip.toBuffer(), {
      author,
      team_name: "",
      extra_agents: [],
      fileName: fileName.replace(/\.json$/i, ".zip")
    });

    return NextResponse.json(result);
  } catch (error) {
    if (error instanceof PersistenceError) {
      return NextResponse.json({ error: error.message }, { status: 503 });
    }
    return NextResponse.json({ error: String(error instanceof Error ? error.message : error) }, { status: 500 });
  }
}
