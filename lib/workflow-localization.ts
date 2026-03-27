import type {
  Agent,
  CronJob,
  CronJobLocalizations,
  LocalizedText,
  SupportedLocale,
  Workflow,
  WorkflowLocalizations
} from "@/lib/types";

export type AgentLocalizationScope = "experts" | "internal_agents" | "external_agents";
export type WorkflowLocalizationField = "title" | "description" | "detail" | "category";

const TEXT_RE = /[A-Za-z\u4e00-\u9fff]/;
const CJK_RE = /[\u4e00-\u9fff]/g;
const LATIN_RE = /[A-Za-z]/g;
const FILE_NAME_RE = /^[\w.-]+\.(?:json|ya?ml|md|txt)$/i;
const TECHNICAL_TOKEN_RE = /^[a-z0-9_.:/#-]+$/i;

export function pickLocalizedText(value: string | undefined | null, localized: LocalizedText | undefined, locale: SupportedLocale): string {
  const fallback = value ?? "";
  if (!localized) {
    return fallback;
  }
  return localized[locale] ?? localized.en ?? localized.zh ?? fallback;
}

export function pickWorkflowText(
  workflow: Pick<Workflow, "localizations">,
  field: WorkflowLocalizationField,
  fallback: string,
  locale: SupportedLocale
): string {
  return pickLocalizedText(fallback, workflow.localizations?.[field], locale);
}

export function pickWorkflowTag(workflow: Pick<Workflow, "localizations">, tag: string, locale: SupportedLocale): string {
  return pickLocalizedText(tag, workflow.localizations?.tags?.[tag], locale);
}

export function makeAgentLocalizationKey(name?: string, tag?: string): string {
  return `${String(name ?? "").trim().toLowerCase()}::${String(tag ?? "").trim().toLowerCase()}`;
}

export function makeCronJobLocalizationKey(index: number): string {
  return `job_${index}`;
}

export function pickAgentText(
  localizations: WorkflowLocalizations | undefined,
  scopes: AgentLocalizationScope[],
  name: string | undefined,
  tag: string | undefined,
  field: keyof NonNullable<WorkflowLocalizations["experts"]>[string],
  fallback: string,
  locale: SupportedLocale
): string {
  const key = makeAgentLocalizationKey(name, tag);
  for (const scope of scopes) {
    const localized = localizations?.[scope]?.[key]?.[field];
    if (localized) {
      return pickLocalizedText(fallback, localized, locale);
    }
  }
  return fallback;
}

export function pickCronJobText(
  localizations: WorkflowLocalizations | undefined,
  agentName: string | undefined,
  index: number,
  field: keyof CronJobLocalizations,
  fallback: string,
  locale: SupportedLocale
): string {
  if (!agentName) {
    return fallback;
  }
  const localized = localizations?.cron_jobs?.[agentName]?.[makeCronJobLocalizationKey(index)]?.[field];
  return pickLocalizedText(fallback, localized, locale);
}

export function detectTextLocale(value: string): SupportedLocale | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const cjkCount = (trimmed.match(CJK_RE) ?? []).length;
  const latinCount = (trimmed.match(LATIN_RE) ?? []).length;
  if (cjkCount === 0 && latinCount === 0) {
    return null;
  }
  if (cjkCount > latinCount) {
    return "zh";
  }
  return "en";
}

export function isTranslatableText(value: string): boolean {
  const trimmed = value.trim();
  if (!trimmed) {
    return false;
  }
  if (!TEXT_RE.test(trimmed)) {
    return false;
  }
  if (FILE_NAME_RE.test(trimmed)) {
    return false;
  }
  if (TECHNICAL_TOKEN_RE.test(trimmed) && !trimmed.includes(" ")) {
    return false;
  }
  return true;
}

export function getExternalAgentPersona(agent: Agent): string {
  if (typeof agent.persona === "string" && agent.persona.trim()) {
    return agent.persona.trim();
  }
  if (!agent.workspace_files || typeof agent.workspace_files !== "object") {
    return "";
  }
  const workspaceFiles = agent.workspace_files as Record<string, unknown>;
  const identity = workspaceFiles["IDENTITY.md"];
  if (typeof identity !== "string") {
    return "";
  }
  return identity
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 5)
    .join(" ");
}

export function appendWorkflowSearchText(parts: string[], workflow: Pick<Workflow, "localizations">): void {
  const localizations = workflow.localizations;
  if (!localizations) {
    return;
  }

  [localizations.title, localizations.description, localizations.detail, localizations.category].forEach((entry) => {
    if (!entry) {
      return;
    }
    if (entry.en) parts.push(entry.en.toLowerCase());
    if (entry.zh) parts.push(entry.zh.toLowerCase());
  });

  Object.values(localizations.tags ?? {}).forEach((entry) => {
    if (entry.en) parts.push(entry.en.toLowerCase());
    if (entry.zh) parts.push(entry.zh.toLowerCase());
  });
}

export function buildCronJobLocalizationEntries(cronJobs: Record<string, CronJob[]> | undefined): Array<{
  agentName: string;
  index: number;
  field: keyof CronJobLocalizations;
  text: string;
}> {
  if (!cronJobs) {
    return [];
  }

  const entries: Array<{ agentName: string; index: number; field: keyof CronJobLocalizations; text: string }> = [];
  Object.entries(cronJobs).forEach(([agentName, jobs]) => {
    if (!Array.isArray(jobs)) {
      return;
    }
    jobs.forEach((job, index) => {
      if (typeof job.name === "string" && job.name.trim()) {
        entries.push({ agentName, index, field: "name", text: job.name });
      }
      if (typeof job.message === "string" && job.message.trim()) {
        entries.push({ agentName, index, field: "message", text: job.message });
      }
    });
  });
  return entries;
}
