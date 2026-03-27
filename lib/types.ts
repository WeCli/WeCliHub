export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };
export type SupportedLocale = "en" | "zh";

export interface LocalizedText {
  en?: string;
  zh?: string;
}

export interface AgentLocalizations {
  name?: LocalizedText;
  persona?: LocalizedText;
}

export interface CronJobLocalizations {
  name?: LocalizedText;
  message?: LocalizedText;
}

export interface WorkflowLocalizations {
  title?: LocalizedText;
  description?: LocalizedText;
  detail?: LocalizedText;
  category?: LocalizedText;
  tags?: Record<string, LocalizedText>;
  experts?: Record<string, AgentLocalizations>;
  internal_agents?: Record<string, AgentLocalizations>;
  external_agents?: Record<string, AgentLocalizations>;
  cron_jobs?: Record<string, Record<string, CronJobLocalizations>>;
}

export interface GithubUser {
  login: string;
  name: string;
  avatar_url: string;
  id?: number;
  html_url?: string;
}

export interface Expert {
  name: string;
  tag: string;
  persona: string;
  temperature: number;
  [key: string]: JsonValue | undefined;
}

export interface Agent {
  name: string;
  tag?: string;
  session?: string;
  persona?: string;
  temperature?: number;
  config?: JsonValue;
  workspace_files?: JsonValue;
  global_name?: string;
  [key: string]: JsonValue | undefined;
}

export interface Workflow {
  id: string;
  title: string;
  description: string;
  author: string;
  tags: string[];
  category: string;
  stars: number;
  forks: number;
  icon: string;
  yaml_content: string;
  detail: string;
  published_at?: string;
  source?: "preset" | "community" | "user";
  steps?: number;
  is_dag?: boolean;
  repeat?: boolean;
  step_types?: string[];
  experts?: string[] | Expert[];
  experts_detail?: Expert[];
  github_user?: string;
  internal_agents?: Agent[];
  external_agents?: Agent[] | Record<string, JsonValue>;
  oasis_agents?: Agent[];
  openclaw_agents?: Agent[];
  skills_data?: Record<string, string>;
  skills_info?: Record<string, Record<string, SkillInfo>>;
  cron_jobs?: Record<string, CronJob[]>;
  yaml_files?: Record<string, string>;
  localizations?: WorkflowLocalizations;
}

export interface SkillInfo {
  files?: string[];
  meta?: {
    ownerId?: string;
    slug?: string;
    version?: string;
    publishedAt?: number;
    [key: string]: JsonValue | undefined;
  };
  origin?: {
    version?: number;
    registry?: string;
    slug?: string;
    installedVersion?: string;
    installedAt?: number;
    [key: string]: JsonValue | undefined;
  };
}

export interface CronJob {
  name?: string;
  enabled?: boolean;
  scheduleKind?: string;
  cron?: string;
  at?: string | number;
  every?: string;
  mode?: string;
  session?: string;
  message?: string;
  [key: string]: JsonValue | undefined;
}

export interface HubMeta {
  workflows: Workflow[];
  version: number;
}
