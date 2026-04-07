import fs from "node:fs";
import path from "node:path";

import { UI_TRANSLATION_SEED } from "../lib/ui-translation-seed";

const OPENAI_API_KEY = process.env.OPENAI_API_KEY?.trim() ?? "";
const OPENAI_BASE_URL = (process.env.OPENAI_BASE_URL?.trim() || "https://api.openai.com/v1").replace(/\/+$/, "");
const TRANSLATION_MODEL =
  process.env.TEAMCLAWHUB_TRANSLATION_MODEL?.trim() ||
  process.env.FLOWHUB_TRANSLATION_MODEL?.trim() ||
  process.env.OPENAI_TRANSLATION_MODEL?.trim() ||
  "gpt-4.1-mini";

type TranslationResponse = {
  items?: Array<{
    id?: string;
    en?: string;
    zh?: string;
  }>;
};

function buildUrl(resourcePath: string): string {
  return `${OPENAI_BASE_URL}/${resourcePath.replace(/^\/+/, "")}`;
}

function stripCodeFences(value: string): string {
  const trimmed = value.trim();
  if (!trimmed.startsWith("```")) {
    return trimmed;
  }
  return trimmed.replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "").trim();
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
        if (typeof item === "string") return item;
        if (item && typeof item === "object" && typeof (item as Record<string, unknown>).text === "string") {
          return String((item as Record<string, unknown>).text);
        }
        return "";
      })
      .join("");
  }
  return "";
}

async function main() {
  if (!OPENAI_API_KEY) {
    throw new Error("OPENAI_API_KEY is required to generate UI translations.");
  }

  const items = Object.entries(UI_TRANSLATION_SEED).map(([id, text]) => ({ id, text }));
  const response = await fetch(buildUrl("/chat/completions"), {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: TRANSLATION_MODEL,
      temperature: 0,
      response_format: { type: "json_object" },
      messages: [
        {
          role: "system",
          content:
            "You translate product UI copy between English and Simplified Chinese. Return strict JSON only in the form {\"items\":[{\"id\":\"...\",\"en\":\"...\",\"zh\":\"...\"}]}. Keep the tone concise, natural, and product-ready. Preserve placeholders, punctuation, and UI intent."
        },
        {
          role: "user",
          content: JSON.stringify({ items })
        }
      ]
    })
  });

  if (!response.ok) {
    throw new Error(`Translation request failed with ${response.status}`);
  }

  const payload = (await response.json()) as Record<string, unknown>;
  const content = parseChatContent(payload);
  const parsed = JSON.parse(stripCodeFences(content)) as TranslationResponse;

  const localizations: Record<string, { en?: string; zh?: string }> = {};
  parsed.items?.forEach((item) => {
    if (!item?.id) {
      return;
    }
    localizations[item.id] = {
      en: item.en?.trim() || UI_TRANSLATION_SEED[item.id],
      zh: item.zh?.trim() || undefined
    };
  });

  const output = `type UiLocale = "en" | "zh";

export const UI_TRANSLATIONS_GENERATED: Record<string, Partial<Record<UiLocale, string>>> = ${JSON.stringify(localizations, null, 2)};\n`;

  const target = path.resolve(process.cwd(), "lib/ui-translations.generated.ts");
  fs.writeFileSync(target, output, "utf-8");
  console.log(`Wrote UI translations for ${Object.keys(localizations).length} keys to ${target}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
