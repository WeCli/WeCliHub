"""
ClawCrossHub — Community Workflow Marketplace
==========================================
A GitHub-style community platform for browsing, sharing, and selecting
OASIS workflow templates. Users can discover pre-built workflows, preview
their structure, and import them into the visual orchestrator.

Run:
  python clawcrosshub.py
  Open http://127.0.0.1:51211
"""

import io
import json
import os
import sys
import tempfile
import time
import uuid
import zipfile
from datetime import datetime
from typing import Optional

import hashlib
import requests as http_requests

import yaml
from flask import Flask, Response, jsonify, render_template_string, request, abort, redirect, session
from werkzeug.datastructures import FileStorage

# ── Path setup ──
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

# ── Constants ──
HUB_META_PATH = os.path.join(_THIS_DIR, "hub_meta.json")
USER_FILES_ROOT = os.path.join(_PROJECT_ROOT, "data", "user_files")
UPLOAD_DIR = os.path.join(_THIS_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Default port
CLAWCROSSHUB_PORT = 51211

# Import _yaml_to_layout_data from visual system for canvas rendering
try:
    from mcp_oasis import _yaml_to_layout_data
except ImportError:
    _yaml_to_layout_data = None

# Tag → emoji mapping (reuse from visual)
TAG_EMOJI = {
    "creative": "🎨", "critical": "🔍", "data": "📊", "synthesis": "🎯",
    "economist": "📈", "lawyer": "⚖️", "cost_controller": "💰",
    "revenue_planner": "📊", "entrepreneur": "🚀", "common_person": "🧑",
    "manual": "📝", "custom": "⭐", "ml": "🤖", "code": "💻",
    "review": "📋", "brainstorm": "💡", "pipeline": "🔗", "debate": "🎙️",
}

# Built-in expert tag → full expert metadata (loaded from prompts or hardcoded)
# Used to auto-generate oasis_experts.json / internal_agents.json from YAML plans
_PROMPTS_EXPERTS_PATH = os.path.join(_PROJECT_ROOT, "data", "prompts", "oasis_experts.json")
BUILTIN_EXPERTS: dict = {}   # tag → {name, tag, persona, temperature}
try:
    with open(_PROMPTS_EXPERTS_PATH, "r", encoding="utf-8") as _f:
        for _exp in json.load(_f):
            BUILTIN_EXPERTS[_exp["tag"]] = _exp
except Exception:
    pass


def _extract_experts_from_yaml(yaml_content: str) -> list:
    """Parse YAML plan and extract unique expert tags.
    Expert format in YAML: "tag#temp#value" or "tag#oasis#name"
    Returns list of {name, tag, persona, temperature} dicts (Clawcross format).
    Also returns a list of internal agent dicts [{name, tag}].
    """
    try:
        parsed = yaml.safe_load(yaml_content)
    except Exception:
        return [], []
    if not isinstance(parsed, dict):
        return [], []
    plan = parsed.get("plan", [])
    if not isinstance(plan, list):
        return [], []

    seen_tags = set()
    experts = []
    internal_agents = []

    def _process_expert_str(expert_str):
        """Process a single expert string like 'creative#temp#1'"""
        if not isinstance(expert_str, str):
            return
        parts = expert_str.split("#")
        tag = parts[0].strip()
        if not tag or tag in seen_tags:
            return
        seen_tags.add(tag)

        # Look up in built-in experts
        builtin = BUILTIN_EXPERTS.get(tag)
        if builtin:
            experts.append({
                "name": builtin.get("name", tag),
                "tag": tag,
                "persona": builtin.get("persona", ""),
                "temperature": builtin.get("temperature", 0.7),
            })
            internal_agents.append({
                "name": builtin.get("name", tag),
                "tag": tag,
            })
        else:
            # Custom / unknown tag — still include with defaults
            experts.append({
                "name": tag,
                "tag": tag,
                "persona": "",
                "temperature": 0.7,
            })
            internal_agents.append({
                "name": tag,
                "tag": tag,
            })

    for step in plan:
        if isinstance(step, dict):
            # Handle: {expert: "tag#temp#1"} or {id: ..., expert: "tag#temp#1"}
            expert_val = step.get("expert")
            if expert_val:
                _process_expert_str(expert_val)
            # Handle: {parallel: ["tag1#temp#1", "tag2#temp#1"]}
            par = step.get("parallel")
            if isinstance(par, list):
                for p in par:
                    if isinstance(p, str):
                        _process_expert_str(p)
                    elif isinstance(p, dict):
                        _process_expert_str(p.get("expert", ""))
            # Handle: {manual: {author: ..., content: ...}} — skip manual nodes

    return experts, internal_agents


# Preset workflow templates (built-in showcases)
PRESET_WORKFLOWS = [
    {
        "id": "ml_code_test",
        "title": "ML Code Testing Pipeline",
        "description": "Automated machine learning code testing workflow with parallel agents analyzing why this pipeline is optimal for ML testing scenarios.",
"author": "ClawCrossHub Team",
        "tags": ["ml", "code", "pipeline"],
        "category": "Engineering",
        "stars": 128,
        "forks": 34,
        "icon": "🤖",
        "yaml_content": """# ML Code Testing Pipeline
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
""",
        "detail": "This workflow leverages parallel Agent computation to analyze ML code testing. The data analyst and critical expert work simultaneously to evaluate test coverage and identify edge cases, then the creative expert synthesizes a testing strategy, and finally the synthesis advisor produces a comprehensive test report.",
    },
    {
        "id": "brainstorm_trio",
        "title": "Creative Brainstorm Trio",
        "description": "Three experts brainstorm in parallel, then a synthesis advisor summarizes the best ideas.",
"author": "ClawCrossHub Team",
        "tags": ["brainstorm", "creative"],
        "category": "Ideation",
        "stars": 96,
        "forks": 22,
        "icon": "💡",
        "yaml_content": """# Creative Brainstorm Trio
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
""",
        "detail": "A classic brainstorming workflow: three diverse perspectives (creative thinker, entrepreneur, common person) generate ideas simultaneously, then a synthesis advisor distills the most promising concepts into actionable recommendations.",
    },
    {
        "id": "code_review_pipeline",
        "title": "Code Review Pipeline",
        "description": "Sequential code review with security, performance, and readability checks.",
"author": "ClawCrossHub Team",
        "tags": ["code", "review", "pipeline"],
        "category": "Engineering",
        "stars": 203,
        "forks": 67,
        "icon": "💻",
        "yaml_content": """# Code Review Pipeline
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
""",
        "detail": "A thorough code review pipeline: the critical expert checks for bugs and security vulnerabilities, the data analyst evaluates performance metrics, and the synthesis advisor provides an overall assessment with prioritized action items.",
    },
    {
        "id": "business_debate",
        "title": "Business Strategy Debate",
        "description": "Economist, lawyer, and entrepreneur debate business strategy from different angles.",
"author": "ClawCrossHub Team",
        "tags": ["debate", "brainstorm"],
        "category": "Business",
        "stars": 75,
        "forks": 18,
        "icon": "🎙️",
        "yaml_content": """# Business Strategy Debate
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
""",
        "detail": "A comprehensive business strategy evaluation: economist, lawyer, and entrepreneur provide parallel perspectives, followed by cost-benefit analysis, revenue planning, and a final moderator summary. Perfect for evaluating new business initiatives.",
    },
    {
        "id": "dag_research_pipeline",
        "title": "Research Analysis DAG",
        "description": "DAG-based research pipeline with parallel data collection and sequential analysis.",
"author": "ClawCrossHub Team",
        "tags": ["pipeline", "data"],
        "category": "Research",
        "stars": 64,
        "forks": 15,
        "icon": "📊",
        "yaml_content": """# Research Analysis DAG
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
""",
        "detail": "A DAG-based research pipeline that maximizes parallelism: two data collection agents work simultaneously, then a critical analyst reviews the combined data, a synthesis advisor draws conclusions, and finally a creative expert produces an engaging research report.",
    },
    {
        "id": "auto_research_claw",
        "title": "🧬 AutoResearchClaw — 23-Stage Research Pipeline",
        "description": "Fully autonomous 23-stage research pipeline that turns a single research idea into a conference-ready paper (NeurIPS/ICML/ICLR). Features real literature search, self-healing experiments, 4-layer citation verification, and quality gates with human-in-the-loop approval.",
"author": "ClawCrossHub Team",
        "tags": ["research", "pipeline", "ml", "code", "review"],
        "category": "Research",
        "stars": 512,
        "forks": 147,
        "icon": "🧬",
        "yaml_content": """# AutoResearchClaw — 23-Stage Autonomous Research Pipeline
# A → Scoping | B → Literature | C → Synthesis | D → Design | E → Execution | F → Analysis | G → Writing | H → Finalization
version: 2
repeat: false
plan:
  # ─── Phase A: Scoping (Stages 1-2) ───
  - id: begin
    manual:
      author: begin
      content: "🚀 AutoResearchClaw Pipeline Initiated — Starting autonomous research workflow"
  - id: s1_topic_init
    expert: "synthesis#temp#0.3"
  - id: s2_decompose
    expert: "critical#temp#0.4"

  # ─── Phase B: Literature (Stages 3-6) ───
  - id: s3_search_strategy
    expert: "data#temp#0.3"
  - id: s4_lit_collect
    parallel:
      - expert: "data#temp#0.2"
      - expert: "economist#temp#0.2"
  - id: s5_lit_screen
    expert: "critical#temp#0.3"
  - id: s5_gate
    selector: true
    expert: "synthesis#temp#0.2"
  - id: s6_knowledge_extract
    expert: "data#temp#0.4"

  # ─── Phase C: Synthesis (Stages 7-8) ───
  - id: s7_knowledge_synth
    expert: "synthesis#temp#0.5"
  - id: s8_hypothesis
    parallel:
      - expert: "creative#temp#0.8"
      - expert: "critical#temp#0.5"
      - expert: "entrepreneur#temp#0.6"

  # ─── Phase D: Design (Stages 9-11) ───
  - id: s9_experiment_design
    expert: "data#temp#0.4"
  - id: s9_gate
    selector: true
    expert: "critical#temp#0.2"
  - id: s10_code_gen
    expert: "creative#temp#0.5"
  - id: s11_resource_plan
    expert: "economist#temp#0.3"

  # ─── Phase E: Execution (Stages 12-13) ───
  - id: s12_experiment_run
    expert: "data#temp#0.2"
  - id: s13_refine
    expert: "critical#temp#0.4"

  # ─── Phase F: Analysis (Stages 14-15) ───
  - id: s14_result_analysis
    parallel:
      - expert: "data#temp#0.3"
      - expert: "economist#temp#0.4"
  - id: s15_research_decision
    selector: true
    expert: "synthesis#temp#0.3"

  # ─── Phase G: Writing (Stages 16-19) ───
  - id: s16_outline
    expert: "synthesis#temp#0.5"
  - id: s17_draft
    expert: "creative#temp#0.6"
  - id: s18_peer_review
    parallel:
      - expert: "critical#temp#0.5"
      - expert: "data#temp#0.4"
  - id: s19_revision
    expert: "creative#temp#0.4"

  # ─── Phase H: Finalization (Stages 20-23) ───
  - id: s20_quality_gate
    selector: true
    expert: "critical#temp#0.2"
  - id: s21_knowledge_archive
    expert: "synthesis#temp#0.3"
  - id: s22_latex_export
    expert: "creative#temp#0.3"
  - id: s23_citation_verify
    expert: "critical#temp#0.2"
  - id: finish
    manual:
      author: bend
      content: "🏁 AutoResearchClaw Pipeline Complete — Conference-ready paper generated"

edges:
  # Phase A: Scoping
  - [begin, s1_topic_init]
  - [s1_topic_init, s2_decompose]
  # Phase B: Literature
  - [s2_decompose, s3_search_strategy]
  - [s3_search_strategy, s4_lit_collect]
  - [s4_lit_collect, s5_lit_screen]
  - [s5_lit_screen, s5_gate]
  - [s5_gate, s6_knowledge_extract]
  # Phase C: Synthesis
  - [s6_knowledge_extract, s7_knowledge_synth]
  - [s7_knowledge_synth, s8_hypothesis]
  # Phase D: Design
  - [s8_hypothesis, s9_experiment_design]
  - [s9_experiment_design, s9_gate]
  - [s9_gate, s10_code_gen]
  - [s10_code_gen, s11_resource_plan]
  # Phase E: Execution
  - [s11_resource_plan, s12_experiment_run]
  - [s12_experiment_run, s13_refine]
  # Phase F: Analysis
  - [s13_refine, s14_result_analysis]
  - [s14_result_analysis, s15_research_decision]
  # Phase G: Writing
  - [s15_research_decision, s16_outline]
  - [s16_outline, s17_draft]
  - [s17_draft, s18_peer_review]
  - [s18_peer_review, s19_revision]
  # Phase H: Finalization
  - [s19_revision, s20_quality_gate]
  - [s20_quality_gate, s21_knowledge_archive]
  - [s21_knowledge_archive, s22_latex_export]
  - [s22_latex_export, s23_citation_verify]
  - [s23_citation_verify, finish]

selector_edges:
  # Stage 5 Gate: Literature screening approval
  - source: s5_gate
    choices:
      "1": s6_knowledge_extract
      "2": s4_lit_collect
  # Stage 9 Gate: Experiment design approval
  - source: s9_gate
    choices:
      "1": s10_code_gen
      "2": s9_experiment_design
  # Stage 15: Research decision (PROCEED / REFINE / PIVOT)
  - source: s15_research_decision
    choices:
      "1": s16_outline
      "2": s12_experiment_run
      "3": s8_hypothesis
  # Stage 20: Final quality gate
  - source: s20_quality_gate
    choices:
      "1": s21_knowledge_archive
      "2": s19_revision
""",
        "detail": """AutoResearchClaw is a fully autonomous 23-stage research pipeline that turns a single research idea into a conference-ready paper with minimal human intervention.

🔬 PIPELINE OVERVIEW (8 Phases, 23 Stages):

━━━ Phase A: Scoping (Stages 1-2) ━━━
  Stage 1 — Topic Initialization: Parses and formalizes the research idea
  Stage 2 — Problem Decomposition: Breaks the topic into sub-problems and hypotheses

━━━ Phase B: Literature (Stages 3-6) ━━━
  Stage 3 — Search Strategy: Plans multi-source literature search (OpenAlex, Semantic Scholar, arXiv)
  Stage 4 — Literature Collection: Parallel agents collect papers from different sources
  Stage 5 — Literature Screening: Quality filter with approval gate (⛔ GATE)
  Stage 6 — Knowledge Extraction: Extracts key findings, methods, and gaps

━━━ Phase C: Synthesis (Stages 7-8) ━━━
  Stage 7 — Knowledge Synthesis: Builds unified knowledge graph from extracted information
  Stage 8 — Hypothesis Generation: Multi-agent debate (creative + critical + entrepreneur) generates novel hypotheses

━━━ Phase D: Design (Stages 9-11) ━━━
  Stage 9 — Experiment Design: Creates detailed experiment plan
  Stage 9 Gate — Design Approval: Quality check on experiment design (⛔ GATE)
  Stage 10 — Code Generation: Generates experiment code (hardware-aware: GPU/MPS/CPU)
  Stage 11 — Resource Planning: Estimates compute, data, and time requirements

━━━ Phase E: Execution (Stages 12-13) ━━━
  Stage 12 — Experiment Execution: Runs experiments in self-healing sandbox
  Stage 13 — Iterative Refinement: Analyzes failures and retries with fixes

━━━ Phase F: Analysis (Stages 14-15) ━━━
  Stage 14 — Result Analysis: Parallel statistical and economic analysis of results
  Stage 15 — Research Decision: PROCEED → writing / REFINE → re-run experiments / PIVOT → new hypothesis (⛔ GATE)

━━━ Phase G: Writing (Stages 16-19) ━━━
  Stage 16 — Paper Outline: Structures the paper (NeurIPS/ICML/ICLR format)
  Stage 17 — Draft Writing: Generates full paper draft (5,000-6,500 words)
  Stage 18 — Peer Review: Parallel review by critical analyst and data expert
  Stage 19 — Revision: Incorporates review feedback

━━━ Phase H: Finalization (Stages 20-23) ━━━
  Stage 20 — Quality Gate: Final approval checkpoint (⛔ GATE)
  Stage 21 — Knowledge Archive: Saves lessons learned (MetaClaw integration)
  Stage 22 — LaTeX Export: Generates conference-grade LaTeX + BibTeX
  Stage 23 — Citation Verification: 4-layer citation verification pipeline

🎯 KEY FEATURES:
  📚 Real literature from OpenAlex, Semantic Scholar & arXiv (no hallucinated references)
  🖥️ Hardware-aware execution (auto-detects GPU/MPS/CPU)
  🧪 Self-healing sandbox experiments with iterative refinement
  📝 Conference-grade LaTeX output (NeurIPS/ICML/ICLR templates)
  🔍 4-layer citation verification
  🧬 Self-learning lessons (with optional MetaClaw integration)
  🚦 Quality gates with human-in-the-loop approval

📦 OUTPUT: Full paper (5,000-6,500 words), LaTeX, BibTeX, experiment code, charts, peer reviews""",
    },
]


# ── Hub metadata store ──
def _load_hub_meta() -> dict:
    """Load the hub metadata (community-published workflows)."""
    if os.path.isfile(HUB_META_PATH):
        try:
            with open(HUB_META_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"workflows": [], "version": 1}


def _save_hub_meta(meta: dict):
    """Persist hub metadata to disk."""
    with open(HUB_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _scan_user_workflows() -> list[dict]:
    """Scan all user directories for published workflows."""
    results = []
    if not os.path.isdir(USER_FILES_ROOT):
        return results
    for user_dir in os.listdir(USER_FILES_ROOT):
        yaml_dir = os.path.join(USER_FILES_ROOT, user_dir, "oasis", "yaml")
        if not os.path.isdir(yaml_dir):
            continue
        for fname in os.listdir(yaml_dir):
            if not fname.endswith((".yaml", ".yml")):
                continue
            fpath = os.path.join(yaml_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    content = f.read()
                # Extract description from first comment line
                desc = ""
                for line in content.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        desc = stripped.lstrip("# ")
                        break
                    elif stripped:
                        break
                results.append({
                    "file": fname,
                    "user": user_dir,
                    "description": desc,
                    "path": fpath,
                    "yaml_content": content,
                    "modified": os.path.getmtime(fpath),
                })
            except Exception:
                continue
    return results


def _parse_yaml_plan_summary(yaml_str: str) -> dict:
    """Parse YAML and return a summary of the plan structure."""
    try:
        data = yaml.safe_load(yaml_str)
        if not isinstance(data, dict) or "plan" not in data:
            return {"steps": 0, "types": [], "is_dag": False, "repeat": False}
        plan = data.get("plan", [])
        repeat = data.get("repeat", False)
        version = data.get("version", 1)
        has_edges = "edges" in data
        is_dag = has_edges or any(isinstance(s, dict) and ("id" in s or "depends_on" in s) for s in plan)
        step_types = []
        expert_names = []
        for step in plan:
            if isinstance(step, dict):
                if step.get("selector"):
                    step_types.append("selector")
                    if "expert" in step:
                        expert_names.append(step["expert"].split("#")[0])
                elif "expert" in step:
                    step_types.append("expert")
                    expert_names.append(step["expert"].split("#")[0])
                elif "parallel" in step:
                    step_types.append("parallel")
                    for p in step["parallel"]:
                        if isinstance(p, str):
                            expert_names.append(p.split("#")[0])
                        elif isinstance(p, dict) and "expert" in p:
                            expert_names.append(p["expert"].split("#")[0])
                elif "all_experts" in step:
                    step_types.append("all_experts")
                elif "manual" in step:
                    step_types.append("manual")
        return {
            "steps": len(plan),
            "types": step_types,
            "is_dag": is_dag,
            "repeat": repeat,
            "experts": list(set(expert_names)),
        }
    except Exception:
        return {"steps": 0, "types": [], "is_dag": False, "repeat": False}


# ── GitHub OAuth Configuration ──
# Set these via environment variables or fill in directly
GITHUB_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "Ov23liONMlTPW8yuCwZ2")
GITHUB_CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET", "63c8dc542c40ff540e7ee664bd89d69cbbb0eabe")
GITHUB_REDIRECT_URI = os.environ.get("GITHUB_REDIRECT_URI", "http://127.0.0.1:51211/auth/github/callback")


# ── Flask App ──
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", hashlib.sha256(b"clawcrosshub-default-secret-key").hexdigest())


# ── GitHub OAuth Routes ──
@app.route("/auth/github")
def auth_github():
    """Redirect user to GitHub OAuth authorization page."""
    if not GITHUB_CLIENT_ID:
        return jsonify({"error": "GitHub OAuth not configured. Set GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET environment variables."}), 500
    github_auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_REDIRECT_URI}"
        f"&scope=read:user"
    )
    return redirect(github_auth_url)


@app.route("/auth/github/callback")
def auth_github_callback():
    """Handle GitHub OAuth callback, exchange code for access token and fetch user info."""
    code = request.args.get("code")
    if not code:
        return "<h2>Authorization failed: no code provided.</h2><a href='/'>Back to ClawCrossHub</a>", 400

    # Exchange code for access token
    token_resp = http_requests.post(
        "https://github.com/login/oauth/access_token",
        json={
            "client_id": GITHUB_CLIENT_ID,
            "client_secret": GITHUB_CLIENT_SECRET,
            "code": code,
            "redirect_uri": GITHUB_REDIRECT_URI,
        },
        headers={"Accept": "application/json"},
        timeout=15,
    )
    token_data = token_resp.json()
    access_token = token_data.get("access_token")
    if not access_token:
        return f"<h2>Failed to get access token.</h2><pre>{token_data}</pre><a href='/'>Back</a>", 400

    # Fetch user info from GitHub API
    user_resp = http_requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=10,
    )
    user_data = user_resp.json()

    # Store user info in session
    session["github_user"] = {
        "login": user_data.get("login", "unknown"),
        "name": user_data.get("name", user_data.get("login", "GitHub User")),
        "avatar_url": user_data.get("avatar_url", ""),
        "id": user_data.get("id"),
        "html_url": user_data.get("html_url", ""),
    }
    return redirect("/")


@app.route("/auth/logout")
def auth_logout():
    """Clear session and log out."""
    session.pop("github_user", None)
    return redirect("/")


@app.route("/api/auth/status")
def api_auth_status():
    """Return current authentication status and user info."""
    user = session.get("github_user")
    if user:
        return jsonify({"logged_in": True, "user": user})
    return jsonify({"logged_in": False, "github_client_id": GITHUB_CLIENT_ID or None})


def _require_github_login():
    """Check if user is logged in via GitHub. Returns error response or None."""
    user = session.get("github_user")
    if not user:
        return jsonify({"error": "GitHub login required to publish/upload workflows. Please log in first."}), 401
    return None


@app.route("/")
def index():
"""Serve the ClawCrossHub main page."""
    return render_template_string(MAIN_HTML)


@app.route("/workflow/<workflow_id>")
def workflow_detail(workflow_id):
    """Serve the workflow detail page."""
    return render_template_string(DETAIL_HTML, workflow_id=workflow_id)


@app.route("/api/workflows", methods=["GET"])
def api_list_workflows():
    """List all available workflows (presets + community)."""
    search = request.args.get("search", "").lower()
    category = request.args.get("category", "")
    tag = request.args.get("tag", "")

    all_workflows = []

    # 1. Add preset workflows
    for pw in PRESET_WORKFLOWS:
        summary = _parse_yaml_plan_summary(pw["yaml_content"])
        item = {
            "id": pw["id"],
            "title": pw["title"],
            "description": pw["description"],
            "author": pw["author"],
            "tags": pw["tags"],
            "category": pw["category"],
            "stars": pw["stars"],
            "forks": pw["forks"],
            "icon": pw["icon"],
            "source": "preset",
            "steps": summary["steps"],
            "is_dag": summary["is_dag"],
            "repeat": summary["repeat"],
            "step_types": summary["types"],
            "experts": summary.get("experts", []),
        }
        all_workflows.append(item)

    # 2. Add community-published workflows from hub_meta
    meta = _load_hub_meta()
    for cw in meta.get("workflows", []):
        summary = _parse_yaml_plan_summary(cw.get("yaml_content", ""))
        item = {
            "id": cw["id"],
            "title": cw.get("title", cw.get("file", "Untitled")),
            "description": cw.get("description", ""),
            "author": cw.get("author", "Community"),
            "tags": cw.get("tags", []),
            "category": cw.get("category", "Community"),
            "stars": cw.get("stars", 0),
            "forks": cw.get("forks", 0),
            "icon": cw.get("icon", "📦"),
            "source": "community",
            "steps": summary["steps"],
            "is_dag": summary["is_dag"],
            "repeat": summary["repeat"],
            "step_types": summary["types"],
            "experts": summary.get("experts", []),
        }
        all_workflows.append(item)

    # 3. Add user file system workflows (not yet published)
    scanned = _scan_user_workflows()
    published_ids = {w["id"] for w in all_workflows}
    for uw in scanned:
        wid = f"user_{uw['user']}_{uw['file'].replace('.yaml','').replace('.yml','')}"
        if wid in published_ids:
            continue
        summary = _parse_yaml_plan_summary(uw["yaml_content"])
        item = {
            "id": wid,
            "title": uw["file"].replace(".yaml", "").replace(".yml", "").replace("_", " ").title(),
            "description": uw["description"] or "User workflow",
            "author": uw["user"],
            "tags": [],
            "category": "User",
            "stars": 0,
            "forks": 0,
            "icon": "📄",
            "source": "user",
            "steps": summary["steps"],
            "is_dag": summary["is_dag"],
            "repeat": summary["repeat"],
            "step_types": summary["types"],
            "experts": summary.get("experts", []),
        }
        all_workflows.append(item)

    # Apply filters
    if search:
        all_workflows = [
            w for w in all_workflows
            if search in w["title"].lower()
            or search in w["description"].lower()
            or search in w["author"].lower()
            or any(search in t for t in w["tags"])
        ]
    if category:
        all_workflows = [w for w in all_workflows if w["category"].lower() == category.lower()]
    if tag:
        all_workflows = [w for w in all_workflows if tag in w["tags"]]

    return jsonify({"workflows": all_workflows, "total": len(all_workflows)})


@app.route("/api/workflows/<workflow_id>", methods=["GET"])
def api_get_workflow(workflow_id):
    """Get detailed info for a single workflow."""
    # Check presets
    for pw in PRESET_WORKFLOWS:
        if pw["id"] == workflow_id:
            summary = _parse_yaml_plan_summary(pw["yaml_content"])
            # Build experts_detail with full persona info from BUILTIN_EXPERTS
            experts_detail = []
            for tag in summary.get("experts", []):
                if tag in BUILTIN_EXPERTS:
                    experts_detail.append(BUILTIN_EXPERTS[tag])
                else:
                    experts_detail.append({"name": tag, "tag": tag, "persona": "", "temperature": 0.7})
            return jsonify({
                **pw,
                "source": "preset",
                "steps": summary["steps"],
                "is_dag": summary["is_dag"],
                "step_types": summary["types"],
                "experts": summary.get("experts", []),
                "experts_detail": experts_detail,
            })

    # Check community
    meta = _load_hub_meta()
    for cw in meta.get("workflows", []):
        if cw["id"] == workflow_id:
            summary = _parse_yaml_plan_summary(cw.get("yaml_content", ""))
            # Preserve full expert objects from imported data (oasis_experts.json)
            stored_experts = cw.get("experts", [])
            # Build experts_detail: prefer stored rich objects, fallback to BUILTIN
            experts_detail = []
            if stored_experts and isinstance(stored_experts[0], dict):
                experts_detail = stored_experts
            else:
                for tag in summary.get("experts", []):
                    if tag in BUILTIN_EXPERTS:
                        experts_detail.append(BUILTIN_EXPERTS[tag])
                    else:
                        experts_detail.append({"name": tag, "tag": tag, "persona": "", "temperature": 0.7})
            return jsonify({
                **cw,
                "source": "community",
                "steps": summary["steps"],
                "is_dag": summary["is_dag"],
                "step_types": summary["types"],
                "experts": summary.get("experts", []),
                "experts_detail": experts_detail,
            })

    # Check user files
    if workflow_id.startswith("user_"):
        parts = workflow_id.split("_", 2)
        if len(parts) >= 3:
            user = parts[1]
            fname_base = parts[2]
            yaml_dir = os.path.join(USER_FILES_ROOT, user, "oasis", "yaml")
            for ext in (".yaml", ".yml"):
                fpath = os.path.join(yaml_dir, fname_base + ext)
                if os.path.isfile(fpath):
                    with open(fpath, "r", encoding="utf-8") as f:
                        content = f.read()
                    desc = ""
                    for line in content.splitlines():
                        stripped = line.strip()
                        if stripped.startswith("#"):
                            desc = stripped.lstrip("# ")
                            break
                        elif stripped:
                            break
                    summary = _parse_yaml_plan_summary(content)
                    return jsonify({
                        "id": workflow_id,
                        "title": fname_base.replace("_", " ").title(),
                        "description": desc or "User workflow",
                        "author": user,
                        "tags": [],
                        "category": "User",
                        "stars": 0,
                        "forks": 0,
                        "icon": "📄",
                        "yaml_content": content,
                        "detail": f"Workflow created by user '{user}'.",
                        "source": "user",
                        "steps": summary["steps"],
                        "is_dag": summary["is_dag"],
                        "step_types": summary["types"],
                        "experts": summary.get("experts", []),
                    })
    abort(404)


@app.route("/api/workflows/<workflow_id>/star", methods=["POST"])
def api_star_workflow(workflow_id):
    """Toggle star on a workflow."""
    meta = _load_hub_meta()
    for cw in meta.get("workflows", []):
        if cw["id"] == workflow_id:
            cw["stars"] = cw.get("stars", 0) + 1
            _save_hub_meta(meta)
            return jsonify({"stars": cw["stars"]})
    # For presets, just acknowledge (not persisted)
    for pw in PRESET_WORKFLOWS:
        if pw["id"] == workflow_id:
            pw["stars"] = pw.get("stars", 0) + 1
            return jsonify({"stars": pw["stars"]})
    abort(404)


@app.route("/api/workflows/publish", methods=["POST"])
def api_publish_workflow():
    """Publish a workflow to the community hub. Requires GitHub login."""
    auth_err = _require_github_login()
    if auth_err:
        return auth_err
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    required = ["title", "yaml_content"]
    for field in required:
        if not data.get(field):
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # Validate YAML
    try:
        parsed = yaml.safe_load(data["yaml_content"])
        if not isinstance(parsed, dict) or "plan" not in parsed:
            return jsonify({"error": "YAML must contain 'plan' key"}), 400
    except yaml.YAMLError as e:
        return jsonify({"error": f"Invalid YAML: {e}"}), 400

    meta = _load_hub_meta()
    new_workflow = {
        "id": f"community_{uuid.uuid4().hex[:8]}",
        "title": data["title"],
        "description": data.get("description", ""),
        "author": data.get("author", "Anonymous"),
        "tags": data.get("tags", []),
        "category": data.get("category", "Community"),
        "stars": 0,
        "forks": 0,
        "icon": data.get("icon", "📦"),
        "yaml_content": data["yaml_content"],
        "detail": data.get("detail", ""),
        "published_at": datetime.now().isoformat(),
    }
    # Attach GitHub user info as author metadata
    gh_user = session.get("github_user", {})
    if gh_user:
        new_workflow["author"] = gh_user.get("name") or gh_user.get("login", data.get("author", "Anonymous"))
        new_workflow["github_user"] = gh_user.get("login", "")
    meta["workflows"].append(new_workflow)
    _save_hub_meta(meta)
    return jsonify({"status": "ok", "id": new_workflow["id"]})


@app.route("/api/categories", methods=["GET"])
def api_categories():
    """List all available categories."""
    cats = set()
    for pw in PRESET_WORKFLOWS:
        cats.add(pw["category"])
    meta = _load_hub_meta()
    for cw in meta.get("workflows", []):
        cats.add(cw.get("category", "Community"))
    cats.add("User")
    return jsonify(sorted(cats))


@app.route("/api/workflows/<workflow_id>/layout", methods=["GET"])
def api_get_workflow_layout(workflow_id):
    """Get visual canvas layout data for a workflow (same format as visual app)."""
    if _yaml_to_layout_data is None:
        return jsonify({"error": "Layout engine not available"}), 503

    # Find the workflow's YAML content
    yaml_content = None
    for pw in PRESET_WORKFLOWS:
        if pw["id"] == workflow_id:
            yaml_content = pw["yaml_content"]
            break
    if not yaml_content:
        meta = _load_hub_meta()
        for cw in meta.get("workflows", []):
            if cw["id"] == workflow_id:
                yaml_content = cw.get("yaml_content", "")
                break
    if not yaml_content:
        return jsonify({"error": "Workflow not found"}), 404

    try:
        layout = _yaml_to_layout_data(yaml_content)
        return jsonify(layout)
    except Exception as e:
        return jsonify({"error": f"Layout conversion failed: {e}"}), 500


def _do_import_zip(file, *, author="Imported", team_name="", extra_agents=None,
                   description="", category="", tags=None):
    """Core logic for importing a Clawcross team snapshot ZIP file.
    Called by both api_import_zip (direct upload) and api_import_json (backward-compat wrapper).
    Supports optional description, category, tags from the unified publish modal.
    """
    if extra_agents is None:
        extra_agents = []
    if tags is None:
        tags = []

    try:
        zip_buffer = io.BytesIO(file.read() if hasattr(file, 'read') else file.stream.read())
        imported = []
        internal_agents = []   # from internal_agents.json (Clawcross format)
        external_agents = []   # from external_agents.json (OpenClaw agents)
        experts_list = []      # from oasis_experts.json
        cron_jobs = {}         # from cron_jobs.json
        skills_info = {}       # parsed from skills/ directory structure

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            # First pass: read JSON metadata files and skills data
            skills_data = {}  # {rel_path: base64_content} for skills/ files
            import base64 as _b64
            for info in zf.infolist():
                # Preserve skills/ folder files as base64 for re-download
                if info.filename.startswith('skills/') and not info.is_dir():
                    try:
                        raw_bytes = zf.read(info.filename)
                        skills_data[info.filename] = _b64.b64encode(raw_bytes).decode('ascii')
                    except Exception:
                        pass
                fname = os.path.basename(info.filename)
                if fname == "internal_agents.json":
                    raw = json.loads(zf.read(info.filename))
                    if isinstance(raw, list):
                        # Strip session fields (private, will be regenerated)
                        internal_agents = [
                            {k: v for k, v in a.items() if k != "session"}
                            for a in raw if isinstance(a, dict)
                        ]
                elif fname == "external_agents.json":
                    raw = json.loads(zf.read(info.filename))
                    if isinstance(raw, list):
                        external_agents = raw
                elif fname == "oasis_experts.json":
                    raw = json.loads(zf.read(info.filename))
                    if isinstance(raw, list):
                        experts_list = raw
                elif fname == "cron_jobs.json":
                    raw = json.loads(zf.read(info.filename))
                    if isinstance(raw, dict):
                        cron_jobs = raw
                    elif isinstance(raw, list):
                        cron_jobs = {"_global": raw}

            # Parse skills/ directory: group by agent name
            for info in zf.infolist():
                if info.filename.startswith('skills/') and not info.is_dir():
                    parts = info.filename.split('/')
                    # Structure: skills/<agent_name>/<skill_name>/...
                    if len(parts) >= 3:
                        agent_name = parts[1]
                        skill_name = parts[2]
                        fname_part = parts[-1]
                        if agent_name not in skills_info:
                            skills_info[agent_name] = {}
                        if skill_name not in skills_info[agent_name]:
                            skills_info[agent_name][skill_name] = {"files": [], "meta": {}, "origin": {}}
                        skills_info[agent_name][skill_name]["files"].append(info.filename)
                        if fname_part == '_meta.json':
                            try:
                                meta_raw = json.loads(zf.read(info.filename))
                                skills_info[agent_name][skill_name]["meta"] = meta_raw
                            except Exception:
                                pass
                        if fname_part == 'origin.json':
                            try:
                                origin_raw = json.loads(zf.read(info.filename))
                                skills_info[agent_name][skill_name]["origin"] = origin_raw
                            except Exception:
                                pass

            # Merge extra custom agents defined by the uploader
            if extra_agents:
                for ea in extra_agents:
                    if isinstance(ea, dict) and ea.get("name"):
                        # Add to internal_agents if not already present
                        existing_names = {a.get("name") for a in internal_agents}
                        if ea["name"] not in existing_names:
                            internal_agents.append({
                                "name": ea["name"],
                                "tag": ea.get("tag", ""),
                            })

            # Second pass: import YAML workflows (may be at root or in oasis/yaml/)
            meta = _load_hub_meta()
            yaml_found = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if not info.filename.endswith(('.yaml', '.yml')):
                    continue
                yaml_content = zf.read(info.filename).decode('utf-8')
                try:
                    parsed = yaml.safe_load(yaml_content)
                    if not isinstance(parsed, dict) or 'plan' not in parsed:
                        continue
                except Exception:
                    continue
                yaml_found.append((info.filename, yaml_content))

            # Build combined agent list for display
            all_agents_display = []
            for a in internal_agents:
                all_agents_display.append(a)
            for a in external_agents:
                if a.get("tag") == "openclaw":
                    all_agents_display.append(a)

            # Build team title
            zip_filename = getattr(file, 'filename', None) or "upload.zip"
            zip_stem = os.path.splitext(os.path.basename(zip_filename))[0]
            base_title = team_name or zip_stem.replace("_", " ").title()

            for rel_path, yaml_content in yaml_found:
                fname = os.path.basename(rel_path)
                title = fname.replace('.yaml', '').replace('.yml', '').replace('-', ' ').replace('_', ' ').title()

                auto_desc = f"Team snapshot with {len(internal_agents)} agents, {len(external_agents)} OpenClaw agents"
                merged_tags = list(set((tags or []) + ["team", "snapshot"]))
                new_wf = {
                    "id": f"community_{uuid.uuid4().hex[:8]}",
                    "title": f"{base_title} — {title}" if len(yaml_found) > 1 else base_title,
                    "description": description or auto_desc,
                    "author": author,
                    "tags": merged_tags,
                    "category": category or "Community",
                    "stars": 0,
                    "forks": 0,
                    "icon": "📦",
                    "yaml_content": yaml_content,
                    "detail": "",
                    "published_at": datetime.now().isoformat(),
                    # Store in Clawcross-compatible fields
                    "internal_agents": internal_agents,
                    "external_agents": external_agents,
                    "oasis_agents": internal_agents,      # alias for display
                    "openclaw_agents": external_agents,    # alias for display
                    "experts": experts_list,
                    "skills_data": skills_data,            # preserved for re-download
                    "cron_jobs": cron_jobs,                # from cron_jobs.json
                    "skills_info": skills_info,            # parsed skills metadata per agent
                }
                meta["workflows"].append(new_wf)
                imported.append(new_wf["title"])

            # If no YAML but has agent data, create a summary entry
            if not yaml_found and (internal_agents or external_agents or experts_list):
                agent_names = [a.get("name", "?") for a in all_agents_display]
                auto_desc2 = f"Agents: {', '.join(agent_names[:5])}{'...' if len(agent_names)>5 else ''}"
                merged_tags2 = list(set((tags or []) + ["team", "snapshot"]))
                new_wf = {
                    "id": f"community_{uuid.uuid4().hex[:8]}",
                    "title": base_title or f"Team Snapshot ({len(agent_names)} agents)",
                    "description": description or auto_desc2,
                    "author": author,
                    "tags": merged_tags2,
                    "category": category or "Community",
                    "stars": 0,
                    "forks": 0,
                    "icon": "👥",
                    "yaml_content": "",
                    "detail": "",
                    "published_at": datetime.now().isoformat(),
                    "internal_agents": internal_agents,
                    "external_agents": external_agents,
                    "oasis_agents": internal_agents,
                    "openclaw_agents": external_agents,
                    "experts": experts_list,
                    "skills_data": skills_data,            # preserved for re-download
                    "cron_jobs": cron_jobs,                # from cron_jobs.json
                    "skills_info": skills_info,            # parsed skills metadata per agent
                }
                meta["workflows"].append(new_wf)
                imported.append(new_wf["title"])

            _save_hub_meta(meta)

        return jsonify({
            "status": "ok",
            "imported": imported,
            "count": len(imported),
            "internal_agents_count": len(internal_agents),
            "external_agents_count": len(external_agents),
            "experts_count": len(experts_list),
            "extra_agents_added": len(extra_agents) if extra_agents else 0,
        })
    except zipfile.BadZipFile:
        return jsonify({"error": "Invalid ZIP file"}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/import/zip", methods=["POST"])
def api_import_zip():
    """Import a Clawcross team snapshot ZIP file. Requires GitHub login.
    Clawcross ZIP format:
      - internal_agents.json   [{name, tag}]  (session stripped)
      - external_agents.json   [{name, tag:"openclaw", config, workspace_files}] (global_name stripped)
      - oasis_experts.json     [{name, tag, persona, temperature}]
      - oasis/yaml/*.yaml      OASIS workflow YAML files
      - skills/<agent>/        OpenClaw agent skill folders (preserved for re-download)
      - skills/_managed/       Managed skill folders (preserved for re-download)
    Also supports the optional extra_agents field from the import form,
    allowing the uploader to define custom agent names and capabilities.
    """
    auth_err = _require_github_login()
    if auth_err:
        return auth_err
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    file = request.files['file']
    if not file.filename or not file.filename.endswith('.zip'):
        return jsonify({"error": "File must be a .zip"}), 400

    author = request.form.get("author", "Imported")
    team_name = request.form.get("team_name", "")  # optional team display name
    description = request.form.get("description", "")
    category = request.form.get("category", "")

    # Parse tags (may be JSON array string)
    tags_raw = request.form.get("tags", "[]")
    try:
        pub_tags = json.loads(tags_raw)
        if not isinstance(pub_tags, list):
            pub_tags = []
    except Exception:
        pub_tags = []

    # Parse extra custom agents defined by the uploader
    extra_agents_raw = request.form.get("extra_agents", "[]")
    try:
        extra_agents = json.loads(extra_agents_raw)
        if not isinstance(extra_agents, list):
            extra_agents = []
    except Exception:
        extra_agents = []

    return _do_import_zip(file, author=author, team_name=team_name,
                          extra_agents=extra_agents, description=description,
                          category=category, tags=pub_tags)


@app.route("/api/import/json", methods=["POST"])
def api_import_json():
    """(Deprecated) Backward-compatible JSON import endpoint.
    Wraps the uploaded JSON into a temporary ZIP and delegates to api_import_zip logic.
    New callers should pack JSON files into a ZIP and use /api/import/zip directly.
    """
    auth_err = _require_github_login()
    if auth_err:
        return auth_err
    if 'file' not in request.files:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No file or JSON body provided. Please upload a .zip file instead."}), 400
        raw_bytes = json.dumps(data).encode("utf-8")
        fname = data.get("_filename", "upload.json")
    else:
        file = request.files['file']
        if not file.filename:
            return jsonify({"error": "No file uploaded"}), 400
        raw_bytes = file.read()
        fname = file.filename

    # Auto-detect JSON filename → proper Clawcross naming
    base = os.path.basename(fname).lower()
    if "external" in base or "openclaw" in base:
        inner_name = "external_agents.json"
    elif "expert" in base:
        inner_name = "oasis_experts.json"
    else:
        inner_name = "internal_agents.json"

    # Wrap JSON into a temporary in-memory ZIP and forward to the ZIP import logic
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(inner_name, raw_bytes)
        zip_buffer.seek(0)

        # Build a synthetic file-like object for the ZIP import handler
        synthetic_file = FileStorage(
            stream=zip_buffer,
            filename=fname.replace('.json', '.zip'),
            content_type='application/zip',
        )
        # Temporarily inject the synthetic ZIP file into request.files
        # and call the core import logic directly
        author = request.form.get("author", "Imported") if 'file' in request.files else "Imported"
        return _do_import_zip(synthetic_file, author=author, team_name="", extra_agents=[])
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/workflows/<workflow_id>/download", methods=["GET"])
def api_download_zip(workflow_id):
    """Download a workflow as a Clawcross-compatible team snapshot ZIP.
    Output format matches front.py's /teams/snapshot/download exactly:
      - internal_agents.json   [{name, tag}]  (session stripped)
      - external_agents.json   [{name, tag, config, workspace_files}] (global_name stripped)
      - oasis_experts.json     [{name, tag, persona, temperature}]
      - oasis/yaml/<name>.yaml  Workflow YAML files
      - skills/<agent>/        OpenClaw agent skill folders (if available)
      - skills/_managed/       Managed skill folders (if available)
    This ZIP can be uploaded directly to Clawcross via /teams/snapshot/upload.
    """
    # Find workflow
    wf = None
    for pw in PRESET_WORKFLOWS:
        if pw["id"] == workflow_id:
            wf = pw
            break
    if not wf:
        meta = _load_hub_meta()
        for cw in meta.get("workflows", []):
            if cw["id"] == workflow_id:
                wf = cw
                break
    if not wf:
        abort(404)

    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # --- 0. Auto-extract agents from YAML if no explicit metadata ---
            yaml_content = wf.get("yaml_content", "")
            yaml_experts, yaml_internal = [], []
            if yaml_content:
                yaml_experts, yaml_internal = _extract_experts_from_yaml(yaml_content)

            # --- 1. JSON metadata files (same order as Clawcross front.py) ---
            json_files_written = set()

            # internal_agents.json — strip session field (private)
            internal = wf.get("internal_agents", wf.get("oasis_agents", []))
            if not (isinstance(internal, list) and internal):
                # Fallback: auto-generate from YAML plan
                internal = yaml_internal
            if isinstance(internal, list) and internal:
                cleaned = []
                for a in internal:
                    if isinstance(a, dict):
                        c = dict(a)
                        c.pop("session", None)
                        cleaned.append(c)
                if cleaned:
                    zf.writestr("internal_agents.json", json.dumps(cleaned, indent=2, ensure_ascii=False))
                    json_files_written.add("internal_agents.json")

            # external_agents.json — strip global_name (regenerated on restore)
            external = wf.get("external_agents", wf.get("openclaw_agents", []))
            if isinstance(external, list) and external:
                cleaned = []
                for a in external:
                    if isinstance(a, dict):
                        c = dict(a)
                        c.pop("global_name", None)
                        c.pop("session", None)
                        cleaned.append(c)
                if cleaned:
                    zf.writestr("external_agents.json", json.dumps(cleaned, indent=2, ensure_ascii=False))
                    json_files_written.add("external_agents.json")
            # Also support legacy dict format (from old imports)
            elif isinstance(external, dict) and external:
                ext_list = []
                for name, data in external.items():
                    entry = {"name": name, "tag": "openclaw"}
                    if isinstance(data, dict):
                        entry["config"] = data.get("config", {})
                        entry["workspace_files"] = data.get("workspace_files", {})
                    ext_list.append(entry)
                if ext_list:
                    zf.writestr("external_agents.json", json.dumps(ext_list, indent=2, ensure_ascii=False))
                    json_files_written.add("external_agents.json")

            # oasis_experts.json
            experts = wf.get("experts", [])
            if not (isinstance(experts, list) and experts):
                # Fallback: auto-generate from YAML plan
                experts = yaml_experts
            if isinstance(experts, list) and experts:
                zf.writestr("oasis_experts.json", json.dumps(experts, indent=2, ensure_ascii=False))
                json_files_written.add("oasis_experts.json")

            # cron_jobs.json
            cron_jobs_data = wf.get("cron_jobs", {})
            if isinstance(cron_jobs_data, dict) and cron_jobs_data:
                zf.writestr("cron_jobs.json", json.dumps(cron_jobs_data, indent=2, ensure_ascii=False))
                json_files_written.add("cron_jobs.json")

            # --- 2. YAML files in oasis/yaml/ subdirectory (Clawcross convention) ---
            if yaml_content:
                safe_name = wf.get("title", "workflow").replace(" ", "_").replace("\u2014", "-").lower()
                safe_name = "".join(c for c in safe_name if c.isalnum() or c in ('_', '-')).strip('_')
                zf.writestr(f"oasis/yaml/{safe_name or 'my-layout'}.yaml", yaml_content)

            # --- 3. Skills folders (pass-through if stored in workflow metadata) ---
            # When a ZIP was imported with skills/ data, it may be stored
            # as wf["skills_data"] = {rel_path: base64_content, ...}
            skills_data = wf.get("skills_data", {})
            if isinstance(skills_data, dict):
                import base64
                for rel_path, b64_content in skills_data.items():
                    try:
                        raw = base64.b64decode(b64_content)
                        zf.writestr(rel_path, raw)
                    except Exception:
                        pass

        zip_buffer.seek(0)

        # Generate filename with timestamp (matches Clawcross format)
        safe_title = wf.get("title", "workflow").replace(" ", "_").lower()[:40]
        safe_title = "".join(c for c in safe_title if c.isalnum() or c in ('_', '-'))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"team_{safe_title or 'workflow'}_snapshot_{timestamp}.zip"

        return Response(
            zip_buffer.read(),
            mimetype='application/zip',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ══════════════════════════════════════════════════════════════
# Embedded Frontend HTML Templates
# ══════════════════════════════════════════════════════════════

MAIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ClawCrossHub — Workflow Community</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--surface:#161b22;--surface2:#21262d;--border:#30363d;--text:#e6edf3;--text2:#8b949e;--accent:#58a6ff;--accent2:#238636;--accent-hover:#1f6feb;--green:#3fb950;--orange:#d29922;--pink:#f778ba;--radius:8px;--shadow:0 2px 8px rgba(0,0,0,.3)}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}

/* Header */
.header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}
.header .logo{font-size:24px;font-weight:700;display:flex;align-items:center;gap:8px}
.header .logo span{background:linear-gradient(135deg,var(--accent),var(--pink));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header nav{display:flex;gap:16px;margin-left:auto}
.header nav a{color:var(--text2);font-size:14px;padding:6px 12px;border-radius:var(--radius);transition:.2s}
.header nav a:hover{color:var(--text);background:var(--surface2);text-decoration:none}

/* Search bar */
.search-section{max-width:1200px;margin:32px auto 0;padding:0 24px}
.search-bar{display:flex;gap:12px;align-items:center}
.search-bar input{flex:1;background:var(--surface);border:1px solid var(--border);color:var(--text);padding:10px 16px;border-radius:var(--radius);font-size:14px;outline:none;transition:.2s}
.search-bar input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(88,166,255,.15)}
.search-bar select{background:var(--surface);border:1px solid var(--border);color:var(--text);padding:10px 12px;border-radius:var(--radius);font-size:14px;cursor:pointer}

/* Stats banner */
.stats{max-width:1200px;margin:20px auto 0;padding:0 24px;display:flex;gap:24px;color:var(--text2);font-size:14px}
.stats .stat{display:flex;align-items:center;gap:6px}
.stats .stat b{color:var(--text);font-size:16px}

/* Tag filters */
.tag-filters{max-width:1200px;margin:16px auto 0;padding:0 24px;display:flex;gap:8px;flex-wrap:wrap}
.tag-btn{padding:4px 12px;border-radius:20px;font-size:12px;cursor:pointer;border:1px solid var(--border);background:var(--surface);color:var(--text2);transition:.2s}
.tag-btn:hover,.tag-btn.active{border-color:var(--accent);color:var(--accent);background:rgba(88,166,255,.1)}

/* Grid */
.grid{max-width:1200px;margin:24px auto;padding:0 24px;display:grid;grid-template-columns:repeat(auto-fill,minmax(340px,1fr));gap:16px}

/* Card */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:20px;cursor:pointer;transition:all .2s;display:flex;flex-direction:column;gap:12px;position:relative;overflow:hidden}
.card:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:var(--shadow)}
.card .card-header{display:flex;align-items:flex-start;gap:12px}
.card .card-icon{font-size:32px;flex-shrink:0;width:48px;height:48px;display:flex;align-items:center;justify-content:center;background:var(--surface2);border-radius:var(--radius)}
.card .card-title-block{flex:1;min-width:0}
.card .card-title{font-size:16px;font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.card .card-author{font-size:12px;color:var(--text2);margin-top:2px}
.card .card-desc{font-size:13px;color:var(--text2);line-height:1.5;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.card .card-meta{display:flex;gap:16px;align-items:center;margin-top:auto;padding-top:8px;border-top:1px solid var(--border);font-size:12px;color:var(--text2)}
.card .card-meta .meta-item{display:flex;align-items:center;gap:4px}
.card .card-tags{display:flex;gap:6px;flex-wrap:wrap}
.card .card-tags .tag{padding:2px 8px;border-radius:12px;font-size:11px;background:rgba(88,166,255,.1);color:var(--accent);border:1px solid rgba(88,166,255,.2)}
.card .dag-badge{position:absolute;top:12px;right:12px;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.3)}

/* Empty state */
.empty{text-align:center;padding:80px 24px;color:var(--text2)}
.empty .empty-icon{font-size:64px;margin-bottom:16px}
.empty h3{color:var(--text);margin-bottom:8px}

/* Publish modal */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:200;justify-content:center;align-items:center}
.modal-overlay.show{display:flex}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:12px;width:90%;max-width:600px;max-height:85vh;overflow-y:auto;padding:24px}
.modal h2{margin-bottom:16px;font-size:20px}
.modal label{display:block;font-size:13px;color:var(--text2);margin-bottom:4px;margin-top:12px}
.modal input,.modal textarea,.modal select{width:100%;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:8px 12px;border-radius:var(--radius);font-size:14px;font-family:inherit}
.modal textarea{min-height:120px;resize:vertical;font-family:'SFMono-Regular',Consolas,monospace;font-size:13px}
.modal .btn-row{display:flex;gap:12px;margin-top:20px;justify-content:flex-end}
.btn{padding:8px 16px;border-radius:var(--radius);font-size:14px;font-weight:500;cursor:pointer;border:1px solid var(--border);transition:.2s}
.btn-primary{background:var(--accent2);border-color:var(--accent2);color:#fff}.btn-primary:hover{filter:brightness(1.1)}
.btn-secondary{background:var(--surface2);color:var(--text)}.btn-secondary:hover{background:var(--border)}

/* User avatar & auth */
.user-auth{display:flex;align-items:center;gap:10px;margin-left:8px}
.github-btn{display:inline-flex;align-items:center;gap:6px;padding:6px 14px;border-radius:var(--radius);font-size:13px;font-weight:500;cursor:pointer;border:1px solid var(--border);background:var(--surface2);color:var(--text);transition:.2s;text-decoration:none}
.github-btn:hover{background:var(--border);text-decoration:none}
.github-btn svg{width:18px;height:18px;fill:currentColor}
.user-avatar{width:32px;height:32px;border-radius:50%;border:2px solid var(--border)}
.user-menu{position:relative;display:inline-flex;align-items:center;cursor:pointer}
.user-dropdown{display:none;position:absolute;top:40px;right:0;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:8px 0;min-width:180px;box-shadow:0 4px 12px rgba(0,0,0,.4);z-index:300}
.user-dropdown.show{display:block}
.user-dropdown a{display:block;padding:8px 16px;color:var(--text);font-size:13px;transition:.2s;text-decoration:none}
.user-dropdown a:hover{background:var(--surface2);text-decoration:none}
.user-dropdown .user-dropdown-name{padding:8px 16px;font-weight:600;font-size:13px;border-bottom:1px solid var(--border);margin-bottom:4px;color:var(--text)}

/* Login required modal */
.login-modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:250;justify-content:center;align-items:center}
.login-modal-overlay.show{display:flex}
.login-modal{background:var(--surface);border:1px solid var(--border);border-radius:12px;width:90%;max-width:400px;padding:32px;text-align:center}
.login-modal h3{margin-bottom:12px;font-size:20px}
.login-modal p{color:var(--text2);font-size:14px;line-height:1.6;margin-bottom:20px}
.login-modal .login-actions{display:flex;flex-direction:column;gap:10px;align-items:center}

/* Responsive */
@media(max-width:768px){.grid{grid-template-columns:1fr}.header{flex-wrap:wrap}.search-bar{flex-wrap:wrap}}
</style>
</head>
<body>
<div class="header">
<div class="logo">🌊 <span>ClawCrossHub</span></div>
  <nav>
    <a href="/" class="active">Explore</a>
  </nav>
  <div style="display:flex;align-items:center;gap:8px;margin-left:auto">
    <a href="https://github.com/ClawCross/ClawCross" target="_blank" rel="noopener" style="display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:var(--radius);background:var(--surface2);border:1px solid var(--border);color:var(--text);font-size:13px;font-weight:500;text-decoration:none;transition:.2s" onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--accent)'" onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text)'">⭐ GitHub</a>
    <button id="magicCopyBtn" onclick="copyMagicPrompt(this)" style="display:inline-flex;align-items:center;gap:5px;padding:6px 12px;border-radius:var(--radius);background:linear-gradient(135deg,#238636,#2ea043);border:1px solid rgba(63,185,80,.4);color:#fff;font-size:13px;font-weight:500;cursor:pointer;transition:.2s" onmouseover="this.style.filter='brightness(1.15)'" onmouseout="this.style.filter='none'" title="Copy a magic prompt to guide OpenClaw to download Clawcross from GitHub">📋 Copy Magic Prompt</button>
  </div>
  <div class="user-auth" id="userAuthArea">
    <!-- Filled by JS on load -->
  </div>
  <a href="javascript:void(0)" onclick="openPublishModal()" style="display:inline-flex;align-items:center;gap:5px;padding:6px 14px;border-radius:var(--radius);background:linear-gradient(135deg,var(--accent),var(--pink));color:#fff;font-size:13px;font-weight:600;text-decoration:none;cursor:pointer;transition:.2s;margin-left:4px" onmouseover="this.style.filter='brightness(1.15)'" onmouseout="this.style.filter='none'">📤 Publish</a>
</div>

<div class="search-section">
  <div class="search-bar">
    <input id="searchInput" type="text" placeholder="🔍 Search workflows by name, description, or author..." oninput="debounceSearch()">
    <select id="categoryFilter" onchange="loadWorkflows()">
      <option value="">All Categories</option>
    </select>
  </div>
</div>

<div class="stats" id="statsBar"></div>
<div class="tag-filters" id="tagFilters"></div>
<div class="grid" id="workflowGrid"></div>

<!-- Unified Publish Modal (combines Import + Publish) -->
<div class="modal-overlay" id="publishModal">
  <div class="modal">
    <h2>� Publish Workflow</h2>
    <!-- Mode Tabs -->
    <div id="pubModeTabs" style="display:flex;gap:0;margin-bottom:16px;border:1px solid var(--border);border-radius:var(--radius);overflow:hidden">
      <button class="pub-tab active" onclick="switchPubMode('zip')" id="tabZip" style="flex:1;padding:10px 16px;font-size:14px;font-weight:500;cursor:pointer;border:none;transition:.2s;background:var(--accent);color:#fff">📦 Upload ZIP</button>
      <button class="pub-tab" onclick="switchPubMode('yaml')" id="tabYaml" style="flex:1;padding:10px 16px;font-size:14px;font-weight:500;cursor:pointer;border:none;transition:.2s;background:var(--surface2);color:var(--text2)">📝 Write YAML</button>
    </div>

    <!-- Common Fields -->
    <label>Title</label>
    <input id="pubTitle" placeholder="My Awesome Workflow">
    <label>Author</label>
    <input id="pubAuthor" placeholder="Your name" value="Anonymous">
    <label>Description</label>
    <input id="pubDesc" placeholder="A brief description of what this workflow does">
    <label>Category</label>
    <select id="pubCategory">
      <option value="Engineering">Engineering</option>
      <option value="Ideation">Ideation</option>
      <option value="Business">Business</option>
      <option value="Research">Research</option>
      <option value="Community">Community</option>
      <option value="Imported">Imported</option>
    </select>
    <label>Tags (comma-separated)</label>
    <input id="pubTags" placeholder="ml, code, pipeline">

    <!-- ZIP Upload Section -->
    <div id="pubZipSection">
      <label style="margin-top:16px">Upload Team Snapshot (.zip)</label>
      <p style="color:var(--text2);font-size:12px;margin-bottom:8px">ZIP should contain JSON metadata (internal_agents.json, external_agents.json, oasis_experts.json) and YAML workflow files in oasis/yaml/.</p>
      <div id="importDropZone" style="border:2px dashed var(--border);border-radius:var(--radius);padding:32px;text-align:center;color:var(--text2);cursor:pointer;margin-top:8px;transition:.2s">
        <div style="font-size:32px;margin-bottom:8px">📂</div>
        <div id="importDropLabel">Drag & drop or click to select a <b>.zip</b> file</div>
      </div>
      <input type="file" id="importFileInput" accept=".zip" style="display:none">

      <details style="margin-top:16px">
        <summary style="cursor:pointer;color:var(--accent);font-size:13px">➕ Define Custom Agents (optional)</summary>
        <div style="margin-top:8px;font-size:12px;color:var(--text2);margin-bottom:8px">Add custom agent definitions that will be included in the import. Each agent needs a name and ability/tag.</div>
        <div id="customAgentsList"></div>
        <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-top:8px" onclick="addCustomAgent()">+ Add Agent</button>
      </details>
    </div>

    <!-- YAML Write Section -->
    <div id="pubYamlSection" style="display:none">
      <label style="margin-top:16px">YAML Content *</label>
<textarea id="pubYaml" placeholder="version: 2&#10;repeat: false&#10;plan:&#10;- id: on1&#10;  expert: creative#temp#1"></textarea>
      <label>Detailed Description</label>
      <textarea id="pubDetail" placeholder="Explain how this workflow works and when to use it..." style="min-height:80px;font-family:inherit"></textarea>
    </div>

    <div id="publishStatus" style="margin-top:12px;font-size:13px;color:var(--text2);display:none"></div>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="closePublishModal()">Cancel</button>
      <button class="btn btn-primary" id="publishBtn" onclick="doPublish()">Publish</button>
    </div>
  </div>
</div>

<!-- Login Required Modal -->
<div class="login-modal-overlay" id="loginModal">
  <div class="login-modal">
    <h3>🔒 Login Required</h3>
    <p>Publishing and uploading workflows requires GitHub authentication.<br>Browsing and downloading are available without login.</p>
    <div class="login-actions">
      <a href="/auth/github" class="github-btn" style="padding:10px 24px;font-size:15px">
        <svg viewBox="0 0 16 16" width="20" height="20" fill="currentColor"><path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 01-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.04-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 010 8c0-4.42 3.58-8 8-8z"></path></svg>
        Sign in with GitHub
      </a>
      <button class="btn btn-secondary" onclick="closeLoginModal()" style="margin-top:4px">Continue as Guest</button>
    </div>
  </div>
</div>

<script>
let searchTimer;
const allTags = new Set();
let activeTag = '';
let currentUser = null;  // GitHub user object or null

// ── Auth helpers ──
async function checkAuthStatus() {
  try {
    const resp = await fetch('/api/auth/status');
    const data = await resp.json();
    const area = document.getElementById('userAuthArea');
    if (data.logged_in) {
      currentUser = data.user;
      area.innerHTML = `<div class="user-menu" onclick="toggleUserDropdown()">
        <img class="user-avatar" src="${escHtml(data.user.avatar_url)}" alt="avatar">
        <div class="user-dropdown" id="userDropdown">
          <div class="user-dropdown-name">👤 ${escHtml(data.user.name || data.user.login)}</div>
          <a href="${escHtml(data.user.html_url)}" target="_blank">🔗 GitHub Profile</a>
          <a href="/auth/logout">🚪 Logout</a>
        </div>
      </div>`;
    } else {
      currentUser = null;
      area.innerHTML = `<a href="/auth/github" class="github-btn">
        <svg viewBox="0 0 16 16" width="18" height="18" fill="currentColor"><path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 01-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.04-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 010 8c0-4.42 3.58-8 8-8z"/></svg>
        Sign in
      </a>`;
    }
  } catch(e) { console.error('Auth check failed:', e); }
}

function toggleUserDropdown() {
  const dd = document.getElementById('userDropdown');
  dd.classList.toggle('show');
}
// Close dropdown when clicking outside
document.addEventListener('click', e => {
  const dd = document.getElementById('userDropdown');
  if (dd && !e.target.closest('.user-menu')) dd.classList.remove('show');
});

function openLoginModal() {
  document.getElementById('loginModal').classList.add('show');
}
function closeLoginModal() {
  document.getElementById('loginModal').classList.remove('show');
}

// Magic Prompt — copy to clipboard for user's OpenClaw
function copyMagicPrompt(btn) {
  const prompt = 'Clone https://github.com/ClawCross/ClawCross.git, read AGENTS.md, and install Clawcross.';
  if (!btn) btn = document.getElementById('magicCopyBtn');
  const orig = btn.innerHTML;
  function onSuccess() {
    btn.innerHTML = '✅ Copied!';
    btn.style.background = 'var(--accent2)';
    setTimeout(function() { btn.innerHTML = orig; btn.style.background = 'linear-gradient(135deg,#238636,#2ea043)'; }, 2000);
  }
  // Try modern clipboard API first
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(prompt).then(onSuccess).catch(function() { fallbackCopy(prompt, onSuccess); });
  } else {
    fallbackCopy(prompt, onSuccess);
  }
}
function fallbackCopy(text, cb) {
  var ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;opacity:0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  try { document.execCommand('copy'); if (cb) cb(); } catch(e) { alert('Copy failed, please copy manually.'); }
  document.body.removeChild(ta);
}

async function loadWorkflows() {
  const search = document.getElementById('searchInput').value;
  const category = document.getElementById('categoryFilter').value;
  let url = `/api/workflows?search=${encodeURIComponent(search)}&category=${encodeURIComponent(category)}`;
  if (activeTag) url += `&tag=${encodeURIComponent(activeTag)}`;
  const resp = await fetch(url);
  const data = await resp.json();
  renderGrid(data.workflows);
  renderStats(data);
}

function renderGrid(workflows) {
  const grid = document.getElementById('workflowGrid');
  if (!workflows.length) {
    grid.innerHTML = `<div class="empty" style="grid-column:1/-1"><div class="empty-icon">🔍</div><h3>No workflows found</h3><p>Try adjusting your search or filters</p></div>`;
    return;
  }
  grid.innerHTML = workflows.map(w => {
    const tagHtml = (w.tags||[]).map(t => {
      allTags.add(t);
      return `<span class="tag">${t}</span>`;
    }).join('');
    const dagBadge = w.is_dag ? '<div class="dag-badge">DAG</div>' : '';
    const typeIcons = (w.step_types||[]).map(t => {
      if(t==='expert') return '👤';
      if(t==='parallel') return '⚡';
      if(t==='manual') return '📝';
      if(t==='all_experts') return '👥';
      return '•';
    }).join(' ');
    return `
      <div class="card" onclick="window.location='/workflow/${w.id}'">
        ${dagBadge}
        <div class="card-header">
          <div class="card-icon">${w.icon||'📦'}</div>
          <div class="card-title-block">
            <div class="card-title">${escHtml(w.title)}</div>
            <div class="card-author">by ${escHtml(w.author)} · ${w.source==='preset'?'Official':'Community'}</div>
          </div>
        </div>
        <div class="card-desc">${escHtml(w.description)}</div>
        <div class="card-tags">${tagHtml}</div>
        <div class="card-meta">
          <span class="meta-item">⭐ ${w.stars||0}</span>
          <span class="meta-item">🔀 ${w.forks||0}</span>
          <span class="meta-item">📊 ${w.steps} steps</span>
          <span class="meta-item">${w.repeat?'🔁 Repeat':'▶️ Once'}</span>
          <span class="meta-item">${typeIcons}</span>
          <span class="meta-item" style="margin-left:auto"><button onclick="event.stopPropagation();copyCurlForCard(this,'${w.id}',${JSON.stringify(w.title||'workflow').replace(/'/g,'\\u0027')})" style="display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:4px;border:1px solid var(--border);background:var(--surface2);color:var(--text2);font-size:11px;cursor:pointer;transition:.2s" onmouseover="this.style.borderColor='var(--accent)';this.style.color='var(--accent)'" onmouseout="this.style.borderColor='var(--border)';this.style.color='var(--text2)'" title="Copy curl download command">📋 curl</button></span>
        </div>
      </div>`;
  }).join('');
  renderTagFilters();
}

function copyCurlForCard(btn, wfId, title) {
  const safeTitle = (title || 'workflow').toLowerCase().replace(/[\s\u2014]+/g, '_').replace(/[^a-z0-9_-]/g, '').slice(0, 40) || 'workflow';
  const cmd = 'curl -L -o "team_' + safeTitle + '_snapshot.zip" "' + window.location.origin + '/api/workflows/' + wfId + '/download"';
  const orig = btn.innerHTML;
  function onOk() { btn.innerHTML = '✅ Copied!'; setTimeout(function(){ btn.innerHTML = orig; }, 1500); }
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(cmd).then(onOk).catch(function(){ fallbackCopy(cmd, onOk); });
  } else { fallbackCopy(cmd, onOk); }
}

function renderStats(data) {
  document.getElementById('statsBar').innerHTML = `
    <div class="stat"><b>${data.total}</b> workflows available</div>
    <div class="stat">📦 Presets + Community</div>
  `;
}

function renderTagFilters() {
  const container = document.getElementById('tagFilters');
  if (!allTags.size) { container.innerHTML = ''; return; }
  let html = `<span class="tag-btn ${!activeTag?'active':''}" onclick="filterTag('')">All</span>`;
  allTags.forEach(t => {
    html += `<span class="tag-btn ${activeTag===t?'active':''}" onclick="filterTag('${t}')">${t}</span>`;
  });
  container.innerHTML = html;
}

function filterTag(tag) {
  activeTag = tag;
  loadWorkflows();
}

function debounceSearch() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadWorkflows, 300);
}

async function loadCategories() {
  const resp = await fetch('/api/categories');
  const cats = await resp.json();
  const sel = document.getElementById('categoryFilter');
  cats.forEach(c => {
    const opt = document.createElement('option');
    opt.value = c; opt.textContent = c;
    sel.appendChild(opt);
  });
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s||'';
  return d.innerHTML;
}

// ── Unified Publish Modal (ZIP upload + YAML write) ──
let pubMode = 'zip';  // 'zip' or 'yaml'
let importFile = null;
let customAgents = [];  // [{name, tag}]

function switchPubMode(mode) {
  pubMode = mode;
  const tabZip = document.getElementById('tabZip');
  const tabYaml = document.getElementById('tabYaml');
  const zipSec = document.getElementById('pubZipSection');
  const yamlSec = document.getElementById('pubYamlSection');
  if (mode === 'zip') {
    tabZip.style.background = 'var(--accent)'; tabZip.style.color = '#fff';
    tabYaml.style.background = 'var(--surface2)'; tabYaml.style.color = 'var(--text2)';
    zipSec.style.display = ''; yamlSec.style.display = 'none';
  } else {
    tabYaml.style.background = 'var(--accent)'; tabYaml.style.color = '#fff';
    tabZip.style.background = 'var(--surface2)'; tabZip.style.color = 'var(--text2)';
    zipSec.style.display = 'none'; yamlSec.style.display = '';
  }
}

function openPublishModal() {
  if (!currentUser) {
    openLoginModal();
    return;
  }
  document.getElementById('publishModal').classList.add('show');
  // Pre-fill author with GitHub username
  if (currentUser) {
    document.getElementById('pubAuthor').value = currentUser.name || currentUser.login || 'Anonymous';
  }
}

function closePublishModal() {
  document.getElementById('publishModal').classList.remove('show');
  // Reset all fields
  importFile = null;
  customAgents = [];
  document.getElementById('pubTitle').value = '';
  document.getElementById('pubDesc').value = '';
  document.getElementById('pubAuthor').value = 'Anonymous';
  document.getElementById('pubCategory').value = 'Engineering';
  document.getElementById('pubTags').value = '';
  document.getElementById('pubYaml').value = '';
  document.getElementById('pubDetail').value = '';
  document.getElementById('importDropLabel').innerHTML = 'Drag & drop or click to select a <b>.zip</b> file';
  document.getElementById('customAgentsList').innerHTML = '';
  document.getElementById('publishStatus').style.display = 'none';
  switchPubMode('zip');
}

// Drag & drop / file input for ZIP upload
(function(){
  const dz = document.getElementById('importDropZone');
  const fi = document.getElementById('importFileInput');
  dz.addEventListener('click', () => fi.click());
  dz.addEventListener('dragover', e => { e.preventDefault(); dz.style.borderColor='var(--accent)'; });
  dz.addEventListener('dragleave', () => { dz.style.borderColor='var(--border)'; });
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.style.borderColor='var(--border)';
    if (e.dataTransfer.files.length) handleImportFile(e.dataTransfer.files[0]);
  });
  fi.addEventListener('change', () => { if(fi.files.length) handleImportFile(fi.files[0]); });
})();

function handleImportFile(f) {
  if (!f.name.endsWith('.zip')) { alert('Only .zip files are accepted.'); return; }
  importFile = f;
  document.getElementById('importDropLabel').innerHTML = '✅ <b>' + escHtml(f.name) + '</b> (' + (f.size/1024).toFixed(1) + ' KB)';
}

function addCustomAgent() {
  const idx = customAgents.length;
  customAgents.push({name:'', tag:''});
  const container = document.getElementById('customAgentsList');
  const row = document.createElement('div');
  row.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;align-items:center';
  row.innerHTML = `<input placeholder="Agent Name" style="flex:1;background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 10px;border-radius:var(--radius);font-size:13px" oninput="customAgents[${idx}].name=this.value">
    <select style="background:var(--surface2);border:1px solid var(--border);color:var(--text);padding:6px 8px;border-radius:var(--radius);font-size:12px" onchange="customAgents[${idx}].tag=this.value">
      <option value="">Select Tag/Ability</option>
      <option value="creative">🎨 Creative</option>
      <option value="critical">🔍 Critical</option>
      <option value="data">📊 Data</option>
      <option value="synthesis">🎯 Synthesis</option>
      <option value="economist">📈 Economist</option>
      <option value="lawyer">⚖️ Lawyer</option>
      <option value="entrepreneur">🚀 Entrepreneur</option>
      <option value="common_person">🧑 Common Person</option>
      <option value="ml">🤖 ML</option>
      <option value="code">💻 Code</option>
      <option value="review">📋 Review</option>
      <option value="custom">⭐ Custom</option>
    </select>
    <button style="background:none;border:none;color:var(--text2);cursor:pointer;font-size:16px" onclick="this.parentElement.remove();customAgents[${idx}]=null">✕</button>`;
  container.appendChild(row);
}

async function doPublish() {
  const statusEl = document.getElementById('publishStatus');
  statusEl.style.display = 'block'; statusEl.textContent = '⏳ Publishing...';

  const title = document.getElementById('pubTitle').value.trim();
  const author = document.getElementById('pubAuthor').value.trim() || 'Anonymous';
  const description = document.getElementById('pubDesc').value.trim();
  const category = document.getElementById('pubCategory').value;
  const tags = document.getElementById('pubTags').value.split(',').map(s=>s.trim()).filter(Boolean);

  if (pubMode === 'zip') {
    // ── ZIP upload mode ──
    if (!importFile) { statusEl.innerHTML = '❌ Please select a .zip file first'; return; }
    const fd = new FormData();
    fd.append('file', importFile);
    fd.append('author', author);
    fd.append('team_name', title);
    fd.append('description', description);
    fd.append('category', category);
    fd.append('tags', JSON.stringify(tags));
    const validAgents = customAgents.filter(a => a && a.name && a.name.trim());
    if (validAgents.length) fd.append('extra_agents', JSON.stringify(validAgents));
    try {
      const resp = await fetch('/api/import/zip', {method:'POST', body:fd});
      const result = await resp.json();
      if (resp.status === 401) { closePublishModal(); openLoginModal(); return; }
      if (result.error) { statusEl.innerHTML = '❌ ' + escHtml(result.error); return; }
      let msg = '✅ Published ' + result.count + ' workflow(s)!';
      if (result.internal_agents_count) msg += ' (' + result.internal_agents_count + ' agents';
      if (result.external_agents_count) msg += ', ' + result.external_agents_count + ' OpenClaw';
      if (result.experts_count) msg += ', ' + result.experts_count + ' experts';
      if (result.internal_agents_count || result.external_agents_count || result.experts_count) msg += ')';
      statusEl.innerHTML = msg;
      setTimeout(() => { closePublishModal(); loadWorkflows(); }, 1500);
    } catch(e) { statusEl.innerHTML = '❌ ' + e.message; }
  } else {
    // ── YAML write mode ──
    const yamlContent = document.getElementById('pubYaml').value.trim();
    if (!title || !yamlContent) { statusEl.innerHTML = '❌ Title and YAML content are required'; return; }
    const body = {
      title, description, author, category, tags,
      yaml_content: yamlContent,
      detail: document.getElementById('pubDetail').value.trim(),
    };
    try {
      const resp = await fetch('/api/workflows/publish', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      const result = await resp.json();
      if (resp.status === 401) { closePublishModal(); openLoginModal(); return; }
      if (result.error) { statusEl.innerHTML = '❌ ' + escHtml(result.error); return; }
      statusEl.innerHTML = '✅ Workflow published successfully!';
      setTimeout(() => { closePublishModal(); loadWorkflows(); }, 1500);
    } catch(e) { statusEl.innerHTML = '❌ ' + e.message; }
  }
}

// Init
checkAuthStatus();
loadCategories();
loadWorkflows();
</script>
</body>
</html>"""


DETAIL_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ClawCrossHub — Workflow Detail</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#0d1117;--surface:#161b22;--surface2:#21262d;--border:#30363d;--text:#e6edf3;--text2:#8b949e;--accent:#58a6ff;--accent2:#238636;--green:#3fb950;--orange:#d29922;--pink:#f778ba;--radius:8px}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}

.header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 24px;display:flex;align-items:center;gap:16px;position:sticky;top:0;z-index:100}
.header .logo{font-size:24px;font-weight:700;display:flex;align-items:center;gap:8px}
.header .logo span{background:linear-gradient(135deg,var(--accent),var(--pink));-webkit-background-clip:text;-webkit-text-fill-color:transparent}

.container{max-width:1200px;margin:32px auto;padding:0 24px}
.back-link{display:inline-flex;align-items:center;gap:6px;color:var(--text2);font-size:14px;margin-bottom:20px;transition:.2s}
.back-link:hover{color:var(--accent);text-decoration:none}

.detail-header{display:flex;align-items:flex-start;gap:20px;margin-bottom:24px}
.detail-icon{font-size:48px;width:72px;height:72px;display:flex;align-items:center;justify-content:center;background:var(--surface);border:1px solid var(--border);border-radius:12px;flex-shrink:0}
.detail-info h1{font-size:28px;font-weight:700;margin-bottom:4px}
.detail-info .author{font-size:14px;color:var(--text2)}
.detail-info .desc{font-size:15px;color:var(--text2);margin-top:8px;line-height:1.6}

.action-bar{display:flex;gap:12px;margin-bottom:24px;flex-wrap:wrap}
.btn{padding:8px 16px;border-radius:var(--radius);font-size:14px;font-weight:500;cursor:pointer;border:1px solid var(--border);transition:.2s;display:inline-flex;align-items:center;gap:6px}
.btn-primary{background:var(--accent2);border-color:var(--accent2);color:#fff}.btn-primary:hover{filter:brightness(1.1)}
.btn-secondary{background:var(--surface2);color:var(--text)}.btn-secondary:hover{background:var(--border)}
.btn-star{background:var(--surface);color:var(--orange)}.btn-star:hover{background:var(--surface2)}

.meta-badges{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px}
.badge{padding:4px 12px;border-radius:20px;font-size:13px;border:1px solid var(--border);background:var(--surface)}
.badge.dag{border-color:rgba(63,185,80,.3);color:var(--green);background:rgba(63,185,80,.1)}
.badge.repeat{border-color:rgba(210,153,34,.3);color:var(--orange);background:rgba(210,153,34,.1)}
.badge.tag{border-color:rgba(88,166,255,.2);color:var(--accent);background:rgba(88,166,255,.1)}

.section{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);margin-bottom:20px;overflow:hidden}
.section-header{padding:12px 16px;border-bottom:1px solid var(--border);font-weight:600;font-size:14px;background:var(--surface2);display:flex;align-items:center;gap:8px}
.section-body{padding:16px}
.section-body p{line-height:1.7;color:var(--text2)}

/* YAML code block */
.yaml-block{background:#0d1117;border:1px solid var(--border);border-radius:var(--radius);overflow:auto;max-height:500px}
.yaml-block pre{padding:16px;font-family:'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace;font-size:13px;line-height:1.6;color:#e6edf3;white-space:pre;margin:0}

/* Floating info panel inside canvas — compact */
.fg-panel{position:absolute;top:10px;right:10px;z-index:120;width:320px;max-height:55%;background:rgba(22,27,34,.92);border:1px solid var(--border);border-radius:10px;backdrop-filter:blur(10px);display:flex;flex-direction:column;transition:width .2s ease,max-height .2s ease,opacity .2s;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,.4);font-size:12px}
.fg-panel.collapsed{width:32px;max-height:32px;border-radius:8px;cursor:pointer;opacity:.75}
.fg-panel.collapsed:hover{opacity:1}
.fg-panel-toggle{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;font-size:12px;font-weight:600;color:var(--text);cursor:pointer;user-select:none;border-bottom:1px solid var(--border);flex-shrink:0}
.fg-panel-toggle .toggle-icon{font-size:12px;transition:transform .2s}
.fg-panel.collapsed .fg-panel-toggle{border-bottom:none;justify-content:center;padding:6px}
.fg-panel.collapsed .fg-panel-toggle .toggle-label{display:none}
.fg-panel-body{overflow-y:auto;overflow-x:hidden;padding:10px;display:flex;flex-direction:column;gap:10px;flex:1;min-height:0;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.15) transparent}
.fg-panel-body::-webkit-scrollbar{width:4px}
.fg-panel-body::-webkit-scrollbar-thumb{background:rgba(255,255,255,.18);border-radius:2px}
.fg-panel.collapsed .fg-panel-body{display:none}
.fg-panel .sidebar-card{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px}
.fg-panel .sidebar-card-header{font-weight:600;font-size:12px;margin-bottom:6px;display:flex;align-items:center;gap:5px}
.fg-panel .sidebar-expert-chip{padding:3px 8px;border-radius:10px;font-size:10px;background:var(--surface);border:1px solid var(--border);display:inline-flex;align-items:center;gap:3px;margin:2px}
.fg-panel .persona-item{margin-bottom:5px;padding:6px;background:var(--surface);border-radius:5px;border:1px solid var(--border)}
.fg-panel .persona-name{font-weight:600;font-size:11px;margin-bottom:3px}
.fg-panel .persona-desc{font-size:11px;color:var(--text2);line-height:1.4;display:-webkit-box;-webkit-line-clamp:4;-webkit-box-orient:vertical;overflow:hidden}

/* YAML toggle button */
.yaml-toggle-btn{display:inline-flex;align-items:center;gap:6px;padding:8px 16px;border-radius:var(--radius);font-size:13px;font-weight:500;cursor:pointer;border:1px solid var(--border);background:var(--surface2);color:var(--text);transition:.2s}
.yaml-toggle-btn:hover{background:var(--border)}
.yaml-section-collapsible{max-height:0;overflow:hidden;transition:max-height .3s ease}
.yaml-section-collapsible.open{max-height:2000px}

/* Flow diagram — node-and-wire graph (canvas with pan/zoom) */
.flow-graph{position:relative;overflow:hidden;min-height:400px;border-radius:var(--radius);background:#0d1117;cursor:grab}
.flow-graph.fg-grabbing{cursor:grabbing}
.flow-graph-inner{position:absolute;top:0;left:0;transform-origin:0 0;background:linear-gradient(rgba(48,54,61,.3) 1px,transparent 1px),linear-gradient(90deg,rgba(48,54,61,.3) 1px,transparent 1px);background-size:24px 24px}
.flow-graph svg.flow-edges{position:absolute;top:0;left:0;pointer-events:none;z-index:1}
.fg-nav{position:absolute;bottom:10px;right:10px;z-index:100;display:flex;align-items:center;gap:4px;background:rgba(22,27,34,.85);border-radius:8px;padding:4px 6px;border:1px solid var(--border);backdrop-filter:blur(6px)}
.fg-nav button{background:none;border:1px solid var(--border);border-radius:4px;color:var(--text2);width:26px;height:26px;font-size:13px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .15s}
.fg-nav button:hover{background:var(--surface2);color:var(--text)}
.fg-nav .fg-zoom-label{font-size:11px;color:var(--text2);min-width:38px;text-align:center;user-select:none}
.flow-graph .fg-node{position:absolute;min-width:140px;padding:12px 16px;border-radius:12px;background:var(--surface);border:2px solid var(--accent);cursor:pointer;user-select:none;z-index:10;display:flex;align-items:center;gap:10px;font-size:13px;box-shadow:0 2px 12px rgba(0,0,0,.2);transition:border-color .15s, box-shadow .15s}
.flow-graph .fg-node:hover{border-color:#79c0ff;box-shadow:0 4px 16px rgba(88,166,255,.25)}
.flow-graph .fg-node.parallel-node{border-color:var(--green);background:rgba(63,185,80,.06)}
.flow-graph .fg-node.parallel-node:hover{border-color:#56d364;box-shadow:0 4px 16px rgba(63,185,80,.25)}
.flow-graph .fg-node.manual-node{border-color:var(--orange);background:rgba(210,153,34,.06)}
.flow-graph .fg-node.manual-node:hover{border-color:#e3b341;box-shadow:0 4px 16px rgba(210,153,34,.25)}
.flow-graph .fg-node.all-node{border-color:var(--pink);background:rgba(247,120,186,.06)}
.flow-graph .fg-node .fg-emoji{font-size:20px;flex-shrink:0}
.flow-graph .fg-node .fg-info{display:flex;flex-direction:column;gap:2px;min-width:0}
.flow-graph .fg-node .fg-name{font-weight:600;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.flow-graph .fg-node .fg-tag{font-size:10px;color:var(--text2)}
.flow-graph .fg-node .fg-port{position:absolute;width:10px;height:10px;border-radius:50%;background:var(--accent);border:2px solid var(--surface);z-index:15}
.flow-graph .fg-node .fg-port.port-out{right:-5px;top:50%;transform:translateY(-50%)}
.flow-graph .fg-node .fg-port.port-in{left:-5px;top:50%;transform:translateY(-50%)}
.flow-graph .fg-group{position:absolute;border-radius:14px;border:2px dashed var(--green);background:rgba(63,185,80,.04);z-index:2}
.flow-graph .fg-group-label{position:absolute;top:-10px;left:14px;padding:1px 8px;border-radius:8px;font-size:10px;background:var(--surface);color:var(--green);border:1px solid rgba(63,185,80,.4)}

/* Expert cards */
.expert-list{display:flex;flex-wrap:wrap;gap:8px}
.expert-chip{padding:6px 12px;border-radius:20px;font-size:13px;background:var(--surface2);border:1px solid var(--border);display:flex;align-items:center;gap:4px}

/* Agent detail section below diagram */
.agent-detail-section{padding:16px}
.agent-type-group{margin-bottom:24px}
.agent-type-header{display:flex;align-items:center;gap:10px;margin-bottom:14px;padding-bottom:8px;border-bottom:2px solid var(--border);cursor:pointer;user-select:none}
.agent-type-header:hover{border-bottom-color:var(--accent)}
.agent-type-header .type-arrow{font-size:12px;color:var(--text2);transition:transform .2s;width:16px}
.agent-type-header.collapsed .type-arrow{transform:rotate(-90deg)}
.agent-type-header .type-emoji{font-size:22px}
.agent-type-header .type-title{font-size:16px;font-weight:700;color:var(--text)}
.agent-type-badge{font-size:10px;font-weight:700;padding:2px 8px;border-radius:6px;text-transform:uppercase;letter-spacing:.5px}
.agent-type-badge.badge-oasis{background:rgba(63,185,80,.15);color:#3fb950;border:1px solid rgba(63,185,80,.3)}
.agent-type-badge.badge-openclaw{background:rgba(136,98,255,.15);color:#8862ff;border:1px solid rgba(136,98,255,.3)}
.agent-type-badge.badge-external{background:rgba(255,166,87,.15);color:#ffa657;border:1px solid rgba(255,166,87,.3)}
.agent-type-badge.badge-custom{background:rgba(255,107,237,.15);color:#ff6bed;border:1px solid rgba(255,107,237,.3)}
.agent-type-body{overflow:hidden;transition:max-height .3s ease}
.agent-type-body.collapsed{max-height:0 !important}
.agent-cards-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}
.agent-card{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px 16px;transition:border-color .2s,box-shadow .2s}
.agent-card:hover{border-color:var(--accent);box-shadow:0 2px 12px rgba(88,166,255,.15)}
.agent-card-top{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.agent-card-icon{font-size:28px;width:42px;height:42px;display:flex;align-items:center;justify-content:center;background:var(--surface);border-radius:10px;border:1px solid var(--border);flex-shrink:0}
.agent-card-name{font-size:15px;font-weight:700;color:var(--text)}
.agent-card-tag{font-size:11px;color:var(--accent);font-family:monospace}
.agent-card-type-label{margin-left:auto}
.agent-card-body{display:flex;flex-direction:column;gap:6px}
.agent-card-row{display:flex;align-items:flex-start;gap:6px;font-size:12px}
.agent-card-row .row-label{color:var(--text2);font-weight:600;min-width:80px;flex-shrink:0}
.agent-card-row .row-value{color:var(--text);line-height:1.5}
.agent-persona-toggle{display:flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;color:var(--accent);padding:4px 0;user-select:none;transition:color .2s}
.agent-persona-toggle:hover{color:var(--text)}
.agent-persona-toggle .persona-arrow{display:inline-block;font-size:10px;transition:transform .2s}
.agent-persona-toggle.open .persona-arrow{transform:rotate(90deg)}
.agent-card-persona{font-size:12px;color:var(--text2);line-height:1.5;margin-top:4px;padding:8px;background:var(--surface);border-radius:6px;border:1px solid var(--border);max-height:120px;overflow-y:auto;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.1) transparent;display:none}
.agent-card-persona.show{display:block}
.agent-card-persona::-webkit-scrollbar{width:3px}
.agent-card-persona::-webkit-scrollbar-thumb{background:rgba(255,255,255,.15);border-radius:2px}
.agent-card-config{display:flex;flex-wrap:wrap;gap:6px;margin-top:4px}
.agent-config-badge{display:inline-flex;align-items:center;gap:3px;padding:3px 8px;border-radius:6px;font-size:11px;background:var(--surface);border:1px solid var(--border);color:var(--text2)}
.agent-config-badge .cfg-icon{font-size:12px}
.agent-config-badge .cfg-val{color:var(--text);font-weight:600}
.agent-node-list{margin-top:6px;display:flex;flex-wrap:wrap;gap:4px}
.agent-node-chip{padding:2px 7px;border-radius:4px;font-size:10px;font-family:monospace;background:rgba(88,166,255,.1);border:1px solid rgba(88,166,255,.2);color:var(--accent)}
.agent-skills-section{margin-top:8px;padding:8px;background:var(--surface);border-radius:6px;border:1px solid var(--border)}
.agent-skills-title{font-size:12px;font-weight:600;color:var(--text);margin-bottom:6px;display:flex;align-items:center;gap:5px}
.agent-skill-item{display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:4px;background:var(--surface2);border-radius:6px;border:1px solid var(--border);font-size:11px}
.agent-skill-item:last-child{margin-bottom:0}
.agent-skill-name{font-weight:600;color:var(--accent)}
.agent-skill-meta{color:var(--text2);font-size:10px;display:flex;gap:8px;flex-wrap:wrap}
.agent-skill-meta span{display:inline-flex;align-items:center;gap:2px}
.agent-skill-registry{color:var(--text2);font-size:10px;opacity:.7}
.agent-cron-section{margin-top:8px;padding:8px;background:var(--surface);border-radius:6px;border:1px solid var(--border)}
.agent-cron-title{font-size:12px;font-weight:600;color:var(--text);margin-bottom:6px;display:flex;align-items:center;gap:5px}
.agent-cron-item{display:flex;flex-direction:column;gap:3px;padding:6px 8px;margin-bottom:4px;background:var(--surface2);border-radius:6px;border:1px solid var(--border);font-size:11px}
.agent-cron-item:last-child{margin-bottom:0}
.agent-cron-name{font-weight:600;color:#e5c07b}
.agent-cron-detail{color:var(--text2);font-size:10px;display:flex;gap:10px;flex-wrap:wrap}
.agent-cron-detail span{display:inline-flex;align-items:center;gap:2px}
.agent-cron-msg{color:var(--text2);font-size:10px;font-style:italic;margin-top:2px;padding:3px 6px;background:rgba(229,192,123,.08);border-radius:4px;border-left:2px solid rgba(229,192,123,.3)}
.agent-cron-badge-enabled{color:#98c379;font-size:9px;font-weight:600}
.agent-cron-badge-disabled{color:#e06c75;font-size:9px;font-weight:600}

.loading{text-align:center;padding:60px;color:var(--text2);font-size:16px}

/* Agent hover tooltip */
.fg-node{position:relative}
.agent-tooltip{display:none;position:absolute;bottom:calc(100% + 10px);left:50%;transform:translateX(-50%);background:var(--surface);border:1px solid var(--accent);border-radius:var(--radius);padding:12px 16px;min-width:260px;max-width:360px;box-shadow:0 4px 16px rgba(0,0,0,.5);z-index:500;text-align:left;pointer-events:none}
.agent-tooltip::after{content:'';position:absolute;top:100%;left:50%;transform:translateX(-50%);border:6px solid transparent;border-top-color:var(--accent)}
.agent-tooltip .tt-name{font-weight:700;font-size:14px;margin-bottom:4px;color:var(--text)}
.agent-tooltip .tt-tag{font-size:11px;color:var(--accent);margin-bottom:6px}
.agent-tooltip .tt-persona{font-size:12px;color:var(--text2);line-height:1.5;white-space:pre-wrap;word-break:break-word}
.agent-tooltip .tt-temp{font-size:11px;color:var(--orange);margin-top:6px}
.fg-node:hover .agent-tooltip{display:block}
</style>
</head>
<body>
<div class="header">
  <a href="/" style="text-decoration:none"><div class="logo">🌊 <span>ClawCrossHub</span></div></a>
</div>

<div class="container">
  <a href="/" class="back-link">← Back to Explore</a>
<div id="detailContent" class="loading">Loading workflow...</div>
</div>

<script>
const WORKFLOW_ID = '{{ workflow_id }}';

const TAG_EMOJI = {creative:'🎨',critical:'🔍',data:'📊',synthesis:'🎯',economist:'📈',lawyer:'⚖️',cost_controller:'💰',revenue_planner:'📊',entrepreneur:'🚀',common_person:'🧑',manual:'📝',custom:'⭐'};

// Global storage for expert detail lookup (populated by loadDetail)
let expertsDetailMap = {};  // tag → {name, tag, persona, temperature}

function buildTooltipHtml(tag) {
  const info = expertsDetailMap[tag];
  if (!info) return '';
  const name = info.name || info.name_en || tag;
  const persona = info.persona || '';
  const temp = info.temperature;
  let html = `<div class="tt-name">${TAG_EMOJI[tag]||'⭐'} ${escHtml(name)}</div>`;
  html += `<div class="tt-tag">Tag: ${escHtml(tag)}</div>`;
  if (persona) html += `<div class="tt-persona">${escHtml(persona.length > 200 ? persona.slice(0,200) + '...' : persona)}</div>`;
  if (temp !== undefined) html += `<div class="tt-temp">🌡️ Temperature: ${temp}</div>`;
  return html;
}

async function loadDetail() {
  const resp = await fetch(`/api/workflows/${WORKFLOW_ID}`);
  if (!resp.ok) {
    document.getElementById('detailContent').innerHTML = '<div class="loading">❌ Workflow not found</div>';
    return;
  }
  const w = await resp.json();
  document.title = `ClawCrossHub — ${w.title}`;

  const tagsHtml = (w.tags||[]).map(t => `<span class="badge tag">${t}</span>`).join('');
  const dagBadge = w.is_dag ? '<span class="badge dag">⚡ DAG Mode</span>' : '';
  const repeatBadge = w.repeat ? '<span class="badge repeat">🔁 Repeat</span>' : '<span class="badge">▶️ Run Once</span>';
  const stepsHtml = `<span class="badge">📊 ${w.steps} steps</span>`;
  const sourceLabel = w.source === 'preset' ? '🏷️ Official' : '🌐 Community';

  const expertChips = (w.experts||[]).map(e => {
    const emoji = TAG_EMOJI[e] || '⭐';
    return `<span class="expert-chip">${emoji} ${e}</span>`;
  }).join('');

  // Build experts detail map for tooltip lookup
  expertsDetailMap = {};
  const detailList = w.experts_detail || [];
  detailList.forEach(e => {
    if (e && e.tag) expertsDetailMap[e.tag] = e;
    // Also map by name for custom agents (custom#oasis#name pattern)
    if (e && e.name) expertsDetailMap[e.name] = e;
  });
  // Also try to map from internal_agents with expert info
  (w.internal_agents || w.oasis_agents || []).forEach(a => {
    if (a && a.name && !expertsDetailMap[a.name]) {
      expertsDetailMap[a.name] = {name: a.name, tag: a.tag || '', persona: a.persona || '', temperature: a.temperature};
    }
  });

  // Build flow diagram
  const flowNodes = parseYamlToFlowNodes(w.yaml_content);

  // Build agent detail section (to be placed below diagram)
  const agentDetailHtml = buildAgentDetailSection(w, parseYamlToFlowNodes(w.yaml_content));

  document.getElementById('detailContent').innerHTML = `
    <div class="detail-header">
      <div class="detail-icon">${w.icon||'📦'}</div>
      <div class="detail-info">
        <h1>${escHtml(w.title)}</h1>
        <div class="author">by ${escHtml(w.author)} · ${sourceLabel} · ⭐ ${w.stars||0} stars · 🔀 ${w.forks||0} forks</div>
        <div class="desc">${escHtml(w.description)}</div>
      </div>
    </div>

    <div class="action-bar">
      <button class="btn btn-star" onclick="starWorkflow()">⭐ Star</button>
      <button class="btn btn-primary" onclick="copyYaml()">📋 Copy YAML</button>
      <button class="btn btn-secondary" onclick="downloadZip()">📥 Download ZIP</button>
      <button class="btn btn-secondary" onclick="openInOrchestrator()">🎨 Open in Visual Orchestrator</button>
    </div>

    <div class="meta-badges">${dagBadge}${repeatBadge}${stepsHtml}${tagsHtml}</div>

    ${w.detail ? `<div class="section"><div class="section-header">📖 About this Workflow</div><div class="section-body"><p>${escHtml(w.detail)}</p></div></div>` : ''}

    <div class="section">
      <div class="section-header">🔀 Workflow Diagram</div>
      <div class="section-body">
        <div id="flowGraph" class="flow-graph"></div>
      </div>
    </div>

    <div class="section">
      <div class="section-header">🤖 Agents</div>
      <div class="agent-detail-section" id="agentDetailSection">${agentDetailHtml}</div>
    </div>

    ${w.yaml_content ? `<div class="section">
      <div class="section-header" style="justify-content:space-between">
        <span>📄 YAML Configuration</span>
        <button class="yaml-toggle-btn" onclick="toggleYaml()"><span id="yamlToggleIcon">▶</span> Show YAML</button>
      </div>
      <div class="yaml-section-collapsible" id="yamlCollapsible">
        <div class="yaml-block"><pre id="yamlContent">${escHtml(w.yaml_content)}</pre></div>
      </div>
    </div>` : ''}
  `;

  // Render the node-and-wire flow graph (no floating panel — info is below)
  renderFlowGraph(flowNodes, document.getElementById('flowGraph'), '');

  // Store for copy
  window._yamlContent = w.yaml_content || '';
}

function _parseAgentStr(rawStr) {
  // Parse expert strings like "creative#temp#1", "custom#oasis#test_2", "data#temp#1"
  // Returns {displayName, lookupKeys: [tags to try for tooltip lookup]}
  const parts = rawStr.split('#');
  const tag = parts[0];
  if (tag === 'custom' && parts.length >= 3) {
    // custom#oasis#agentName — show agent name, look up by name
    const agentName = parts.slice(2).join('#');
    return { displayName: agentName, lookupKeys: [agentName, rawStr, tag] };
  }
  return { displayName: tag, lookupKeys: [tag] };
}

function parseYamlToFlowNodes(yamlStr) {
  // Parse YAML workflow into structured node/edge data for rendering
  // Returns { nodes: [...], dagEdges: [[sourceId, targetId], ...] | null }
  try {
    const lines = (yamlStr||'').split('\n');
    let nodes = [];
    let inParallel = false;
    let parallelItems = [];
    let nodeId = 0;
    let dagEdges = null; // null = linear mode; array = DAG mode
    let inEdges = false;
    let edgePair = [];
    let dagIdMap = {}; // dagId -> node id

    for (const line of lines) {
      const trimmed = line.trim();

      // Detect edges: section
      if (trimmed === 'edges:') {
        inEdges = true;
        inParallel = false;
        dagEdges = [];
        continue;
      }

      if (inEdges) {
        // Parse edge pairs like:  - - on1 /   - on2
        if (trimmed.startsWith('- - ')) {
          // Start of new edge pair
          if (edgePair.length === 2) dagEdges.push([...edgePair]);
          edgePair = [trimmed.replace('- - ', '').trim()];
        } else if (trimmed.startsWith('- ') && edgePair.length === 1) {
          edgePair.push(trimmed.replace('- ', '').trim());
        }
        continue;
      }

      if (trimmed.startsWith('- expert:')) {
        const raw = trimmed.replace('- expert:', '').trim().replace(/"/g, '');
        const info = _parseAgentStr(raw);
        if (inParallel) {
          parallelItems.push(info);
        } else {
          nodes.push({id: 'n'+(nodeId++), type:'expert', displayName: info.displayName, lookupKeys: info.lookupKeys});
        }
      } else if (trimmed.startsWith('- parallel:')) {
        inParallel = true;
        parallelItems = [];
      } else if (trimmed.startsWith('- "') && inParallel) {
        const rawP = trimmed.replace(/^- "/, '').replace(/"$/, '');
        parallelItems.push(_parseAgentStr(rawP));
      } else if (trimmed.startsWith('- all_experts:')) {
        nodes.push({id: 'n'+(nodeId++), type:'all', displayName:'All Experts', lookupKeys:[]});
      } else if (trimmed.startsWith('- manual:') || trimmed.startsWith('manual:')) {
        if (!inParallel) {
          nodes.push({id: 'n'+(nodeId++), type:'manual', displayName:'Manual', lookupKeys:[]});
        }
      } else if (trimmed.startsWith('- id:')) {
        const dagId = trimmed.replace('- id:', '').trim();
        const nid = 'n'+(nodeId++);
        nodes.push({id: nid, type:'dag_start', displayName: dagId, dagId: dagId, lookupKeys:[]});
        dagIdMap[dagId] = nid;
      } else if (trimmed.startsWith('expert:') && nodes.length > 0 && nodes[nodes.length-1].type === 'dag_start') {
        const rawDag = trimmed.replace('expert:', '').trim().replace(/"/g, '');
        const dagInfo = _parseAgentStr(rawDag);
        const prev = nodes[nodes.length-1];
        prev.type = 'expert';
        prev.displayName = dagInfo.displayName;
        prev.lookupKeys = dagInfo.lookupKeys;
        prev.label = prev.dagId; // keep dag id as sub-label
      }

      // Close parallel group
      if (inParallel && (trimmed.startsWith('- expert:') || trimmed.startsWith('- all_experts:') || trimmed.startsWith('- manual:') || trimmed === '') && !trimmed.startsWith('- "') && !trimmed.startsWith('- parallel:') && trimmed !== '' && !line.startsWith('      ')) {
        if (parallelItems.length > 0) {
          const groupId = 'g'+(nodeId++);
          const children = parallelItems.map(info => ({id: 'n'+(nodeId++), type:'expert', displayName: info.displayName, lookupKeys: info.lookupKeys, groupId}));
          nodes.push({id: groupId, type:'parallel_group', children});
          parallelItems = [];
          inParallel = false;
          // Re-process current line
          if (trimmed.startsWith('- expert:')) {
            const rawRe = trimmed.replace('- expert:', '').trim().replace(/"/g, '');
            const reInfo = _parseAgentStr(rawRe);
            nodes.push({id: 'n'+(nodeId++), type:'expert', displayName: reInfo.displayName, lookupKeys: reInfo.lookupKeys});
          }
        }
      }
    }

    // Flush remaining edge pair
    if (edgePair.length === 2 && dagEdges) dagEdges.push([...edgePair]);

    // Flush remaining parallel items
    if (inParallel && parallelItems.length > 0) {
      const groupId = 'g'+(nodeId++);
      const children = parallelItems.map(info => ({id: 'n'+(nodeId++), type:'expert', displayName: info.displayName, lookupKeys: info.lookupKeys, groupId}));
      nodes.push({id: groupId, type:'parallel_group', children});
    }

    // Convert dagEdges from dagId to node id
    if (dagEdges) {
      dagEdges = dagEdges.map(([src, tgt]) => [dagIdMap[src] || src, dagIdMap[tgt] || tgt]).filter(([s,t]) => s && t);
    }

    return { nodes, dagEdges, dagIdMap };
  } catch(e) {
    return { nodes: [], dagEdges: null, dagIdMap: {} };
  }
}

function renderFlowGraph(parsed, container, panelHtml) {
  // Render a Clawcross-style node + wire graph using topological level layout
  const nodes = parsed.nodes || [];
  const dagEdges = parsed.dagEdges; // null = linear, array = DAG
  if (!container || !nodes.length) {
    container.innerHTML = '<span style="color:var(--text2)">No diagram available</span>';
    return;
  }

  // ── Clawcross-style layout constants ──
  const NW = 160, NH = 56, MARGIN_X = 60, MARGIN_Y = 40, GAP_X = 240, GAP_Y = 80;

  // Step 1: Flatten all nodes (expand parallel_group children) and build edges
  let flatNodes = []; // {id, displayName, type, lookupKeys, label, groupId?}
  let edges = [];
  let groupMeta = {}; // groupId -> {childIds}
  let prevIds = [];

  nodes.forEach((step) => {
    if (step.type === 'parallel_group') {
      const children = step.children || [];
      let childIds = [];
      children.forEach((child) => {
        flatNodes.push({
          id: child.id, displayName: child.displayName, type: 'parallel',
          lookupKeys: child.lookupKeys, label: child.label, groupId: step.id
        });
        childIds.push(child.id);
      });
      groupMeta[step.id] = { childIds, label: '⚡ Parallel' };
      if (!dagEdges) {
        prevIds.forEach(pid => childIds.forEach(cid => edges.push({sourceId: pid, targetId: cid})));
      }
      prevIds = childIds;
    } else {
      flatNodes.push({
        id: step.id, displayName: step.displayName, type: step.type,
        lookupKeys: step.lookupKeys, label: step.label || step.dagId
      });
      if (!dagEdges) {
        prevIds.forEach(pid => edges.push({sourceId: pid, targetId: step.id}));
      }
      prevIds = [step.id];
    }
  });

  if (dagEdges && dagEdges.length) {
    dagEdges.forEach(([src, tgt]) => edges.push({sourceId: src, targetId: tgt}));
  }

  // Step 2: Topological layer assignment (longest-path from sources)
  const nodeById = {};
  flatNodes.forEach(n => nodeById[n.id] = n);
  const preds = {}, succs = {};
  flatNodes.forEach(n => { preds[n.id] = []; succs[n.id] = []; });
  edges.forEach(e => {
    if (preds[e.targetId]) preds[e.targetId].push(e.sourceId);
    if (succs[e.sourceId]) succs[e.sourceId].push(e.targetId);
  });

  const layerOf = {};
  const visiting = new Set();
  function getLayer(nid) {
    if (layerOf[nid] !== undefined) return layerOf[nid];
    if (visiting.has(nid)) { layerOf[nid] = 0; return 0; } // cycle guard
    visiting.add(nid);
    const deps = preds[nid] || [];
    layerOf[nid] = deps.length === 0 ? 0 : Math.max(...deps.map(d => getLayer(d))) + 1;
    visiting.delete(nid);
    return layerOf[nid];
  }
  flatNodes.forEach(n => getLayer(n.id));

  // Step 3: Group nodes by layer, then barycenter sort to minimize crossing
  const layers = {};
  flatNodes.forEach(n => {
    const lv = layerOf[n.id] || 0;
    if (!layers[lv]) layers[lv] = [];
    layers[lv].push(n);
  });

  const nodeY = {};
  const sortedLevels = Object.keys(layers).map(Number).sort((a,b) => a - b);
  sortedLevels.forEach(lv => {
    const items = layers[lv];
    if (lv > 0) {
      // Barycenter ordering: sort by average Y of predecessors
      items.sort((a, b) => {
        const aYs = (preds[a.id]||[]).map(d => nodeY[d]).filter(y => y !== undefined);
        const bYs = (preds[b.id]||[]).map(d => nodeY[d]).filter(y => y !== undefined);
        const aAvg = aYs.length ? aYs.reduce((s,v) => s+v, 0) / aYs.length : 0;
        const bAvg = bYs.length ? bYs.reduce((s,v) => s+v, 0) / bYs.length : 0;
        return aAvg - bAvg;
      });
      layers[lv] = items;
    }
    const count = items.length;
    const totalH = (count - 1) * GAP_Y;
    const yStart = MARGIN_Y + Math.max(0, (380 - totalH) / 2);
    items.forEach((n, i) => { nodeY[n.id] = yStart + i * GAP_Y; });
  });

  // Step 4: Assign final x,y coordinates to layout nodes
  let layoutNodes = [];
  flatNodes.forEach(n => {
    const lv = layerOf[n.id] || 0;
    const x = MARGIN_X + lv * GAP_X;
    const y = nodeY[n.id] || MARGIN_Y;
    layoutNodes.push({
      id: n.id, x, y, w: NW, h: NH,
      displayName: n.displayName, type: n.type,
      lookupKeys: n.lookupKeys, label: n.label, groupId: n.groupId
    });
  });

  // Step 5: Draw group rectangles around parallel children
  Object.entries(groupMeta).forEach(([gid, meta]) => {
    const childNodes = layoutNodes.filter(n => meta.childIds.includes(n.id));
    if (!childNodes.length) return;
    const groupPad = 14;
    const minX = Math.min(...childNodes.map(c => c.x));
    const minY = Math.min(...childNodes.map(c => c.y));
    const maxX = Math.max(...childNodes.map(c => c.x + c.w));
    const maxY = Math.max(...childNodes.map(c => c.y + c.h));
    layoutNodes.push({
      id: gid, x: minX - groupPad, y: minY - groupPad,
      w: maxX - minX + groupPad * 2, h: maxY - minY + groupPad * 2,
      type: '_group', groupLabel: meta.label
    });
  });

  // Calculate total dimensions
  let totalW = MARGIN_X, totalH = MARGIN_Y;
  layoutNodes.forEach(n => {
    totalW = Math.max(totalW, n.x + n.w + MARGIN_X);
    totalH = Math.max(totalH, n.y + n.h + MARGIN_Y);
  });

  // Build HTML — wrap everything in flow-graph-inner for pan/zoom transform
  let html = '';

  // Inner container that receives transform
  html += `<div class="flow-graph-inner" style="width:${totalW}px;height:${totalH}px">`;

  // SVG for edges
  html += `<svg class="flow-edges" width="${totalW}" height="${totalH}" xmlns="http://www.w3.org/2000/svg">`;
  html += '<defs><marker id="fg-arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="#58a6ff"/></marker>';
  html += '<marker id="fg-arrow-green" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="#3fb950"/></marker></defs>';

  // Draw edges as bezier curves
  const nodeMap = {};
  layoutNodes.forEach(n => nodeMap[n.id] = n);
  edges.forEach(e => {
    const s = nodeMap[e.sourceId], t = nodeMap[e.targetId];
    if (!s || !t) return;
    const x1 = s.x + s.w, y1 = s.y + s.h / 2;
    const x2 = t.x, y2 = t.y + t.h / 2;
    const cpx = (x1 + x2) / 2;
    const isParallel = t.type === 'parallel' || s.type === 'parallel';
    const color = isParallel ? '#3fb950' : '#58a6ff';
    const marker = isParallel ? 'url(#fg-arrow-green)' : 'url(#fg-arrow)';
    html += `<path d="M${x1},${y1} C${cpx},${y1} ${cpx},${y2} ${x2},${y2}" stroke="${color}" stroke-width="2" fill="none" marker-end="${marker}" opacity="0.7"/>`;
  });
  html += '</svg>';

  // Draw group rectangles
  layoutNodes.filter(n => n.type === '_group').forEach(g => {
    html += `<div class="fg-group" style="left:${g.x}px;top:${g.y}px;width:${g.w}px;height:${g.h}px"><span class="fg-group-label">${g.groupLabel||''}</span></div>`;
  });

  // Draw nodes
  layoutNodes.filter(n => n.type !== '_group').forEach(n => {
    const keys = n.lookupKeys || [n.displayName];
    const firstKey = keys[0] || n.displayName;
    const emoji = TAG_EMOJI[firstKey] || TAG_EMOJI[n.displayName] || '⭐';
    let cls = 'fg-node';
    if (n.type === 'parallel') cls += ' parallel-node';
    else if (n.type === 'manual') cls += ' manual-node';
    else if (n.type === 'all') cls += ' all-node';

    // Build tooltip
    let tt = '';
    for (const k of keys) { tt = buildTooltipHtml(k); if (tt) break; }

    const tagLabel = n.label ? `<div class="fg-tag">${escHtml(n.label)}</div>` : (firstKey !== n.displayName ? `<div class="fg-tag">${escHtml(firstKey)}</div>` : '');

    html += `<div class="${cls}" style="left:${n.x}px;top:${n.y}px;width:${n.w}px;height:${n.h}px">`;
    html += `<div class="fg-port port-in"></div>`;
    html += `<span class="fg-emoji">${emoji}</span>`;
    html += `<div class="fg-info"><div class="fg-name">${escHtml(n.displayName)}</div>${tagLabel}</div>`;
    html += `<div class="fg-port port-out"></div>`;
    if (tt) html += `<div class="agent-tooltip">${tt}</div>`;
    html += '</div>';
  });

  html += '</div>'; // close flow-graph-inner

  // Navigation controls (zoom / reset)
  html += `<div class="fg-nav">
    <button onclick="fgZoom(-0.15)" title="Zoom out">−</button>
    <span class="fg-zoom-label" id="fgZoomLabel">100%</span>
    <button onclick="fgZoom(0.15)" title="Zoom in">+</button>
    <button onclick="fgResetView()" title="Reset view">⌂</button>
  </div>`;

  // Floating info panel (collapsible, top-right) — starts collapsed
  if (panelHtml) {
    html += `<div class="fg-panel collapsed" id="fgPanel">
      <div class="fg-panel-toggle" onclick="toggleFgPanel()">
        <span class="toggle-label">ℹ️ Info</span>
        <span class="toggle-icon" id="fgPanelIcon">ℹ</span>
      </div>
      <div class="fg-panel-body">${panelHtml}</div>
    </div>`;
  }

  container.innerHTML = html;

  // Initialize canvas pan/zoom interaction
  initFlowCanvas(container);
}

// ── Flow canvas pan/zoom state ──
const fgState = { zoom: 1, panX: 0, panY: 0, panning: null };

function toggleFgPanel() {
  const panel = document.getElementById('fgPanel');
  if (!panel) return;
  panel.classList.toggle('collapsed');
  const icon = document.getElementById('fgPanelIcon');
  if (icon) icon.textContent = panel.classList.contains('collapsed') ? 'ℹ' : '▾';
}

function fgApplyTransform() {
  const inner = document.querySelector('.flow-graph-inner');
  if (inner) inner.style.transform = `translate(${fgState.panX}px, ${fgState.panY}px) scale(${fgState.zoom})`;
  const label = document.getElementById('fgZoomLabel');
  if (label) label.textContent = Math.round(fgState.zoom * 100) + '%';
}

function fgZoom(delta) {
  const container = document.getElementById('flowGraph');
  if (!container) return;
  const rect = container.getBoundingClientRect();
  const mx = rect.width / 2, my = rect.height / 2;
  const oldZoom = fgState.zoom;
  fgState.zoom = Math.min(3, Math.max(0.15, oldZoom + delta));
  fgState.panX = mx - (mx - fgState.panX) * (fgState.zoom / oldZoom);
  fgState.panY = my - (my - fgState.panY) * (fgState.zoom / oldZoom);
  fgApplyTransform();
}

function fgResetView() {
  fgState.zoom = 1; fgState.panX = 0; fgState.panY = 0;
  fgApplyTransform();
}

function initFlowCanvas(container) {
  // Reset state
  fgState.zoom = 1; fgState.panX = 0; fgState.panY = 0;

  // Auto-fit: scale so the graph fits within the container
  const inner = container.querySelector('.flow-graph-inner');
  if (inner) {
    const cw = container.offsetWidth || 600;
    const ch = container.offsetHeight || 280;
    const iw = parseInt(inner.style.width) || cw;
    const ih = parseInt(inner.style.height) || ch;
    const fitZoom = Math.min(cw / iw, ch / ih, 1);
    if (fitZoom < 1) {
      fgState.zoom = fitZoom * 0.9; // 90% of perfect fit, leave some margin
      fgState.panX = (cw - iw * fgState.zoom) / 2;
      fgState.panY = (ch - ih * fgState.zoom) / 2;
    } else {
      fgState.panX = (cw - iw) / 2;
      fgState.panY = (ch - ih) / 2;
    }
    fgApplyTransform();
  }

  // Mouse wheel → zoom (centered on cursor), but allow scroll inside panel
  container.addEventListener('wheel', e => {
    if (e.target.closest && e.target.closest('.fg-panel')) return;
    e.preventDefault();
    const rect = container.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const oldZoom = fgState.zoom;
    const delta = e.deltaY > 0 ? -0.08 : 0.08;
    fgState.zoom = Math.min(3, Math.max(0.15, oldZoom + delta));
    fgState.panX = mx - (mx - fgState.panX) * (fgState.zoom / oldZoom);
    fgState.panY = my - (my - fgState.panY) * (fgState.zoom / oldZoom);
    fgApplyTransform();
  }, { passive: false });

  // Mouse drag → pan canvas
  container.addEventListener('mousedown', e => {
    // Only left-click or middle-click on blank area
    if (e.button !== 0 && e.button !== 1) return;
    const tgt = e.target;
    const isBlank = tgt === container || tgt.classList.contains('flow-graph-inner') || tgt.tagName === 'svg';
    if (e.button === 0 && !isBlank) return; // left-click on node, ignore
    e.preventDefault();
    fgState.panning = { startX: e.clientX, startY: e.clientY, origPanX: fgState.panX, origPanY: fgState.panY };
    container.classList.add('fg-grabbing');
  });

  document.addEventListener('mousemove', e => {
    if (!fgState.panning) return;
    const p = fgState.panning;
    fgState.panX = p.origPanX + (e.clientX - p.startX);
    fgState.panY = p.origPanY + (e.clientY - p.startY);
    fgApplyTransform();
  });

  document.addEventListener('mouseup', () => {
    if (fgState.panning) {
      fgState.panning = null;
      container.classList.remove('fg-grabbing');
    }
  });

  // Touch support (mobile)
  let touchState = null;
  container.addEventListener('touchstart', e => {
    if (e.touches.length === 2) {
      // Pinch zoom
      e.preventDefault();
      const t0 = e.touches[0], t1 = e.touches[1];
      const dist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY);
      touchState = { mode: 'zoom', initDist: dist, initZoom: fgState.zoom, initPanX: fgState.panX, initPanY: fgState.panY,
        mx: (t0.clientX + t1.clientX) / 2, my: (t0.clientY + t1.clientY) / 2 };
    } else if (e.touches.length === 1) {
      const t = e.touches[0];
      const target = document.elementFromPoint(t.clientX, t.clientY);
      const isBlank = target === container || (target && target.classList.contains('flow-graph-inner'));
      if (isBlank) {
        e.preventDefault();
        fgState.panning = { startX: t.clientX, startY: t.clientY, origPanX: fgState.panX, origPanY: fgState.panY };
        touchState = { mode: 'pan' };
      }
    }
  }, { passive: false });

  container.addEventListener('touchmove', e => {
    if (!touchState) return;
    e.preventDefault();
    if (touchState.mode === 'zoom' && e.touches.length >= 2) {
      const t0 = e.touches[0], t1 = e.touches[1];
      const dist = Math.hypot(t1.clientX - t0.clientX, t1.clientY - t0.clientY);
      const scale = dist / touchState.initDist;
      const newZoom = Math.min(3, Math.max(0.15, touchState.initZoom * scale));
      const rect = container.getBoundingClientRect();
      const mx = touchState.mx - rect.left;
      const my = touchState.my - rect.top;
      fgState.zoom = newZoom;
      fgState.panX = mx - (mx - touchState.initPanX) * (newZoom / touchState.initZoom);
      fgState.panY = my - (my - touchState.initPanY) * (newZoom / touchState.initZoom);
      fgApplyTransform();
    } else if (touchState.mode === 'pan' && fgState.panning) {
      const t = e.touches[0];
      const p = fgState.panning;
      fgState.panX = p.origPanX + (t.clientX - p.startX);
      fgState.panY = p.origPanY + (t.clientY - p.startY);
      fgApplyTransform();
    }
  }, { passive: false });

  container.addEventListener('touchend', () => {
    fgState.panning = null;
    touchState = null;
  }, { passive: false });
}

async function starWorkflow() {
  await fetch(`/api/workflows/${WORKFLOW_ID}/star`, {method:'POST'});
  loadDetail();
}

function copyYaml() {
  navigator.clipboard.writeText(window._yamlContent || '').then(() => alert('✅ YAML copied to clipboard!'));
}

function downloadZip() {
  window.location = `/api/workflows/${WORKFLOW_ID}/download`;
}

function toggleYaml() {
  const el = document.getElementById('yamlCollapsible');
  const icon = document.getElementById('yamlToggleIcon');
  const btn = icon.parentElement;
  if (el.classList.contains('open')) {
    el.classList.remove('open');
    icon.textContent = '▶';
    btn.innerHTML = '<span id="yamlToggleIcon">▶</span> Show YAML';
  } else {
    el.classList.add('open');
    icon.textContent = '▼';
    btn.innerHTML = '<span id="yamlToggleIcon">▼</span> Hide YAML';
  }
}

function buildAgentDetailSection(w, parsed) {
  // Build agent info section grouped by agent SOURCE TYPE:
  // Oasis, OpenClaw, External, Custom - with collapsible persona
  const expertsList = w.experts_detail || [];
  const internalAgents = w.internal_agents || w.oasis_agents || [];
  let ocList = w.external_agents || w.openclaw_agents || [];
  if (!Array.isArray(ocList) && typeof ocList === 'object') {
    ocList = Object.entries(ocList).map(([k,v]) => ({name:k, ...v}));
  }

  // Scan YAML for stage→expert mapping
  const yamlStageMap = {};
  try {
    const yamlLines = (w.yaml_content || '').split('\n');
    let currentId = '';
    for (const line of yamlLines) {
      const t = line.trim();
      if (t.startsWith('- id:')) currentId = t.replace('- id:', '').trim();
      if (t.startsWith('expert:') || t.startsWith('- expert:')) {
        const raw = t.replace('- expert:', '').replace('expert:', '').trim().replace(/"/g, '');
        const tag = raw.split('#')[0];
        if (tag && currentId) {
          if (!yamlStageMap[tag]) yamlStageMap[tag] = [];
          if (!yamlStageMap[tag].includes(currentId)) yamlStageMap[tag].push(currentId);
        }
      }
    }
  } catch(e) {}

  // Parse nodes for supplementary stage mapping
  const tagToNodes = {};
  (parsed.nodes || []).forEach(n => {
    if (n.type === 'parallel_group') {
      (n.children || []).forEach(c => {
        const tag = (c.lookupKeys && c.lookupKeys[0]) || c.displayName;
        if (tag) { if (!tagToNodes[tag]) tagToNodes[tag] = []; if (n.dagId) tagToNodes[tag].push(n.dagId); }
      });
    } else if (n.lookupKeys && n.lookupKeys.length) {
      const tag = n.lookupKeys[0];
      if (!tagToNodes[tag]) tagToNodes[tag] = [];
      if (n.dagId || n.label) tagToNodes[tag].push(n.dagId || n.label || n.displayName);
    }
  });

  const TAG_CAT = {'creative':'🎨','critical':'🔍','data':'📊','synthesis':'🎯','economist':'📈','entrepreneur':'🚀','lawyer':'⚖️','cost_controller':'💰','revenue_planner':'📊','common_person':'🧑'};

  // Parse skills_info and cron_jobs from workflow data
  const skillsInfo = w.skills_info || {};
  const cronJobs = w.cron_jobs || {};

  // Helper: get skills for a given agent name
  function getAgentSkills(agentName) {
    // Direct match
    if (skillsInfo[agentName]) return skillsInfo[agentName];
    // Try matching by lowercase
    const lowerName = (agentName||'').toLowerCase();
    for (const key of Object.keys(skillsInfo)) {
      if (key.toLowerCase() === lowerName) return skillsInfo[key];
    }
    return null;
  }

  // Helper: get cron jobs for a given agent name
  function getAgentCronJobs(agentName) {
    if (cronJobs[agentName]) return cronJobs[agentName];
    const lowerName = (agentName||'').toLowerCase();
    for (const key of Object.keys(cronJobs)) {
      if (key.toLowerCase() === lowerName) return cronJobs[key];
    }
    return [];
  }

  // ── Classify all agents into 4 groups ──
  const oasisAgents = [];
  const openclawAgents = [];
  const externalAgents = [];
  const customAgents = [];

  // 1) Experts from experts_detail → Oasis Agents
  const oasisTags = new Set();
  expertsList.forEach(e => {
    const tag = e.tag || 'unknown';
    oasisTags.add(tag);
    oasisAgents.push({ name: e.name||e.name_en||tag, tag, emoji: TAG_CAT[tag]||TAG_EMOJI[tag]||'⭐', persona: e.persona||'', temperature: e.temperature, stages: yamlStageMap[tag]||tagToNodes[tag]||[], sourceType:'oasis', agentSkills: getAgentSkills(e.name||e.name_en||tag), agentCronJobs: getAgentCronJobs(e.name||e.name_en||tag) });
  });

  // 2) From ocList → split into openclaw vs external
  ocList.forEach(entry => {
    const isOC = entry.tag==='openclaw' || entry.workspace_files || (entry.config && entry.config.workspace_files);
    const aName = entry.name || '?';
    const ws = entry.workspace_files || {};
    const identity = (ws['IDENTITY.md']||'').split('\\n').filter(l=>l.trim()).slice(0,5).join(' ');
    const skills = (entry.config?.skills||[]).join(', ') || (entry.config?.skills_all ? 'all' : '');
    const agent = { name: aName, tag: entry.tag||(isOC?'openclaw':'external'), emoji: isOC?'🐾':'🔗', persona: identity, skills, stages: yamlStageMap[aName]||yamlStageMap[entry.tag]||[], config: entry.config||{}, sourceType: isOC?'openclaw':'external', agentSkills: getAgentSkills(aName), agentCronJobs: getAgentCronJobs(aName) };
    if (isOC) openclawAgents.push(agent); else externalAgents.push(agent);
  });

  // 3) Internal agents not already in oasis → Custom
  internalAgents.forEach(a => {
    if (oasisTags.has(a.tag)) return;
    if ((a.session||'').startsWith('oc_')) return;
    customAgents.push({ name: a.name||a.tag||'?', tag: a.tag||'custom', emoji: TAG_EMOJI[a.tag]||'✨', persona: a.persona||'', temperature: a.temperature, stages: yamlStageMap[a.tag]||yamlStageMap[a.name]||[], sourceType:'custom', agentSkills: getAgentSkills(a.name||a.tag), agentCronJobs: getAgentCronJobs(a.name||a.tag) });
  });

  let _uid = 0;

  // Helper: build a single agent card with collapsible persona
  function agentCard(a) {
    const uid = 'ap' + (++_uid);
    const badgeCls = 'badge-' + a.sourceType;
    const badgeLbl = {oasis:'OASIS',openclaw:'OPENCLAW',external:'EXTERNAL',custom:'CUSTOM'}[a.sourceType]||'AGENT';
    let h = '<div class="agent-card">';
    h += '<div class="agent-card-top">';
    h += '<div class="agent-card-icon">' + a.emoji + '</div>';
    h += '<div><div class="agent-card-name">' + escHtml(a.name) + '</div><div class="agent-card-tag">' + escHtml(a.tag) + '</div></div>';
    h += '<span class="agent-card-type-label agent-type-badge ' + badgeCls + '">' + badgeLbl + '</span>';
    h += '</div>';
    h += '<div class="agent-card-body">';
    h += '<div class="agent-card-config">';
    if (a.temperature !== undefined) h += '<span class="agent-config-badge"><span class="cfg-icon">🌡️</span> Temp: <span class="cfg-val">' + a.temperature + '</span></span>';
    if (a.skills) h += '<span class="agent-config-badge"><span class="cfg-icon">🛠️</span> Skills: <span class="cfg-val">' + escHtml((a.skills+'').slice(0,60)) + '</span></span>';
    h += '</div>';
    if (a.persona) {
      h += '<div class="agent-persona-toggle" onclick="var p=document.getElementById(\'' + uid + '\');p.classList.toggle(\'show\');this.classList.toggle(\'open\')">';
      h += '<span class="persona-arrow">▶</span> <span>🎭 Show Persona</span></div>';
      h += '<div class="agent-card-persona" id="' + uid + '">' + escHtml(a.persona) + '</div>';
    }
    if (a.stages && a.stages.length) {
      h += '<div class="agent-card-row"><span class="row-label">📍 Stages</span></div>';
      h += '<div class="agent-node-list">';
      a.stages.forEach(function(sid) { h += '<span class="agent-node-chip">' + escHtml(sid) + '</span>'; });
      h += '</div>';
    }
    // Skills section
    if (a.agentSkills && typeof a.agentSkills === 'object') {
      const skillEntries = Object.entries(a.agentSkills);
      if (skillEntries.length > 0) {
        h += '<div class="agent-skills-section">';
        h += '<div class="agent-skills-title">🛠️ Skills (' + skillEntries.length + ')</div>';
        skillEntries.forEach(function([skillName, skillData]) {
          h += '<div class="agent-skill-item">';
          h += '<span class="agent-skill-name">' + escHtml(skillName) + '</span>';
          const meta = skillData.meta || {};
          const origin = skillData.origin || {};
          h += '<div class="agent-skill-meta">';
          if (meta.version) h += '<span>📦 v' + escHtml(meta.version) + '</span>';
          if (meta.slug) h += '<span>🏷️ ' + escHtml(meta.slug) + '</span>';
          if (origin.registry) h += '<span class="agent-skill-registry">🌐 ' + escHtml(origin.registry) + '</span>';
          if (origin.installedVersion) h += '<span>📥 v' + escHtml(origin.installedVersion) + '</span>';
          h += '</div></div>';
        });
        h += '</div>';
      }
    }
    // Cron Jobs section
    if (a.agentCronJobs && Array.isArray(a.agentCronJobs) && a.agentCronJobs.length > 0) {
      h += '<div class="agent-cron-section">';
      h += '<div class="agent-cron-title">⏰ Cron Jobs (' + a.agentCronJobs.length + ')</div>';
      a.agentCronJobs.forEach(function(job) {
        h += '<div class="agent-cron-item">';
        h += '<div style="display:flex;align-items:center;gap:6px">';
        h += '<span class="agent-cron-name">' + escHtml(job.name || 'Unnamed Job') + '</span>';
        h += '<span class="' + (job.enabled ? 'agent-cron-badge-enabled' : 'agent-cron-badge-disabled') + '">' + (job.enabled ? '● ENABLED' : '○ DISABLED') + '</span>';
        h += '</div>';
        h += '<div class="agent-cron-detail">';
        if (job.scheduleKind) h += '<span>📋 ' + escHtml(job.scheduleKind) + '</span>';
        if (job.cron) h += '<span>🕐 ' + escHtml(job.cron) + '</span>';
        if (job.at) h += '<span>📅 ' + escHtml(new Date(job.at).toLocaleString()) + '</span>';
        if (job.every) h += '<span>🔄 every ' + escHtml(job.every) + '</span>';
        if (job.mode) h += '<span>📢 ' + escHtml(job.mode) + '</span>';
        if (job.session) h += '<span>🔗 ' + escHtml(job.session) + '</span>';
        h += '</div>';
        if (job.message) {
          h += '<div class="agent-cron-msg">💬 ' + escHtml((job.message+'').slice(0,120)) + '</div>';
        }
        h += '</div>';
      });
      h += '</div>';
    }
    h += '</div></div>';
    return h;
  }

  // Helper: build a collapsible type group
  function typeGroup(emoji, title, badgeCls, agents) {
    if (!agents.length) return '';
    const gid = 'atg' + (++_uid);
    let h = '<div class="agent-type-group">';
    h += '<div class="agent-type-header" onclick="var b=document.getElementById(\'' + gid + '\');b.classList.toggle(\'collapsed\');this.classList.toggle(\'collapsed\')">';
    h += '<span class="type-arrow">▼</span>';
    h += '<span class="type-emoji">' + emoji + '</span>';
    h += '<span class="type-title">' + escHtml(title) + '</span>';
    h += '<span class="agent-type-badge ' + badgeCls + '">' + agents.length + '</span>';
    h += '</div>';
    h += '<div class="agent-type-body" id="' + gid + '">';
    h += '<div class="agent-cards-grid">';
    agents.forEach(function(a) { h += agentCard(a); });
    h += '</div></div></div>';
    return h;
  }

  let html = '';
  html += typeGroup('🏛️', 'Oasis Agents', 'badge-oasis', oasisAgents);
  html += typeGroup('🐾', 'OpenClaw Agents', 'badge-openclaw', openclawAgents);
  html += typeGroup('🔗', 'External Agents', 'badge-external', externalAgents);
  html += typeGroup('✨', 'Custom Agents', 'badge-custom', customAgents);

  if (!html) {
    html = '<div style="color:var(--text2);text-align:center;padding:20px">No agents found for this workflow.</div>';
  }

  return html;
}

function renderAgentsSection(w) {
  let html = '';

  // OpenClaw / External agents (Clawcross format: list [{name, tag:"openclaw", config, workspace_files}])
  let ocList = w.external_agents || w.openclaw_agents || [];
  // Support legacy dict format too: {name: {config, workspace_files}}
  if (!Array.isArray(ocList) && typeof ocList === 'object') {
    ocList = Object.entries(ocList).map(([k,v]) => ({name:k, ...v}));
  }
  const openclawAgents = ocList.filter(a => a.tag === 'openclaw' || a.config || a.workspace_files);
  if (openclawAgents.length) {
    let cards = openclawAgents.map(entry => {
      const name = entry.name || '?';
      const ws = entry.workspace_files || {};
      const identity = (ws['IDENTITY.md']||'').split('\\n').filter(l=>l.trim()).slice(0,2).join(' ');
      const skills = (entry.config?.skills||[]).join(', ') || (entry.config?.skills_all ? 'all' : '-');
      return `<div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:12px;min-width:200px">
        <div style="font-weight:600;margin-bottom:4px">🤖 ${escHtml(name)}</div>
        <div style="font-size:12px;color:var(--text2)">${escHtml(identity.slice(0,100))}</div>
        <div style="font-size:11px;color:var(--text2);margin-top:4px">Skills: ${escHtml(skills)}</div>
      </div>`;
    }).join('');
    html += `<div class="section"><div class="section-header">🤖 OpenClaw Agents (${openclawAgents.length})</div><div class="section-body"><div style="display:flex;gap:12px;flex-wrap:wrap">${cards}</div></div></div>`;
  }

  // Internal / OASIS agents (Clawcross format: [{name, tag}])
  const ia = w.internal_agents || w.oasis_agents || [];
  if (Array.isArray(ia) && ia.length) {
    let chips = ia.map(a => {
      const emoji = TAG_EMOJI[a.tag] || '⭐';
      const isOC = (a.session||'').startsWith('oc_');
      const label = isOC ? '🤖' : emoji;
      return `<span class="expert-chip">${label} ${escHtml(a.name||a.tag||'?')} <span style="font-size:10px;color:var(--text2);margin-left:4px">${escHtml(a.tag||'')}</span></span>`;
    }).join('');
    html += `<div class="section"><div class="section-header">🏛️ Internal Agents (${ia.length})</div><div class="section-body"><div class="expert-list">${chips}</div></div></div>`;
  }

  // Expert personas (oasis_experts.json: [{name, tag, persona, temperature}])
  const ex = w.experts || [];
  if (ex.length) {
    let items = ex.map(e => {
      const emoji = TAG_EMOJI[e.tag] || '⭐';
      return `<div style="background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:10px;min-width:180px">
        <div style="font-weight:600;font-size:13px">${emoji} ${escHtml(e.name||e.name_en||e.tag)}</div>
        <div style="font-size:11px;color:var(--text2);margin-top:4px">${escHtml((e.persona||'').slice(0,80))}</div>
        ${e.temperature !== undefined ? `<div style="font-size:10px;color:var(--text2);margin-top:2px">Temp: ${e.temperature}</div>` : ''}
      </div>`;
    }).join('');
    html += `<div class="section"><div class="section-header">🎭 Expert Personas (${ex.length})</div><div class="section-body"><div style="display:flex;gap:10px;flex-wrap:wrap">${items}</div></div></div>`;
  }
  return html;
}

function openInOrchestrator() {
  // Open visual orchestrator (port 51210 or via main frontend)
  const url = 'http://127.0.0.1:51210';
  window.open(url, '_blank');
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s||'';
  return d.innerHTML;
}

loadDetail();
</script>
</body>
</html>"""


# ──────────────────────────────────────────────────────────────
# Entry Point
# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  🌊 ClawCrossHub — Workflow Community Platform")
    print(f"  Open http://127.0.0.1:{CLAWCROSSHUB_PORT} in your browser")
    print("=" * 60)
    app.run(host="0.0.0.0", port=CLAWCROSSHUB_PORT, debug=True)
