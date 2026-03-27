import path from "node:path";

import AdmZip from "adm-zip";
import yaml from "js-yaml";

import { buildWorkflowLocalizations } from "@/lib/translation";
import type { Agent, CronJob, Expert, SkillInfo, Workflow } from "@/lib/types";
import { extractExpertsFromYaml, getWorkflowById, loadHubMeta, saveHubMeta } from "@/lib/workflow-store";

function randomHex(length: number): string {
  const chars = "0123456789abcdef";
  let out = "";
  for (let i = 0; i < length; i += 1) {
    out += chars[Math.floor(Math.random() * chars.length)];
  }
  return out;
}

type ImportOptions = {
  author?: string;
  team_name?: string;
  extra_agents?: Agent[];
  description?: string;
  category?: string;
  tags?: string[];
  fileName?: string;
};

function asAgentArray(raw: unknown): Agent[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item) => item && typeof item === "object") as Agent[];
}

function parseJson(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function isExternalAgentsFile(fileName: string): boolean {
  const base = fileName.toLowerCase();
  if (base === "internal_agents.json" || base === "oasis_experts.json") {
    return false;
  }
  return base.endsWith("_agents.json") || base.includes("external") || base.includes("openclaw");
}

function isValidWorkflowYaml(content: string): boolean {
  try {
    const parsed = yaml.load(content);
    return Boolean(parsed && typeof parsed === "object" && (parsed as Record<string, unknown>).plan);
  } catch {
    return false;
  }
}

/**
 * Merge two Expert arrays, preferring entries from `primary` over `secondary`.
 * De-duplicates by tag (case-insensitive). Primary entries that have a non-empty
 * persona always win; otherwise the secondary entry is used as fallback.
 */
function mergeExperts(primary: Expert[], secondary: Expert[]): Expert[] {
  const byTag = new Map<string, Expert>();
  for (const expert of primary) {
    const key = (expert.tag || expert.name || "").toLowerCase();
    if (key) byTag.set(key, expert);
  }
  for (const expert of secondary) {
    const key = (expert.tag || expert.name || "").toLowerCase();
    if (!key) continue;
    const existing = byTag.get(key);
    if (!existing) {
      byTag.set(key, expert);
    } else if (!existing.persona && expert.persona) {
      // Secondary has richer data — use it
      byTag.set(key, expert);
    }
  }
  return [...byTag.values()];
}

// Maximum allowed uncompressed size (50 MB) to prevent zip bombs
const MAX_UNCOMPRESSED_SIZE = 50 * 1024 * 1024;
// Maximum number of entries allowed in a ZIP
const MAX_ZIP_ENTRIES = 500;
// Forbidden path patterns (path traversal, hidden files, etc.)
const UNSAFE_PATH_RE = /(?:^|[\/])\.\.(?:[\/]|$)|^\//;

export async function importZipBuffer(buffer: Buffer, options: ImportOptions) {
  let zip: AdmZip;
  try {
    zip = new AdmZip(buffer);
  } catch {
    throw new Error("Cannot read ZIP file — the file may be corrupted or is not a valid ZIP archive");
  }

  const entries = zip.getEntries();

  if (entries.length === 0) {
    throw new Error("ZIP file is empty — no files found inside the archive");
  }

  if (entries.length > MAX_ZIP_ENTRIES) {
    throw new Error(`ZIP file contains too many entries (${entries.length}). Maximum allowed: ${MAX_ZIP_ENTRIES}`);
  }

  // Security: check total uncompressed size and path traversal
  let totalSize = 0;
  for (const entry of entries) {
    totalSize += entry.header.size;
    if (totalSize > MAX_UNCOMPRESSED_SIZE) {
      throw new Error("ZIP file is too large when uncompressed (>50 MB). Possible zip bomb detected");
    }
    if (UNSAFE_PATH_RE.test(entry.entryName)) {
      throw new Error(`ZIP file contains unsafe path: "${entry.entryName}". Path traversal is not allowed`);
    }
  }

  const imported: string[] = [];
  let internalAgents: Agent[] = [];
  let externalAgents: Agent[] = [];
  let expertsList: Expert[] = [];
  const skillsData: Record<string, string> = {};
  let cronJobs: Record<string, CronJob[]> = {};
  const skillsInfo: Record<string, Record<string, SkillInfo>> = {};

  entries.forEach((entry) => {
    if (entry.isDirectory) {
      return;
    }

    const name = entry.entryName;
    const base = path.basename(name);

    if (name.startsWith("skills/")) {
      skillsData[name] = entry.getData().toString("base64");

      // Parse skills metadata to build skills_info per agent
      const parts = name.split("/");
      // Expected structures:
      //   skills/<agentName>/<skillName>/_meta.json           (4 parts)
      //   skills/<agentName>/<skillName>/.clawhub/origin.json (5 parts)
      if (parts.length >= 4) {
        const agentName = parts[1];
        const skillName = parts[2];
        if (base === "_meta.json" || base === "origin.json") {
          try {
            const metaContent = JSON.parse(entry.getData().toString("utf-8"));
            if (!skillsInfo[agentName]) skillsInfo[agentName] = {};
            if (!skillsInfo[agentName][skillName]) skillsInfo[agentName][skillName] = {};
            if (base === "_meta.json") {
              skillsInfo[agentName][skillName].meta = metaContent;
            } else {
              skillsInfo[agentName][skillName].origin = metaContent;
            }
          } catch {
            // ignore malformed JSON
          }
        }
        // Collect skill file list
        if (!skillsInfo[agentName]) skillsInfo[agentName] = {};
        if (!skillsInfo[agentName][skillName]) skillsInfo[agentName][skillName] = {};
        if (!skillsInfo[agentName][skillName].files) skillsInfo[agentName][skillName].files = [];
        skillsInfo[agentName][skillName].files!.push(base);
      }
    }

    const fileText = entry.getData().toString("utf-8");

    // Parse cron_jobs.json
    if (base === "cron_jobs.json") {
      const parsed = parseJson(fileText);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        cronJobs = parsed as Record<string, CronJob[]>;
      }
    }

    if (base === "internal_agents.json") {
      const parsed = parseJson(fileText);
      internalAgents = asAgentArray(parsed).map((agent) => {
        const { session, ...rest } = agent;
        return rest;
      });
    } else if (isExternalAgentsFile(base)) {
      externalAgents = [...externalAgents, ...asAgentArray(parseJson(fileText))];
    } else if (base === "oasis_experts.json") {
      const parsed = parseJson(fileText);
      if (Array.isArray(parsed)) {
        // Support both full Expert objects and legacy string-only tag lists
        expertsList = parsed
          .filter((item) => item != null)
          .map((item) => {
            if (typeof item === "string") {
              return { name: item, tag: item, persona: "", temperature: 0.7 };
            }
            if (typeof item === "object") {
              const obj = item as Record<string, unknown>;
              return {
                name: String(obj.name ?? obj.tag ?? "Unknown"),
                tag: String(obj.tag ?? obj.name ?? ""),
                persona: String(obj.persona ?? ""),
                temperature: typeof obj.temperature === "number" ? obj.temperature : 0.7,
              };
            }
            return null;
          })
          .filter(Boolean) as Expert[];
      }
    }
  });

  const seenExternal = new Set<string>();
  externalAgents = externalAgents.filter((agent) => {
    const key = `${String(agent.name ?? "").trim().toLowerCase()}::${String(agent.tag ?? "").trim().toLowerCase()}`;
    if (!key || seenExternal.has(key)) {
      return false;
    }
    seenExternal.add(key);
    return true;
  });

  const extraAgents = Array.isArray(options.extra_agents) ? options.extra_agents : [];
  extraAgents.forEach((agent) => {
    if (!agent || typeof agent.name !== "string" || !agent.name.trim()) {
      return;
    }
    if (internalAgents.some((current) => current.name === agent.name)) {
      return;
    }
    internalAgents.push({
      name: agent.name,
      tag: agent.tag ?? ""
    });
  });

  const yamlFiles = entries
    .filter((entry) => !entry.isDirectory && (entry.entryName.endsWith(".yaml") || entry.entryName.endsWith(".yml")))
    .map((entry) => ({
      path: entry.entryName,
      fileName: path.basename(entry.entryName),
      content: entry.getData().toString("utf-8")
    }))
    .filter((entry) => isValidWorkflowYaml(entry.content));

  const zipName = options.fileName ?? "upload.zip";
  const zipStem = path.basename(zipName).replace(/\.zip$/i, "");
  const baseTitle = (options.team_name || zipStem).replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());

  const meta = loadHubMeta();

  // Build a yaml_files map of all YAML files (filename → content)
  const yamlFilesMap: Record<string, string> = {};
  yamlFiles.forEach((entry) => {
    yamlFilesMap[entry.fileName] = entry.content;
  });

  if (yamlFiles.length > 0) {
    // For v2: store as ONE workflow entry with all YAML files and a yaml_files map
    // The primary yaml_content is the first YAML file
    const primaryYaml = yamlFiles[0];
    const mergedTags = [...new Set([...(options.tags ?? []), "team", "snapshot"])];

    // Merge experts from all YAML files
    let combinedExperts = [...expertsList];
    yamlFiles.forEach((entry) => {
      const yamlExtracted = extractExpertsFromYaml(entry.content);
      combinedExperts = mergeExperts(combinedExperts, yamlExtracted.experts);
    });

    const workflow: Workflow = {
      id: `community_${randomHex(8)}`,
      title: baseTitle,
      description:
        options.description || `Team snapshot with ${internalAgents.length} internal agents, ${externalAgents.length} external agents`,
      author: options.author || "Imported",
      tags: mergedTags,
      category: options.category || "Community",
      stars: 0,
      forks: 0,
      icon: "📦",
      yaml_content: primaryYaml.content,
      detail: "",
      published_at: new Date().toISOString(),
      internal_agents: internalAgents,
      external_agents: externalAgents,
      oasis_agents: internalAgents,
      openclaw_agents: externalAgents,
      experts: combinedExperts,
      experts_detail: combinedExperts,
      skills_data: skillsData,
      skills_info: Object.keys(skillsInfo).length > 0 ? skillsInfo : undefined,
      cron_jobs: Object.keys(cronJobs).length > 0 ? cronJobs : undefined,
      yaml_files: yamlFiles.length > 1 ? yamlFilesMap : undefined
    };

    workflow.localizations = await buildWorkflowLocalizations(workflow);
    meta.workflows.push(workflow);

    imported.push(baseTitle);
  }

  if (!yamlFiles.length && (internalAgents.length || externalAgents.length || expertsList.length)) {
    const names = [...internalAgents, ...externalAgents].map((agent) => agent.name || "?");
    const mergedTags = [...new Set([...(options.tags ?? []), "team", "snapshot"])];
    const title = baseTitle || `Team Snapshot (${names.length} agents)`;

    const workflow: Workflow = {
      id: `community_${randomHex(8)}`,
      title,
      description: options.description || `Agents: ${names.slice(0, 5).join(", ")}${names.length > 5 ? "..." : ""}`,
      author: options.author || "Imported",
      tags: mergedTags,
      category: options.category || "Community",
      stars: 0,
      forks: 0,
      icon: "👥",
      yaml_content: "",
      detail: "",
      published_at: new Date().toISOString(),
      internal_agents: internalAgents,
      external_agents: externalAgents,
      oasis_agents: internalAgents,
      openclaw_agents: externalAgents,
      experts: expertsList,
      experts_detail: expertsList,
      skills_data: skillsData,
      skills_info: Object.keys(skillsInfo).length > 0 ? skillsInfo : undefined,
      cron_jobs: Object.keys(cronJobs).length > 0 ? cronJobs : undefined
    };

    workflow.localizations = await buildWorkflowLocalizations(workflow);
    meta.workflows.push(workflow);

    imported.push(title);
  }

  if (!imported.length) {
    throw new Error("ZIP file does not contain any valid workflow YAML files or agent/expert definitions");
  }

  await saveHubMeta(meta);

  return {
    status: "ok",
    imported,
    count: imported.length,
    internal_agents_count: internalAgents.length,
    external_agents_count: externalAgents.length,
    experts_count: expertsList.length,
    extra_agents_added: extraAgents.length
  };
}

function sanitizeFileName(value: string): string {
  return value
    .toLowerCase()
    .replace(/[\s—]+/g, "_")
    .replace(/[^a-z0-9_-]/g, "")
    .slice(0, 40);
}

export function exportWorkflowZip(workflowId: string): { buffer: Buffer; filename: string } | null {
  const workflow = getWorkflowById(workflowId);
  if (!workflow) {
    return null;
  }

  const zip = new AdmZip();
  const yamlContent = workflow.yaml_content || "";

  const extracted = yamlContent ? extractExpertsFromYaml(yamlContent) : { experts: [], internalAgents: [] };

  const internal =
    (Array.isArray(workflow.internal_agents) && workflow.internal_agents.length
      ? workflow.internal_agents
      : Array.isArray(workflow.oasis_agents) && workflow.oasis_agents.length
        ? workflow.oasis_agents
        : extracted.internalAgents
    ).map((agent) => {
      const { session, ...rest } = agent;
      return rest;
    });

  if (internal.length) {
    zip.addFile("internal_agents.json", Buffer.from(JSON.stringify(internal, null, 2), "utf-8"));
  }

  const externalRaw = workflow.external_agents ?? workflow.openclaw_agents ?? [];
  let external: Agent[] = [];
  if (Array.isArray(externalRaw)) {
    external = externalRaw.map((agent) => {
      const { global_name, session, ...rest } = agent as Agent & { global_name?: string };
      return rest;
    });
  } else if (externalRaw && typeof externalRaw === "object") {
    external = Object.entries(externalRaw).map(([name, data]) => {
      const row = typeof data === "object" && data !== null ? (data as Record<string, unknown>) : {};
      return {
        name,
        tag: "openclaw",
        config: (row.config as Agent["config"]) ?? {},
        workspace_files: (row.workspace_files as Agent["workspace_files"]) ?? {}
      };
    });
  }

  if (external.length) {
    zip.addFile("external_agents.json", Buffer.from(JSON.stringify(external, null, 2), "utf-8"));
  }

  // Build full expert definitions for oasis_experts.json
  // Priority: experts_detail > experts (if object array) > extracted from YAML + builtin lookup
  let fullExperts: Expert[] = [];

  if (Array.isArray(workflow.experts_detail) && workflow.experts_detail.length > 0) {
    // Best source: already-resolved full expert objects
    fullExperts = workflow.experts_detail;
  } else if (
    Array.isArray(workflow.experts) &&
    workflow.experts.length > 0 &&
    typeof workflow.experts[0] === "object"
  ) {
    // Stored experts are already full Expert objects
    fullExperts = workflow.experts as Expert[];
  } else {
    // Fallback: use extractExpertsFromYaml which resolves tags → full definitions via builtin lookup
    fullExperts = extracted.experts;
  }

  // Ensure every expert entry has the required fields (name, tag, persona, temperature)
  fullExperts = fullExperts.map((e) => ({
    name: e.name || e.tag || "Unknown",
    tag: e.tag || "",
    persona: e.persona || "",
    temperature: typeof e.temperature === "number" ? e.temperature : 0.7,
  }));

  if (fullExperts.length) {
    zip.addFile("oasis_experts.json", Buffer.from(JSON.stringify(fullExperts, null, 2), "utf-8"));
  }

  // Export YAML files: if yaml_files map exists (multiple), export all; otherwise export single
  if (workflow.yaml_files && typeof workflow.yaml_files === "object" && Object.keys(workflow.yaml_files).length > 0) {
    Object.entries(workflow.yaml_files).forEach(([fileName, content]) => {
      zip.addFile(`oasis/yaml/${fileName}`, Buffer.from(content, "utf-8"));
    });
  } else if (yamlContent) {
    const safeName = sanitizeFileName(workflow.title || "workflow") || "my-layout";
    zip.addFile(`oasis/yaml/${safeName}.yaml`, Buffer.from(yamlContent, "utf-8"));
  }

  // Export cron_jobs.json if available
  if (workflow.cron_jobs && typeof workflow.cron_jobs === "object" && Object.keys(workflow.cron_jobs).length > 0) {
    zip.addFile("cron_jobs.json", Buffer.from(JSON.stringify(workflow.cron_jobs, null, 2), "utf-8"));
  }

  if (workflow.skills_data && typeof workflow.skills_data === "object") {
    Object.entries(workflow.skills_data).forEach(([relPath, b64]) => {
      try {
        zip.addFile(relPath, Buffer.from(b64, "base64"));
      } catch {
        // ignore invalid base64
      }
    });
  }

  const safeTitle = sanitizeFileName(workflow.title || "workflow") || "workflow";
  const timestamp = new Date().toISOString().replace(/[-:]/g, "").replace(/T/, "_").slice(0, 15);

  return {
    buffer: zip.toBuffer(),
    filename: `team_${safeTitle}_snapshot_${timestamp}.zip`
  };
}
