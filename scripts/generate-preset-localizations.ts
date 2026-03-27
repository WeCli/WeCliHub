import fs from "node:fs";
import path from "node:path";

import { PRESET_WORKFLOW_DEFINITIONS } from "../lib/constants";
import { buildWorkflowLocalizations } from "../lib/translation";
import type { WorkflowLocalizations } from "../lib/types";
import { getWorkflowById } from "../lib/workflow-store";

async function main() {
  const localizationsById: Record<string, WorkflowLocalizations> = {};

  for (const preset of PRESET_WORKFLOW_DEFINITIONS) {
    console.log(`Translating preset: ${preset.id}`);
    const workflow = getWorkflowById(preset.id) ?? preset;
    delete workflow.localizations;
    const localizations = await buildWorkflowLocalizations(workflow);
    if (localizations) {
      localizationsById[preset.id] = localizations;
    }
  }

  const output = `import type { WorkflowLocalizations } from "@/lib/types";

export const PRESET_WORKFLOW_LOCALIZATIONS: Record<string, WorkflowLocalizations> = ${JSON.stringify(localizationsById, null, 2)};\n`;

  const target = path.resolve(process.cwd(), "lib/preset-localizations.generated.ts");
  fs.writeFileSync(target, output, "utf-8");
  console.log(`Wrote preset localizations for ${Object.keys(localizationsById).length} workflows to ${target}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
