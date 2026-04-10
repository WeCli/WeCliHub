import type {
  Agent,
  AgentLocalizations,
  CronJob,
  CronJobLocalizations,
  LocalizedText,
  SupportedLocale,
  Workflow,
  WorkflowLocalizations
} from "@/lib/types";
import {
  buildCronJobLocalizationEntries,
  detectTextLocale,
  getExternalAgentPersona,
  isTranslatableText,
  makeAgentLocalizationKey,
  makeCronJobLocalizationKey
} from "@/lib/workflow-localization";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY?.trim() ?? "";
const OPENAI_BASE_URL = (process.env.OPENAI_BASE_URL?.trim() || "https://api.openai.com/v1").replace(/\/+$/, "");
const TRANSLATION_MODEL =
  process.env.CLAWCROSSHUB_TRANSLATION_MODEL?.trim() ||
  process.env.FLOWHUB_TRANSLATION_MODEL?.trim() ||
  process.env.OPENAI_TRANSLATION_MODEL?.trim() ||
  "gpt-4.1-mini";
const TRANSLATION_DISABLED_ENV =
  process.env.CLAWCROSSHUB_DISABLE_AUTO_TRANSLATION ?? process.env.FLOWHUB_DISABLE_AUTO_TRANSLATION;
const TRANSLATION_DISABLED = TRANSLATION_DISABLED_ENV === "1";
const MAX_BATCH_ITEMS = 12;
const MAX_BATCH_CHARS = 6000;

type TranslationInput = {
  id: string;
  text: string;
  sourceLocale: SupportedLocale;
  kind: string;
};

type TranslationResponse = {
  items?: Array<{
    id?: string;
    en?: string;
    zh?: string;
  }>;
};

function hasTranslationConfig(): boolean {
  return !TRANSLATION_DISABLED && Boolean(OPENAI_API_KEY);
}

function buildUrl(path: string): string {
  return `${OPENAI_BASE_URL}/${path.replace(/^\/+/, "")}`;
}

function stripCodeFences(value: string): string {
  const trimmed = value.trim();
  if (!trimmed.startsWith("```")) {
    return trimmed;
  }
  return trimmed
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/, "")
    .trim();
}

function parseChatContent(data: Record<string, unknown>): string {
  const choices = Array.isArray(data.choices) ? data.choices : [];
  const firstChoice = choices[0];
  if (!firstChoice || typeof firstChoice !== "object") {
    return "";
  }
  const message = (firstChoice as Record<string, unknown>).message;
  if (!message || typeof message !== "object") {
    return "";
  }
  const content = (message as Record<string, unknown>).content;
  if (typeof content === "string") {
    return content;
  }
  if (Array.isArray(content)) {
    return content
      .map((item) => {
        if (typeof item === "string") {
          return item;
        }
        if (item && typeof item === "object" && typeof (item as Record<string, unknown>).text === "string") {
          return String((item as Record<string, unknown>).text);
        }
        return "";
      })
      .join("");
  }
  return "";
}

function normalizeLocalizedText(text: string, sourceLocale: SupportedLocale, translated: Partial<LocalizedText> | undefined): LocalizedText {
  const fallback = text.trim();
  const normalized: LocalizedText = {
    en: translated?.en?.trim() || undefined,
    zh: translated?.zh?.trim() || undefined
  };

  if (sourceLocale === "en") {
    normalized.en = normalized.en || fallback;
    normalized.zh = normalized.zh || fallback;
  } else {
    normalized.zh = normalized.zh || fallback;
    normalized.en = normalized.en || fallback;
  }

  return normalized;
}

async function translateBatch(batch: TranslationInput[]): Promise<Map<string, LocalizedText>> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 30000);

  try {
    const response = await fetch(buildUrl("/chat/completions"), {
      method: "POST",
      headers: {
        Authorization: `Bearer ${OPENAI_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: TRANSLATION_MODEL,
        temperature: 0,
        response_format: {
          type: "json_object"
        },
        messages: [
          {
            role: "system",
            content:
              "You translate workflow marketplace content between English and Simplified Chinese. Return strict JSON only in the form {\"items\":[{\"id\":\"...\",\"en\":\"...\",\"zh\":\"...\"}]}. For every item, en must be natural English and zh must be natural Simplified Chinese. Never leave English unchanged in zh, and never leave Chinese unchanged in en, unless the text is only a filename, URL, code identifier, or a brand/product name that truly must stay literal. Translate titles, descriptions, details, categories, tags, agent names, personas, and cron text. Preserve Markdown structure and formatting, but translate the human-readable words inside it."
          },
          {
            role: "user",
            content: JSON.stringify({
              items: batch.map((item) => ({
                id: item.id,
                kind: item.kind,
                sourceLocale: item.sourceLocale,
                text: item.text
              }))
            })
          }
        ]
      }),
      signal: controller.signal
    });

    if (!response.ok) {
      return new Map();
    }

    const payload = (await response.json().catch(() => ({}))) as Record<string, unknown>;
    const content = parseChatContent(payload);
    const parsed = JSON.parse(stripCodeFences(content)) as TranslationResponse;
    const byId = new Map<string, LocalizedText>();
    parsed.items?.forEach((item) => {
      if (!item?.id) {
        return;
      }
      byId.set(item.id, {
        en: item.en?.trim(),
        zh: item.zh?.trim()
      });
    });
    return byId;
  } catch {
    return new Map();
  } finally {
    clearTimeout(timeout);
  }
}

async function translateEntries(entries: TranslationInput[]): Promise<Map<string, LocalizedText>> {
  if (!entries.length || !hasTranslationConfig()) {
    return new Map();
  }

  const uniqueByText = new Map<string, TranslationInput>();
  entries.forEach((entry) => {
    if (!uniqueByText.has(entry.text)) {
      uniqueByText.set(entry.text, entry);
    }
  });

  const uniqueEntries = [...uniqueByText.values()];
  const translatedByText = new Map<string, LocalizedText>();

  for (let index = 0; index < uniqueEntries.length; ) {
    const batch: TranslationInput[] = [];
    let chars = 0;
    while (index < uniqueEntries.length && batch.length < MAX_BATCH_ITEMS) {
      const candidate = uniqueEntries[index];
      const nextChars = chars + candidate.text.length;
      if (batch.length > 0 && nextChars > MAX_BATCH_CHARS) {
        break;
      }
      batch.push(candidate);
      chars = nextChars;
      index += 1;
    }

    const translated = await translateBatch(batch);
    batch.forEach((entry) => {
      translatedByText.set(entry.text, normalizeLocalizedText(entry.text, entry.sourceLocale, translated.get(entry.id)));
    });
  }

  const result = new Map<string, LocalizedText>();
  entries.forEach((entry) => {
    const localized = translatedByText.get(entry.text);
    if (localized) {
      result.set(entry.id, localized);
    }
  });
  return result;
}

function addTranslationEntry(entries: TranslationInput[], id: string, text: string | undefined, kind: string): void {
  if (!text) {
    return;
  }
  const trimmed = text.trim();
  if (!trimmed || !isTranslatableText(trimmed)) {
    return;
  }
  const sourceLocale = detectTextLocale(trimmed);
  if (!sourceLocale) {
    return;
  }
  entries.push({
    id,
    text: trimmed,
    sourceLocale,
    kind
  });
}

function ensureAgentLocalizationContainer(
  localizations: WorkflowLocalizations,
  scope: "experts" | "internal_agents" | "external_agents",
  key: string
): AgentLocalizations {
  if (!localizations[scope]) {
    localizations[scope] = {};
  }
  const scopeMap = localizations[scope] as Record<string, AgentLocalizations>;
  if (!scopeMap[key]) {
    scopeMap[key] = {};
  }
  return scopeMap[key];
}

function getInternalAgents(workflow: Workflow): Agent[] {
  if (Array.isArray(workflow.internal_agents)) {
    return workflow.internal_agents;
  }
  if (Array.isArray(workflow.oasis_agents)) {
    return workflow.oasis_agents;
  }
  return [];
}

function getExternalAgents(workflow: Workflow): Agent[] {
  if (Array.isArray(workflow.external_agents)) {
    return workflow.external_agents;
  }
  if (Array.isArray(workflow.openclaw_agents)) {
    return workflow.openclaw_agents;
  }
  return [];
}

export async function buildWorkflowLocalizations(workflow: Workflow): Promise<WorkflowLocalizations | undefined> {
  const entries: TranslationInput[] = [];

  addTranslationEntry(entries, "workflow.title", workflow.title, "workflow_title");
  addTranslationEntry(entries, "workflow.description", workflow.description, "workflow_description");
  addTranslationEntry(entries, "workflow.detail", workflow.detail, "workflow_detail");
  addTranslationEntry(entries, "workflow.category", workflow.category, "workflow_category");

  (workflow.tags || []).forEach((tag) => {
    addTranslationEntry(entries, `workflow.tag.${tag}`, tag, "workflow_tag");
  });

  (workflow.experts_detail || []).forEach((expert) => {
    const key = makeAgentLocalizationKey(expert.name, expert.tag);
    addTranslationEntry(entries, `experts.${key}.name`, expert.name, "expert_name");
    addTranslationEntry(entries, `experts.${key}.persona`, expert.persona, "expert_persona");
  });

  getInternalAgents(workflow).forEach((agent) => {
    const key = makeAgentLocalizationKey(agent.name, agent.tag);
    addTranslationEntry(entries, `internal_agents.${key}.name`, agent.name, "internal_agent_name");
    addTranslationEntry(
      entries,
      `internal_agents.${key}.persona`,
      typeof agent.persona === "string" ? agent.persona : "",
      "internal_agent_persona"
    );
  });

  getExternalAgents(workflow).forEach((agent) => {
    const key = makeAgentLocalizationKey(agent.name, agent.tag);
    addTranslationEntry(entries, `external_agents.${key}.name`, agent.name, "external_agent_name");
    addTranslationEntry(entries, `external_agents.${key}.persona`, getExternalAgentPersona(agent), "external_agent_persona");
  });

  buildCronJobLocalizationEntries(workflow.cron_jobs).forEach((entry) => {
    addTranslationEntry(entries, `cron_jobs.${entry.agentName}.${makeCronJobLocalizationKey(entry.index)}.${entry.field}`, entry.text, `cron_${entry.field}`);
  });

  const translated = await translateEntries(entries);
  if (!translated.size) {
    return workflow.localizations;
  }

  const localizations: WorkflowLocalizations = {
    ...(workflow.localizations ?? {})
  };

  const title = translated.get("workflow.title");
  if (title) localizations.title = title;
  const description = translated.get("workflow.description");
  if (description) localizations.description = description;
  const detail = translated.get("workflow.detail");
  if (detail) localizations.detail = detail;
  const category = translated.get("workflow.category");
  if (category) localizations.category = category;

  (workflow.tags || []).forEach((tag) => {
    const localized = translated.get(`workflow.tag.${tag}`);
    if (!localized) {
      return;
    }
    if (!localizations.tags) {
      localizations.tags = {};
    }
    localizations.tags[tag] = localized;
  });

  (workflow.experts_detail || []).forEach((expert) => {
    const key = makeAgentLocalizationKey(expert.name, expert.tag);
    const name = translated.get(`experts.${key}.name`);
    const persona = translated.get(`experts.${key}.persona`);
    if (!name && !persona) {
      return;
    }
    const bucket = ensureAgentLocalizationContainer(localizations, "experts", key);
    if (name) bucket.name = name;
    if (persona) bucket.persona = persona;
  });

  getInternalAgents(workflow).forEach((agent) => {
    const key = makeAgentLocalizationKey(agent.name, agent.tag);
    const name = translated.get(`internal_agents.${key}.name`);
    const persona = translated.get(`internal_agents.${key}.persona`);
    if (!name && !persona) {
      return;
    }
    const bucket = ensureAgentLocalizationContainer(localizations, "internal_agents", key);
    if (name) bucket.name = name;
    if (persona) bucket.persona = persona;
  });

  getExternalAgents(workflow).forEach((agent) => {
    const key = makeAgentLocalizationKey(agent.name, agent.tag);
    const name = translated.get(`external_agents.${key}.name`);
    const persona = translated.get(`external_agents.${key}.persona`);
    if (!name && !persona) {
      return;
    }
    const bucket = ensureAgentLocalizationContainer(localizations, "external_agents", key);
    if (name) bucket.name = name;
    if (persona) bucket.persona = persona;
  });

  buildCronJobLocalizationEntries(workflow.cron_jobs).forEach((entry) => {
    const localized = translated.get(`cron_jobs.${entry.agentName}.${makeCronJobLocalizationKey(entry.index)}.${entry.field}`);
    if (!localized) {
      return;
    }
    if (!localizations.cron_jobs) {
      localizations.cron_jobs = {};
    }
    if (!localizations.cron_jobs[entry.agentName]) {
      localizations.cron_jobs[entry.agentName] = {};
    }
    const jobKey = makeCronJobLocalizationKey(entry.index);
    if (!localizations.cron_jobs[entry.agentName][jobKey]) {
      localizations.cron_jobs[entry.agentName][jobKey] = {};
    }
    (localizations.cron_jobs[entry.agentName][jobKey] as CronJobLocalizations)[entry.field] = localized;
  });

  return localizations;
}
