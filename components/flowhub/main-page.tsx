"use client";

import { Copy, Github, LogOut, Search, Settings, Sparkles, Upload, UserRound } from "lucide-react";

import { LanguageToggle } from "@/components/flowhub/language-toggle";
import { ThemeToggle } from "@/components/flowhub/theme-toggle";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import type { Locale } from "@/lib/i18n";
import { translateValue, useI18n } from "@/lib/i18n";
import { pickWorkflowTag, pickWorkflowText } from "@/lib/workflow-localization";

import { FlowhubLogo } from "@/components/flowhub/logo";
import { StableI18nText } from "@/components/flowhub/stable-i18n-text";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import type { GithubUser, SupportedLocale, Workflow } from "@/lib/types";

type WorkflowsResponse = {
  workflows: Workflow[];
  total: number;
};

type AuthResponse = {
  logged_in: boolean;
  user?: GithubUser;
};

type PublishMode = "zip" | "yaml";

type CustomAgent = {
  id: string;
  name: string;
  tag: string;
};

const AGENT_TAG_OPTIONS = [
  { value: "creative", labelKey: "tag.creative" },
  { value: "critical", labelKey: "tag.critical" },
  { value: "data", labelKey: "tag.data" },
  { value: "synthesis", labelKey: "tag.synthesis" },
  { value: "economist", labelKey: "tag.economist" },
  { value: "lawyer", labelKey: "tag.lawyer" },
  { value: "entrepreneur", labelKey: "tag.entrepreneur" },
  { value: "common_person", labelKey: "tag.common_person" },
  { value: "ml", labelKey: "tag.ml" },
  { value: "code", labelKey: "tag.code" },
  { value: "review", labelKey: "tag.review" },
  { value: "custom", labelKey: "tag.custom" }
];

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

function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "";
}

export function MainPage() {
  const { locale, setLocale, t } = useI18n();
  const currentLocale = locale as SupportedLocale;
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("");
  const [activeTag, setActiveTag] = useState("");
  const [user, setUser] = useState<GithubUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const [publishOpen, setPublishOpen] = useState(false);
  const [loginOpen, setLoginOpen] = useState(false);
  const [publishMode, setPublishMode] = useState<PublishMode>("zip");
  const [publishStatus, setPublishStatus] = useState<string>("");

  const [title, setTitle] = useState("");
  const [author, setAuthor] = useState("Anonymous");
  const [description, setDescription] = useState("");
  const [publishCategory, setPublishCategory] = useState("Engineering");
  const [tagsText, setTagsText] = useState("");
  const [yamlContent, setYamlContent] = useState("");
  const [detail, setDetail] = useState("");

  const [zipFile, setZipFile] = useState<File | null>(null);
  const [customAgents, setCustomAgents] = useState<CustomAgent[]>([]);

  const allTags = useMemo(() => {
    const set = new Set<string>();
    workflows.forEach((workflow) => {
      workflow.tags?.forEach((tag) => set.add(tag));
    });
    return [...set];
  }, [workflows]);
  const localizedTagLabels = useMemo(() => {
    const map = new Map<string, string>();
    workflows.forEach((workflow) => {
      workflow.tags?.forEach((tag) => {
        if (!map.has(tag)) {
          const fallback = translateValue(t, "tag", tag);
          map.set(tag, workflow.localizations?.tags?.[tag] ? pickWorkflowTag(workflow, tag, currentLocale) : fallback);
        }
      });
    });
    return map;
  }, [currentLocale, t, workflows]);
  const localizedCategoryLabels = useMemo(() => {
    const map = new Map<string, string>();
    workflows.forEach((workflow) => {
      if (!workflow.category || map.has(workflow.category)) {
        return;
      }
      const fallback = translateValue(t, "cat", workflow.category);
      map.set(workflow.category, pickWorkflowText(workflow, "category", fallback, currentLocale));
    });
    return map;
  }, [currentLocale, t, workflows]);
  const magicPromptText = t("main.magicPromptText");

  useEffect(() => {
    checkAuth();
    loadCategories();
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadWorkflows().catch(() => {
        // no-op
      });
    }, 250);

    return () => {
      window.clearTimeout(timer);
    };
  }, [search, category, activeTag]);

  async function checkAuth() {
    const response = await fetch("/api/auth/status");
    const data = (await response.json()) as AuthResponse;
    if (data.logged_in && data.user) {
      setUser(data.user);
      setAuthor(data.user.name || data.user.login);
    } else {
      setUser(null);
      setAuthor("Anonymous");
    }
  }

  async function loadCategories() {
    const response = await fetch("/api/categories");
    const data = (await response.json()) as string[];
    setCategories(data);
  }

  async function loadWorkflows() {
    setLoading(true);
    const url = new URL("/api/workflows", window.location.origin);
    url.searchParams.set("search", search);
    url.searchParams.set("category", category);
    if (activeTag) {
      url.searchParams.set("tag", activeTag);
    }

    const response = await fetch(url.toString());
    const data = (await response.json()) as WorkflowsResponse;
    setWorkflows(data.workflows ?? []);
    setTotal(data.total ?? 0);
    setLoading(false);
  }

  function openPublishModal() {
    if (!user) {
      setLoginOpen(true);
      return;
    }

    setPublishOpen(true);
  }

  function resetPublishForm() {
    setPublishMode("zip");
    setTitle("");
    setDescription("");
    setPublishCategory("Engineering");
    setTagsText("");
    setYamlContent("");
    setDetail("");
    setZipFile(null);
    setCustomAgents([]);
    setPublishStatus("");
    setAuthor(user?.name || user?.login || "Anonymous");
  }

  function closePublishModal() {
    setPublishOpen(false);
    resetPublishForm();
  }

  function addCustomAgent() {
    setCustomAgents((prev) => [...prev, { id: crypto.randomUUID(), name: "", tag: "" }]);
  }

  function updateCustomAgent(id: string, patch: Partial<CustomAgent>) {
    setCustomAgents((prev) => prev.map((agent) => (agent.id === id ? { ...agent, ...patch } : agent)));
  }

  function removeCustomAgent(id: string) {
    setCustomAgents((prev) => prev.filter((agent) => agent.id !== id));
  }

  async function copyToClipboard(text: string): Promise<boolean> {
    // Try modern Clipboard API first
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(text);
        return true;
      } catch {
        // fall through to legacy approach
      }
    }
    // Legacy fallback using a hidden textarea + execCommand
    try {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      ta.style.top = "-9999px";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(ta);
      return ok;
    } catch {
      return false;
    }
  }

  async function copyMagicPrompt() {
    const ok = await copyToClipboard(magicPromptText);
    if (ok) {
      window.alert(t("main.magicPromptCopied"));
    } else {
      window.alert(t("main.magicPromptCopyFail"));
    }
  }

  function buildDownloadCommand(workflow: Workflow): string {
    const origin = typeof window !== "undefined" ? window.location.origin : "https://flowhub-mu.vercel.app";
    const safeTitle = (workflow.title || "workflow")
      .toLowerCase()
      .replace(/[\s\u2014]+/g, "_")
      .replace(/[^a-z0-9_-]/g, "")
      .slice(0, 40) || "workflow";
    return `curl -L -o "team_${safeTitle}_snapshot.zip" "${origin}/api/workflows/${workflow.id}/download"`;
  }

  async function copyDownloadCommand(workflow: Workflow) {
    const ok = await copyToClipboard(buildDownloadCommand(workflow));
    if (ok) {
      setCopiedId(workflow.id);
      setTimeout(() => setCopiedId(null), 1500);
      return;
    }
    window.alert(t("main.commandCopyFail"));
  }

  async function submitPublish() {
    setPublishStatus(t("publish.publishingStatus"));
    const tags = tagsText
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);

    if (publishMode === "zip") {
      if (!zipFile) {
        setPublishStatus(`❌ ${t("publish.selectZipFirst")}`);
        return;
      }

      const formData = new FormData();
      formData.append("file", zipFile);
      formData.append("author", author || "Anonymous");
      formData.append("team_name", title);
      formData.append("description", description);
      formData.append("category", publishCategory);
      formData.append("tags", JSON.stringify(tags));

      const validAgents = customAgents.filter((agent) => agent.name.trim());
      if (validAgents.length) {
        formData.append(
          "extra_agents",
          JSON.stringify(
            validAgents.map((agent) => ({
              name: agent.name,
              tag: agent.tag
            }))
          )
        );
      }

      try {
        const response = await fetch("/api/import/zip", {
          method: "POST",
          body: formData
        });

        const result = (await response.json()) as {
          error?: string;
          count?: number;
          internal_agents_count?: number;
          external_agents_count?: number;
          experts_count?: number;
        };

        if (response.status === 401) {
          setPublishOpen(false);
          setLoginOpen(true);
          return;
        }

        if (result.error) {
          setPublishStatus(`❌ ${result.error}`);
          return;
        }

        let message = `✅ ${t("publish.publishedCount")} ${result.count ?? 0} ${t("publish.workflowCount")}`;
        const hasCounts =
          Number(result.internal_agents_count ?? 0) || Number(result.external_agents_count ?? 0) || Number(result.experts_count ?? 0);
        if (hasCounts) {
          message += ` (${result.internal_agents_count ?? 0} ${t("publish.internal")}, ${result.external_agents_count ?? 0} ${t("publish.external")}, ${result.experts_count ?? 0} ${t("publish.experts")})`;
        }
        setPublishStatus(message);

        setTimeout(() => {
          closePublishModal();
          loadWorkflows().catch(() => {
            // no-op
          });
        }, 1100);
      } catch (error) {
        setPublishStatus(`❌ ${getErrorMessage(error) || t("error.unknown")}`);
      }

      return;
    }

    if (!title.trim() || !yamlContent.trim()) {
      setPublishStatus(`❌ ${t("publish.titleAndYamlRequired")}`);
      return;
    }

    try {
      const response = await fetch("/api/workflows/publish", {
        method: "POST",
        headers: {
          "content-type": "application/json"
        },
        body: JSON.stringify({
          title,
          description,
          author,
          category: publishCategory,
          tags,
          yaml_content: yamlContent,
          detail
        })
      });
      const result = (await response.json()) as { error?: string };
      if (response.status === 401) {
        setPublishOpen(false);
        setLoginOpen(true);
        return;
      }
      if (result.error) {
        setPublishStatus(`❌ ${result.error}`);
        return;
      }
      setPublishStatus(`✅ ${t("publish.publishedSuccess")}`);
      setTimeout(() => {
        closePublishModal();
        loadWorkflows().catch(() => {
          // no-op
        });
      }, 1100);
    } catch (error) {
      setPublishStatus(`❌ ${getErrorMessage(error) || t("error.unknown")}`);
    }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-border/70 bg-background/90 backdrop-blur">
        <div className="container flex h-16 items-center gap-4">
          <Link href="/" className="text-xl font-bold text-primary">
            <FlowhubLogo />
          </Link>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
            <LanguageToggle />
            <a
              href="https://github.com/Teamclaw-hub/TeamClaw.git"
              target="_blank"
              rel="noreferrer"
              className={buttonVariants({ variant: "outline" })}
            >
              <Github className="h-4 w-4" />
              <StableI18nText translationKey="header.visitGithub" />
            </a>
            <Button variant="secondary" onClick={openPublishModal}>
              <Upload className="h-4 w-4" />
              <StableI18nText translationKey="header.publish" />
            </Button>
            {user ? (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className="h-10 gap-2">
                    {user.avatar_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={user.avatar_url} alt={user.login} className="h-6 w-6 rounded-full" />
                    ) : (
                      <UserRound className="h-4 w-4" />
                    )}
                    {user.name || user.login}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuLabel>{t("header.signedInAs")} {user.login}</DropdownMenuLabel>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <Link href={`/profile/${user.login}`}>
                      <UserRound className="mr-2 h-4 w-4" />
                      {t("header.myProfile")}
                    </Link>
                  </DropdownMenuItem>
                  {user.html_url ? (
                    <DropdownMenuItem asChild>
                      <a href={user.html_url} target="_blank" rel="noreferrer">
                        <Github className="mr-2 h-4 w-4" />
                        {t("header.githubProfile")}
                      </a>
                    </DropdownMenuItem>
                  ) : null}
                  <DropdownMenuItem onClick={() => setSettingsOpen(true)}>
                    <Settings className="mr-2 h-4 w-4" />
                    {t("header.settings")}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem asChild>
                    <a href="/auth/logout">
                      <LogOut className="mr-2 h-4 w-4" />
                      {t("header.logout")}
                    </a>
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            ) : (
              <a href="/auth/github" className={buttonVariants({ variant: "outline" })}>
                <Github className="h-4 w-4" />
                <StableI18nText translationKey="header.signIn" />
              </a>
            )}
          </div>
        </div>
      </header>

      <main className="container py-8">
        <div className="mb-6 rounded-lg border border-primary/30 bg-primary/5 p-4">
          <div className="flex items-start gap-3">
            <Sparkles className="mt-0.5 h-5 w-5 flex-shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="mb-1 text-sm font-semibold text-primary">{t("main.magicPromptTitle")}</p>
              <p className="text-sm text-muted-foreground leading-relaxed">{magicPromptText}</p>
            </div>
            <Button variant="outline" size="sm" className="flex-shrink-0" onClick={copyMagicPrompt}>
              <Sparkles className="h-3.5 w-3.5" />
              {t("main.copyPrompt")}
            </Button>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-[1fr_240px]">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("main.searchPlaceholder")}
              className="pl-9"
            />
          </div>
          <Select value={category || "__all__"} onValueChange={(value) => setCategory(value === "__all__" ? "" : value)}>
            <SelectTrigger>
              <SelectValue placeholder={t("main.allCategories")} />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all__">{t("main.allCategories")}</SelectItem>
              {categories.map((item) => (
                <SelectItem key={item} value={item}>
                  {localizedCategoryLabels.get(item) ?? translateValue(t, "cat", item)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="secondary">{total} {t("main.workflowsAvailable")}</Badge>
          <Badge variant="outline">📦 {t("main.presetsAndCommunity")}</Badge>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Button variant={activeTag ? "outline" : "default"} size="sm" onClick={() => setActiveTag("")}>
            {t("main.all")}
          </Button>
          {allTags.map((tag) => (
            <Button
              key={tag}
              variant={activeTag === tag ? "default" : "outline"}
              size="sm"
              onClick={() => setActiveTag(tag)}
            >
              {localizedTagLabels.get(tag) ?? tag}
            </Button>
          ))}
        </div>

        {loading ? (
          <div className="py-24 text-center text-muted-foreground">{t("main.loading")}</div>
        ) : workflows.length === 0 ? (
          <div className="py-24 text-center text-muted-foreground">{t("main.noWorkflows")}</div>
        ) : (
          <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {workflows.map((workflow) => {
              const workflowTitle = pickWorkflowText(workflow, "title", workflow.title, currentLocale);
              const workflowDescription = pickWorkflowText(workflow, "description", workflow.description, currentLocale);

              return (
                <Card key={workflow.id} className="group relative h-full transition-all hover:border-primary/60 hover:-translate-y-0.5 hover:shadow-lg">
                  <Link href={`/workflow/${workflow.id}`} className="block">
                    {workflow.is_dag ? (
                      <div className="absolute right-3 top-3 rounded px-2 py-0.5 text-[11px] font-semibold bg-accent/15 text-accent border border-accent/30">
                        DAG
                      </div>
                    ) : null}
                    <CardHeader className="pb-3">
                      <div className="flex items-start gap-3">
                        <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-lg bg-secondary border border-border text-2xl">
                          {workflow.icon || "📦"}
                        </div>
                        <div className="min-w-0 flex-1">
                          <CardTitle className="line-clamp-1 text-base">{workflowTitle}</CardTitle>
                          <CardDescription className="mt-0.5">
                            {t("main.by")} {workflow.author} · {workflow.source === "preset" ? t("main.official") : t("main.community")}
                          </CardDescription>
                        </div>
                      </div>
                    </CardHeader>
                    <CardContent className="pb-3">
                      <p className="line-clamp-2 text-sm text-muted-foreground">{workflowDescription}</p>
                      <div className="mt-3 flex flex-wrap gap-1">
                        {(workflow.tags || []).map((tag) => (
                          <Badge key={tag} variant="outline">
                            {workflow.localizations?.tags?.[tag]
                              ? pickWorkflowTag(workflow, tag, currentLocale)
                              : translateValue(t, "tag", tag)}
                          </Badge>
                        ))}
                      </div>
                    </CardContent>
                  </Link>
                  <CardFooter className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3 border-t border-border pt-3 text-xs text-muted-foreground">
                    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-4 gap-y-2">
                      <span className="inline-flex items-center gap-1">⭐ {workflow.stars || 0}</span>
                      <span className="inline-flex items-center gap-1">🔀 {workflow.forks || 0}</span>
                      <span className="inline-flex items-center gap-1">📊 {workflow.steps || 0} {t("main.steps")}</span>
                      <span className="inline-flex items-center gap-1">{workflow.repeat ? `🔁 ${t("main.repeat")}` : `▶️ ${t("main.once")}`}</span>
                      <span className="inline-flex min-w-0 items-center gap-1">{typeIcons(workflow.step_types)}</span>
                    </div>
                    <button
                      type="button"
                      className="inline-flex self-start whitespace-nowrap items-center gap-1 rounded-md border border-border px-2 py-0.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary hover:border-primary/40"
                      title={t("main.copyDownloadCommand")}
                      onClick={() => copyDownloadCommand(workflow)}
                    >
                      <Copy className="h-3 w-3" />
                      {copiedId === workflow.id ? t("main.commandCopied") : t("main.copyDownloadCommand")}
                    </button>
                  </CardFooter>
                </Card>
              );
            })}
          </div>
        )}
      </main>

      <Dialog
        open={publishOpen}
        onOpenChange={(open) => {
          setPublishOpen(open);
          if (!open) {
            resetPublishForm();
          }
        }}
      >
        <DialogContent className="max-h-[90vh] overflow-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{t("publish.title")}</DialogTitle>
            <DialogDescription>{t("publish.description")}</DialogDescription>
          </DialogHeader>

          <Tabs value={publishMode} onValueChange={(value) => setPublishMode(value as PublishMode)}>
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="zip">📦 {t("publish.uploadZip")}</TabsTrigger>
              <TabsTrigger value="yaml">📝 {t("publish.writeYaml")}</TabsTrigger>
            </TabsList>

            <div className="mt-4 grid gap-3">
              <div className="grid gap-2">
                <Label htmlFor="pub-title">{t("publish.titleLabel")}</Label>
                <Input id="pub-title" value={title} onChange={(event) => setTitle(event.target.value)} placeholder={t("publish.titlePlaceholder")} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="pub-author">{t("publish.authorLabel")}</Label>
                <Input id="pub-author" value={author} onChange={(event) => setAuthor(event.target.value)} />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="pub-description">{t("publish.descriptionLabel")}</Label>
                <Input
                  id="pub-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder={t("publish.descPlaceholder")}
                />
              </div>
              <div className="grid gap-2">
                <Label>{t("publish.categoryLabel")}</Label>
                <Select value={publishCategory} onValueChange={setPublishCategory}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {[
                      "Engineering",
                      "Ideation",
                      "Business",
                      "Research",
                      "Community",
                      "Imported"
                    ].map((item) => (
                      <SelectItem key={item} value={item}>
                        {translateValue(t, "cat", item)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="grid gap-2">
                <Label htmlFor="pub-tags">{t("publish.tagsLabel")}</Label>
                <Input id="pub-tags" value={tagsText} onChange={(event) => setTagsText(event.target.value)} placeholder={t("publish.tagsPlaceholder")} />
              </div>
            </div>

            <TabsContent value="zip" className="space-y-4">
              <div className="grid gap-2">
                <Label htmlFor="zip-file">{t("publish.teamSnapshot")}</Label>
                <Input
                  id="zip-file"
                  type="file"
                  accept=".zip"
                  onChange={(event) => {
                    setZipFile(event.target.files?.[0] ?? null);
                  }}
                />
                {zipFile ? <p className="text-xs text-muted-foreground">✅ {zipFile.name} ({(zipFile.size / 1024).toFixed(1)} KB)</p> : null}
              </div>

              <div className="rounded-md border p-3">
                <div className="mb-2 flex items-center justify-between">
                  <Label>{t("publish.customAgents")}</Label>
                  <Button type="button" size="sm" variant="outline" onClick={addCustomAgent}>
                    {t("publish.addAgent")}
                  </Button>
                </div>
                <div className="space-y-2">
                  {customAgents.map((agent) => (
                    <div key={agent.id} className="grid gap-2 sm:grid-cols-[1fr_220px_auto]">
                      <Input
                        placeholder={t("publish.agentNamePlaceholder")}
                        value={agent.name}
                        onChange={(event) => updateCustomAgent(agent.id, { name: event.target.value })}
                      />
                      <Select value={agent.tag || "__none__"} onValueChange={(value) => updateCustomAgent(agent.id, { tag: value === "__none__" ? "" : value })}>
                        <SelectTrigger>
                          <SelectValue placeholder={t("publish.selectTagPlaceholder")} />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="__none__">{t("publish.selectTagPlaceholder")}</SelectItem>
                          {AGENT_TAG_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {t(option.labelKey)}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <Button type="button" variant="ghost" onClick={() => removeCustomAgent(agent.id)}>
                        {t("publish.remove")}
                      </Button>
                    </div>
                  ))}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="yaml" className="space-y-3">
              <div className="grid gap-2">
                <Label htmlFor="yaml-content">{t("publish.yamlContent")} *</Label>
                <Textarea
                  id="yaml-content"
                  value={yamlContent}
                  onChange={(event) => setYamlContent(event.target.value)}
                  className="min-h-44 font-mono text-xs"
                  placeholder={"version: 2\nrepeat: false\nplan:\n- id: on1\n  expert: creative#temp#1"}
                />
              </div>
              <div className="grid gap-2">
                <Label htmlFor="yaml-detail">{t("publish.detailedDescription")}</Label>
                <Textarea
                  id="yaml-detail"
                  value={detail}
                  onChange={(event) => setDetail(event.target.value)}
                  placeholder={t("publish.yamlPlaceholder")}
                />
              </div>
            </TabsContent>
          </Tabs>

          {publishStatus ? <p className="text-sm text-muted-foreground">{publishStatus}</p> : null}

          <DialogFooter>
            <Button variant="outline" onClick={closePublishModal}>
              {t("publish.cancel")}
            </Button>
            <Button onClick={submitPublish}>{t("publish.publishBtn")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={loginOpen} onOpenChange={setLoginOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("login.title")}</DialogTitle>
            <DialogDescription>
              {t("login.description")}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <a href="/auth/github" className={buttonVariants({ variant: "default" })}>
              <Github className="h-4 w-4" />
              {t("login.signInGithub")}
            </a>
            <Button variant="outline" onClick={() => setLoginOpen(false)}>
              {t("login.continueGuest")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={settingsOpen} onOpenChange={setSettingsOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>⚙️ {t("settings.title")}</DialogTitle>
            <DialogDescription>{t("settings.description")}</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label>{t("settings.language")}</Label>
              <Select value={locale} onValueChange={(value) => setLocale(value as Locale)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="en">{t("settings.english")}</SelectItem>
                  <SelectItem value="zh">{t("settings.chinese")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSettingsOpen(false)}>
              {t("settings.close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
