"use client";

import { Copy } from "lucide-react";
import Link from "next/link";

import type { SupportedLocale, Workflow } from "@/lib/types";
import { translateValue } from "@/lib/i18n";
import { pickWorkflowTag, pickWorkflowText } from "@/lib/workflow-localization";

import { PretextText } from "@/components/clawcrosshub/pretext-text";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";

type WorkflowCardProps = {
  copied: boolean;
  currentLocale: SupportedLocale;
  detailHref?: string;
  onCopyDownload: (workflow: Workflow) => void;
  onImportToClawcross?: (workflow: Workflow) => void;
  preferImport?: boolean;
  t: (key: string) => string;
  workflow: Workflow;
};

function typeIcons(stepTypes?: string[]): string {
  if (!stepTypes?.length) {
    return "";
  }

  const counts = new Map<string, number>();

  stepTypes.forEach((type) => {
    counts.set(type, (counts.get(type) ?? 0) + 1);
  });

  return [...counts.entries()]
    .map(([type, count]) => {
      if (type === "expert") return `👤 x${count}`;
      if (type === "parallel") return `⚡ x${count}`;
      if (type === "manual") return `📝 x${count}`;
      if (type === "all_experts") return `👥 x${count}`;
      return `• x${count}`;
    })
    .join(" ");
}

export function WorkflowCard({ copied, currentLocale, detailHref, onCopyDownload, onImportToClawcross, preferImport = false, t, workflow }: WorkflowCardProps) {
  const workflowTitle = pickWorkflowText(workflow, "title", workflow.title, currentLocale);
  const workflowDescription = pickWorkflowText(workflow, "description", workflow.description, currentLocale);

  return (
    <Card className="group relative flex h-full flex-col overflow-hidden transition-all hover:-translate-y-0.5 hover:border-primary/60 hover:shadow-lg">
      <Link href={detailHref || `/workflow/${workflow.id}`} className="flex flex-1 flex-col">
        {workflow.is_dag ? (
          <div className="absolute right-3 top-3 rounded px-2 py-0.5 text-[11px] font-semibold border border-accent/30 bg-accent/15 text-accent">
            DAG
          </div>
        ) : null}

        <CardHeader className="pb-4">
          <div className="flex items-start gap-3">
            <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-xl border border-border bg-secondary text-2xl shadow-sm">
              {workflow.icon || "📦"}
            </div>
            <div className="min-w-0 flex-1">
              <PretextText
                as="h3"
                text={workflowTitle}
                balance
                idealLineCount={2}
                maxLines={2}
                reserveLines={2}
                className="text-base font-semibold leading-[1.12] text-foreground"
              />
              <p className="mt-1 text-sm text-muted-foreground">
                {t("main.by")} {workflow.author} · {workflow.source === "preset" ? t("main.official") : t("main.community")}
              </p>
            </div>
          </div>
        </CardHeader>

        <CardContent className="flex flex-1 flex-col pb-4">
          <PretextText
            as="p"
            text={workflowDescription}
            maxLines={3}
            reserveLines={3}
            className="text-sm leading-5 text-muted-foreground"
          />

          <div className="mt-4 flex flex-wrap gap-1.5">
            {(workflow.tags || []).map((tag) => (
              <Badge key={tag} variant="outline" className="rounded-full">
                {workflow.localizations?.tags?.[tag]
                  ? pickWorkflowTag(workflow, tag, currentLocale)
                  : translateValue(t, "tag", tag)}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Link>

      <CardFooter className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3 border-t border-border/80 pt-3 text-xs text-muted-foreground">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-2">
          <span className="inline-flex items-center gap-1">⭐ {workflow.stars || 0}</span>
          <span className="inline-flex items-center gap-1">🔀 {workflow.forks || 0}</span>
          <span className="inline-flex items-center gap-1">📊 {workflow.steps || 0} {t("main.steps")}</span>
          <span className="inline-flex items-center gap-1">{workflow.repeat ? `🔁 ${t("main.repeat")}` : `▶️ ${t("main.once")}`}</span>
          <span className="inline-flex min-w-0 items-center gap-1">{typeIcons(workflow.step_types)}</span>
        </div>

        <button
          type="button"
          className="inline-flex self-start items-center gap-1 whitespace-nowrap rounded-md border border-border px-2 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
          title={preferImport ? t("main.importToClawcross") : t("main.copyDownloadCommand")}
          onClick={() => {
            if (preferImport && onImportToClawcross) {
              onImportToClawcross(workflow);
              return;
            }
            onCopyDownload(workflow);
          }}
        >
          <Copy className="h-3 w-3" />
          {preferImport ? t("main.importToClawcross") : (copied ? t("main.commandCopied") : t("main.copyDownloadCommand"))}
        </button>
      </CardFooter>
    </Card>
  );
}
