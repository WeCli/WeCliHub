import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import { PRESET_WORKFLOW_LOCALIZATIONS } from "@/lib/preset-localizations";
import type { Expert, Workflow } from "@/lib/types";

export const FLOWHUB_PORT = 51211;
const IS_VERCEL = process.env.VERCEL === "1";
const PROJECT_ROOT = process.cwd();
export const WORKSPACE_ROOT = IS_VERCEL ? PROJECT_ROOT : path.resolve(/* turbopackIgnore: true */ PROJECT_ROOT, "..");
const TEAMCLAW_ROOT = path.resolve(/* turbopackIgnore: true */ PROJECT_ROOT, "..", "Teamclaw");
const VERCEL_DATA_ROOT = "/tmp/flowhub";
export const HUB_META_PATH = IS_VERCEL ? path.join(VERCEL_DATA_ROOT, "hub_meta.json") : path.join(PROJECT_ROOT, "hub_meta.json");
export const STAR_RECORDS_PATH = IS_VERCEL ? path.join(VERCEL_DATA_ROOT, "star_records.json") : path.join(PROJECT_ROOT, "star_records.json");

function resolveSharedPath(...segments: string[]): string {
  const primary = path.join(WORKSPACE_ROOT, ...segments);
  if (fs.existsSync(primary)) {
    return primary;
  }

  const siblingTeamclaw = path.join(TEAMCLAW_ROOT, ...segments);
  if (fs.existsSync(siblingTeamclaw)) {
    return siblingTeamclaw;
  }

  return primary;
}

export const USER_FILES_ROOT = resolveSharedPath("data", "user_files");
export const PROMPTS_EXPERTS_PATH = resolveSharedPath("data", "prompts", "oasis_experts.json");

export const GITHUB_CLIENT_ID = process.env.GITHUB_CLIENT_ID ?? "";
export const GITHUB_CLIENT_SECRET = process.env.GITHUB_CLIENT_SECRET ?? "";
export const GITHUB_REDIRECT_URI = process.env.GITHUB_REDIRECT_URI ?? "";

export const SESSION_SECRET =
  process.env.SESSION_SECRET ??
  process.env.FLASK_SECRET_KEY ??
  crypto.createHash("sha256").update("flowhub-default-secret-key").digest("hex");

export const TAG_EMOJI: Record<string, string> = {
  creative: "🎨",
  critical: "🔍",
  data: "📊",
  synthesis: "🎯",
  economist: "📈",
  lawyer: "⚖️",
  cost_controller: "💰",
  revenue_planner: "📊",
  entrepreneur: "🚀",
  common_person: "🧑",
  manual: "📝",
  custom: "⭐",
  ml: "🤖",
  code: "💻",
  review: "📋",
  brainstorm: "💡",
  pipeline: "🔗",
  debate: "🎙️"
};

export const PRESET_WORKFLOW_DEFINITIONS: Workflow[] = [
  {
    id: "ml_code_test",
    title: "ML Code Testing Pipeline",
    description:
      "Automated machine learning code testing workflow with parallel agents analyzing why this pipeline is optimal for ML testing scenarios.",
author: "Teamclaw Hub Team",
    tags: ["ml", "code", "pipeline"],
    category: "Engineering",
    stars: 128,
    forks: 34,
    icon: "🤖",
    yaml_content: `# ML Code Testing Pipeline
version: 2
repeat: false
plan:
- id: on1
  expert: data#temp#1
- id: on2
  expert: critical#temp#1
- id: on3
  expert: creative#temp#1
- id: on4
  expert: synthesis#temp#1
edges:
- - on1
  - on3
- - on2
  - on3
- - on3
  - on4
`,
    detail:
      "This workflow leverages parallel Agent computation to analyze ML code testing. The data analyst and critical expert work simultaneously to evaluate test coverage and identify edge cases, then the creative expert synthesizes a testing strategy, and finally the synthesis advisor produces a comprehensive test report."
  },
  {
    id: "brainstorm_trio",
    title: "Creative Brainstorm Trio",
    description: "Three experts brainstorm in parallel, then a synthesis advisor summarizes the best ideas.",
author: "Teamclaw Hub Team",
    tags: ["brainstorm", "creative"],
    category: "Ideation",
    stars: 96,
    forks: 22,
    icon: "💡",
    yaml_content: `# Creative Brainstorm Trio
version: 2
repeat: true
plan:
- id: on1
  expert: creative#temp#1
- id: on2
  expert: entrepreneur#temp#1
- id: on3
  expert: common_person#temp#1
- id: on4
  expert: synthesis#temp#1
edges:
- - on1
  - on4
- - on2
  - on4
- - on3
  - on4
`,
    detail:
      "A classic brainstorming workflow: three diverse perspectives (creative thinker, entrepreneur, common person) generate ideas simultaneously, then a synthesis advisor distills the most promising concepts into actionable recommendations."
  },
  {
    id: "code_review_pipeline",
    title: "Code Review Pipeline",
    description: "Sequential code review with security, performance, and readability checks.",
author: "Teamclaw Hub Team",
    tags: ["code", "review", "pipeline"],
    category: "Engineering",
    stars: 203,
    forks: 67,
    icon: "💻",
    yaml_content: `# Code Review Pipeline
version: 2
repeat: false
plan:
- id: on1
  expert: critical#temp#1
- id: on2
  expert: data#temp#1
- id: on3
  expert: synthesis#temp#1
edges:
- - on1
  - on2
- - on2
  - on3
`,
    detail:
      "A thorough code review pipeline: the critical expert checks for bugs and security vulnerabilities, the data analyst evaluates performance metrics, and the synthesis advisor provides an overall assessment with prioritized action items."
  },
  {
    id: "business_debate",
    title: "Business Strategy Debate",
    description: "Economist, lawyer, and entrepreneur debate business strategy from different angles.",
author: "Teamclaw Hub Team",
    tags: ["debate", "brainstorm"],
    category: "Business",
    stars: 75,
    forks: 18,
    icon: "🎙️",
    yaml_content: `# Business Strategy Debate
version: 2
repeat: true
plan:
- id: on1
  expert: economist#temp#1
- id: on2
  expert: lawyer#temp#1
- id: on3
  expert: entrepreneur#temp#1
- id: on4
  expert: cost_controller#temp#1
- id: on5
  expert: revenue_planner#temp#1
- id: on6
  manual:
    author: 主持人
    content: Please summarize the key takeaways and action items from this discussion.
edges:
- - on1
  - on4
- - on2
  - on4
- - on3
  - on4
- - on4
  - on5
- - on5
  - on6
`,
    detail:
      "A comprehensive business strategy evaluation: economist, lawyer, and entrepreneur provide parallel perspectives, followed by cost-benefit analysis, revenue planning, and a final moderator summary. Perfect for evaluating new business initiatives."
  },
  {
    id: "dag_research_pipeline",
    title: "Research Analysis DAG",
    description: "DAG-based research pipeline with parallel data collection and sequential analysis.",
author: "Teamclaw Hub Team",
    tags: ["pipeline", "data"],
    category: "Research",
    stars: 64,
    forks: 15,
    icon: "📊",
    yaml_content: `# Research Analysis DAG
version: 2
repeat: false
plan:
- id: on1
  expert: data#temp#1
- id: on2
  expert: economist#temp#1
- id: on3
  expert: critical#temp#1
- id: on4
  expert: synthesis#temp#1
- id: on5
  expert: creative#temp#1
edges:
- - on1
  - on3
- - on2
  - on3
- - on3
  - on4
- - on4
  - on5
`,
    detail:
      "A DAG-based research pipeline that maximizes parallelism: two data collection agents work simultaneously, then a critical analyst reviews the combined data, a synthesis advisor draws conclusions, and finally a creative expert produces an engaging research report."
  },
  {
    id: "multi_agent_team",
    title: "Multi-Agent Collaboration Team",
    description: "A comprehensive team snapshot with internal oasis agents, OpenClaw agents with skills, and external connected agents with cron jobs.",
author: "Teamclaw Hub Team",
    tags: ["team", "snapshot", "external", "openclaw"],
    category: "Engineering",
    stars: 156,
    forks: 42,
    icon: "🌐",
    yaml_content: `# Multi-Agent Collaboration Team
version: 2
repeat: true
plan:
- id: on1
  expert: data#temp#0.8
- id: on2
  expert: critical#temp#0.6
- id: on3
  expert: creative#temp#0.9
- id: on4
  expert: synthesis#temp#0.7
edges:
- - on1
  - on2
- - on1
  - on3
- - on2
  - on4
- - on3
  - on4
`,
    detail:
      "A full-featured multi-agent team demonstrating internal Oasis agents working alongside external OpenClaw agents (with workspace files, skills, and personas) and connected external agents (with cron jobs and custom configurations). This example showcases how different agent types collaborate in a single workflow.",
    experts_detail: [
      { name: "Data Analyst", tag: "data", persona: "You are a meticulous data analyst who excels at gathering, cleaning, and interpreting complex datasets.", temperature: 0.8 },
      { name: "Critical Reviewer", tag: "critical", persona: "You are a sharp-eyed code reviewer who identifies bugs, security vulnerabilities, and performance bottlenecks.", temperature: 0.6 },
      { name: "Creative Coder", tag: "creative", persona: "You are an innovative software engineer who writes elegant, well-documented code with creative solutions.", temperature: 0.9 },
      { name: "Synthesis Advisor", tag: "synthesis", persona: "You are a strategic advisor who synthesizes multiple perspectives into actionable recommendations.", temperature: 0.7 }
    ],
    internal_agents: [
      { name: "Data Analyst", tag: "data", persona: "You are a meticulous data analyst who excels at gathering, cleaning, and interpreting complex datasets.", temperature: 0.8 },
      { name: "Critical Reviewer", tag: "critical", persona: "You are a sharp-eyed code reviewer who identifies bugs, security vulnerabilities, and performance bottlenecks.", temperature: 0.6 },
      { name: "Creative Coder", tag: "creative", persona: "You are an innovative software engineer who writes elegant, well-documented code with creative solutions.", temperature: 0.9 },
      { name: "Synthesis Advisor", tag: "synthesis", persona: "You are a strategic advisor who synthesizes multiple perspectives into actionable recommendations.", temperature: 0.7 }
    ],
    external_agents: [
      {
        name: "CodePilot",
        tag: "openclaw",
        workspace_files: {
          "IDENTITY.md": "# CodePilot\nAn advanced coding assistant powered by OpenClaw.\nSpecializes in full-stack development, code review, and automated testing.\nCapable of understanding complex codebases and generating production-ready code."
        },
        config: {
          skills: ["code_generation", "test_writing", "refactoring"],
          workspace_files: { "IDENTITY.md": "CodePilot identity" }
        }
      },
      {
        name: "DocWriter",
        tag: "openclaw",
        workspace_files: {
          "IDENTITY.md": "# DocWriter\nA documentation specialist agent.\nCreates comprehensive API docs, user guides, and technical specifications.\nSupports Markdown, OpenAPI, and JSDoc formats."
        },
        config: {
          skills: ["markdown_gen", "api_docs", "changelog"],
          workspace_files: { "IDENTITY.md": "DocWriter identity" }
        }
      },
      {
        name: "MonitorBot",
        tag: "external",
        config: {
          endpoint: "https://api.monitor-service.io/v1",
          auth_type: "bearer_token"
        }
      },
      {
        name: "SlackNotifier",
        tag: "external",
        config: {
          webhook_url: "https://hooks.slack.com/services/EXAMPLE",
          channel: "#team-alerts"
        }
      }
    ],
    skills_info: {
      CodePilot: {
        code_generation: {
          files: ["generate.py", "templates/"],
          meta: { ownerId: "openclaw", slug: "code-generation", version: "2.1.0", publishedAt: 1710000000 },
          origin: { version: 3, registry: "openclaw-hub", slug: "code-generation", installedVersion: "2.1.0", installedAt: 1710500000 }
        },
        test_writing: {
          files: ["test_gen.py"],
          meta: { ownerId: "openclaw", slug: "test-writing", version: "1.3.0", publishedAt: 1709000000 },
          origin: { version: 2, registry: "openclaw-hub", slug: "test-writing", installedVersion: "1.3.0", installedAt: 1710200000 }
        },
        refactoring: {
          files: ["refactor.py", "patterns.json"],
          meta: { ownerId: "openclaw", slug: "refactoring", version: "1.0.5", publishedAt: 1708000000 },
          origin: { version: 1, registry: "openclaw-hub", slug: "refactoring", installedVersion: "1.0.5", installedAt: 1710100000 }
        }
      },
      DocWriter: {
        markdown_gen: {
          files: ["md_writer.py"],
          meta: { ownerId: "openclaw", slug: "markdown-gen", version: "1.2.0", publishedAt: 1709500000 },
          origin: { version: 2, registry: "openclaw-hub", slug: "markdown-gen", installedVersion: "1.2.0", installedAt: 1710300000 }
        },
        api_docs: {
          files: ["openapi_gen.py", "templates/swagger.yaml"],
          meta: { ownerId: "openclaw", slug: "api-docs", version: "3.0.1", publishedAt: 1710100000 },
          origin: { version: 4, registry: "openclaw-hub", slug: "api-docs", installedVersion: "3.0.1", installedAt: 1710600000 }
        },
        changelog: {
          files: ["changelog_gen.py"],
          meta: { ownerId: "openclaw", slug: "changelog", version: "1.0.0", publishedAt: 1708500000 },
          origin: { version: 1, registry: "openclaw-hub", slug: "changelog", installedVersion: "1.0.0", installedAt: 1710000000 }
        }
      }
    },
    cron_jobs: {
      MonitorBot: [
        {
          name: "Health Check",
          enabled: true,
          scheduleKind: "interval",
          every: "5m",
          mode: "silent",
          session: "monitor_health",
          message: "Run health check on all monitored services and report anomalies."
        },
        {
          name: "Daily Report",
          enabled: true,
          scheduleKind: "cron",
          cron: "0 9 * * *",
          mode: "notify",
          session: "monitor_daily",
          message: "Generate daily monitoring summary report with uptime statistics."
        }
      ],
      SlackNotifier: [
        {
          name: "Weekly Digest",
          enabled: true,
          scheduleKind: "cron",
          cron: "0 10 * * 1",
          mode: "broadcast",
          session: "slack_weekly",
          message: "Compile and send weekly team digest to #team-alerts channel."
        },
        {
          name: "Sprint Reminder",
          enabled: false,
          scheduleKind: "cron",
          cron: "0 9 * * 5",
          mode: "notify",
          session: "slack_sprint",
          message: "Remind team about sprint review meeting."
        }
      ]
    }
  } as unknown as Workflow
];

export const PRESET_WORKFLOWS: Workflow[] = PRESET_WORKFLOW_DEFINITIONS.map((workflow) => ({
  ...workflow,
  localizations: PRESET_WORKFLOW_LOCALIZATIONS[workflow.id] ?? workflow.localizations
}));

let builtinExpertsCache: Record<string, Expert> | null = null;

export function getBuiltinExperts(): Record<string, Expert> {
  if (builtinExpertsCache) {
    return builtinExpertsCache;
  }

  const experts: Record<string, Expert> = {};
  try {
    if (fs.existsSync(PROMPTS_EXPERTS_PATH)) {
      const raw = fs.readFileSync(PROMPTS_EXPERTS_PATH, "utf-8");
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        parsed.forEach((expert) => {
          if (expert && typeof expert === "object" && typeof expert.tag === "string") {
            experts[expert.tag] = {
              name: String(expert.name_en ?? expert.name ?? expert.tag),
              tag: String(expert.tag),
              persona: String(expert.persona ?? ""),
              temperature: Number(expert.temperature ?? 0.7)
            };
          }
        });
      }
    }
  } catch {
    // fallback to empty map
  }

  builtinExpertsCache = experts;
  return experts;
}
