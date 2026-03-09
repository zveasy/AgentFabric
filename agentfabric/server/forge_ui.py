"""Lightweight browser UI for AgentForge project workflows."""

from __future__ import annotations


def render_forge_ui() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AgentForge Repository</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --surface: #ffffff;
      --muted: #6b7280;
      --border: #e5e7eb;
      --text: #111827;
      --accent: #2563eb;
      --green: #16a34a;
      --red: #dc2626;
      --ring: rgba(37, 99, 235, 0.16);
      --shadow-soft: 0 1px 2px rgba(15, 23, 42, 0.05);
      --shadow-strong: 0 8px 20px rgba(15, 23, 42, 0.08);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      min-height: 100vh;
    }
    input, textarea, select {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 8px;
      background: var(--surface);
      color: var(--text);
      transition: border-color .15s ease, box-shadow .15s ease;
      font-size: 13px;
    }
    input:focus, textarea:focus, select:focus {
      outline: none;
      border-color: #2563eb;
      box-shadow: 0 0 0 4px var(--ring);
    }
    button {
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text);
      background: var(--surface);
      padding: 9px 12px;
      cursor: pointer;
      font-weight: 600;
      transition: transform .05s ease, background .15s ease, border-color .15s ease, box-shadow .15s ease;
      box-shadow: var(--shadow-soft);
    }
    button:hover { background: #f9fafb; border-color: #d1d5db; }
    button:active { transform: translateY(1px); }
    button.primary { background: #111827; border-color: #111827; color: #f9fafb; box-shadow: none; }
    button.primary:hover { background: #1f2937; border-color: #1f2937; }
    button.blue { background: #2563eb; border-color: #1d4ed8; color: #eff6ff; box-shadow: none; }
    button.blue:hover { background: #1d4ed8; }
    button.ghost { background: transparent; border-color: transparent; color: #4b5563; box-shadow: none; }
    .topbar {
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      padding: 12px 20px;
      display: flex;
      align-items: center;
      gap: 12px;
      position: sticky;
      top: 0;
      z-index: 50;
    }
    .logo {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--text);
      background: #f3f4f6;
      border: 1px solid var(--border);
      font-weight: 700;
      box-shadow: none;
    }
    .repo-path { font-size: 15px; font-weight: 600; letter-spacing: .1px; color: var(--text); }
    .topbar .split { flex: 1; }
    .toolbar {
      border-bottom: 1px solid var(--border);
      background: var(--surface);
      padding: 14px 20px;
      display: grid;
      gap: 10px;
      grid-template-columns: 1.9fr 1fr 1fr auto auto;
      align-items: end;
    }
    .field > span {
      display: block;
      font-size: 11px;
      color: var(--muted);
      margin: 0 0 4px;
      font-weight: 600;
      letter-spacing: .3px;
      text-transform: uppercase;
    }
    .tabs {
      border-bottom: 1px solid var(--border);
      display: flex;
      gap: 12px;
      padding: 0 20px;
      background: var(--surface);
    }
    .tab {
      padding: 11px 8px;
      color: var(--muted);
      border-bottom: 2px solid transparent;
      font-size: 14px;
      text-decoration: none;
      font-weight: 600;
    }
    .tab.active { color: var(--text); border-bottom-color: var(--accent); }
    .repo-meta {
      display: flex;
      gap: 8px;
      padding: 10px 20px 2px;
      color: var(--muted);
      font-size: 12px;
      flex-wrap: wrap;
    }
    .chip {
      border: 1px solid var(--border);
      background: var(--surface);
      border-radius: 999px;
      padding: 3px 9px;
    }
    .hero {
      margin: 10px 20px 0;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--surface);
      box-shadow: var(--shadow-soft);
      padding: 14px;
      display: grid;
      grid-template-columns: 1.45fr 1fr;
      gap: 12px;
    }
    .hero h1 {
      margin: 6px 0 8px;
      font-size: 22px;
      color: var(--text);
      line-height: 1.15;
      letter-spacing: -0.4px;
    }
    .hero p {
      margin: 0;
      color: var(--muted);
      line-height: 1.5;
      font-size: 12px;
    }
    .hero-eyebrow {
      font-size: 11px;
      letter-spacing: .5px;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }
    .hero-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .hero-kpi {
      border: 1px solid var(--border);
      border-radius: 10px;
      background: #fafafa;
      padding: 9px;
    }
    .hero-kpi .num { font-size: 19px; font-weight: 700; color: var(--text); line-height: 1.1; }
    .hero-kpi .txt { font-size: 10px; color: var(--muted); text-transform: uppercase; }
    .flow {
      margin: 12px 20px 0;
      border: 1px solid var(--border);
      border-radius: 12px;
      background: var(--surface);
      box-shadow: var(--shadow-soft);
      padding: 12px;
    }
    .flow-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      margin-bottom: 10px;
    }
    .flow-head h2 {
      margin: 0;
      font-size: 16px;
      color: #0f172a;
      letter-spacing: .1px;
    }
    #flowHint {
      color: #475467;
      font-size: 12px;
      font-weight: 600;
    }
    .flow-steps {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-bottom: 2px;
      margin-bottom: 10px;
    }
    .flow-step {
      flex: 1 0 180px;
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px;
      background: #fafafa;
      color: var(--muted);
      font-size: 12px;
      min-height: 56px;
    }
    .flow-step strong {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      font-size: 12px;
      color: var(--text);
      margin-bottom: 2px;
    }
    .flow-state {
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: .4px;
      border-radius: 999px;
      padding: 2px 7px;
      background: #e2e8f0;
      color: #334155;
      border: 1px solid rgba(15, 23, 42, 0.14);
    }
    .flow-step.done {
      border-color: rgba(22, 163, 74, 0.35);
      background: rgba(240, 253, 244, 0.9);
    }
    .flow-step.done .flow-state {
      background: rgba(22, 163, 74, 0.14);
      color: #0f7a35;
      border-color: rgba(22, 163, 74, 0.25);
    }
    .flow-step.active {
      border-color: rgba(37, 99, 235, 0.35);
      background: rgba(239, 246, 255, 0.8);
      box-shadow: none;
    }
    .flow-step.active .flow-state {
      background: rgba(37, 99, 235, 0.14);
      color: #1d4ed8;
      border-color: rgba(37, 99, 235, 0.28);
    }
    .api-map {
      margin: 0;
      white-space: pre-wrap;
      max-height: 180px;
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      background: #f8fafc;
      color: #334155;
      font-size: 11px;
      line-height: 1.45;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }
    .layout {
      display: grid;
      gap: 12px;
      padding: 12px 20px 18px;
      grid-template-columns: 260px minmax(580px, 1fr) 320px;
    }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px;
      box-shadow: var(--shadow-soft);
    }
    .card h3 { margin: 0 0 10px 0; font-size: 15px; letter-spacing: .1px; color: var(--text); }
    .label { color: #667085; font-size: 12px; margin: 8px 0 4px 0; }
    .muted { color: #64748b; font-size: 12px; line-height: 1.45; }
    .helper {
      font-size: 11px;
      color: #64748b;
      margin: 4px 0 8px;
      padding: 2px 0;
      border-radius: 0;
      background: transparent;
      border: 0;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
    }
    .row { display: flex; gap: 8px; }
    .row > * { flex: 1; }
    .pr-stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 8px;
      margin-bottom: 10px;
    }
    .stat {
      border: 1px solid var(--border);
      border-radius: 8px;
      background: #fafafa;
      padding: 8px;
      text-align: center;
    }
    .stat .num { font-size: 18px; font-weight: 700; line-height: 1.1; color: var(--text); }
    .stat .txt { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .4px; }
    .pr-item {
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 10px;
      margin-bottom: 8px;
      background: var(--surface);
      transition: border-color .15s ease, transform .05s ease;
    }
    .pr-item:hover { border-color: #4b5561; transform: translateY(-1px); }
    .pr-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
    .badge {
      padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase;
    }
    .badge.pending { background: #fffbeb; color: #92400e; }
    .badge.evaluated { background: #eff6ff; color: #1d4ed8; }
    .badge.merged { background: #f0fdf4; color: #166534; }
    .badge.rejected { background: #fef2f2; color: #991b1b; }
    .activity {
      max-height: 420px; overflow: auto; background: #f8fafc; border: 1px solid var(--border); border-radius: 8px; padding: 8px;
    }
    .event {
      border-left: 2px solid var(--border); padding: 8px 8px 8px 10px; margin: 6px 0; font-size: 12px; color: #334155;
      white-space: pre-wrap;
    }
    .event.ok { border-color: var(--green); }
    .event.err { border-color: var(--red); }
    #toast {
      position: fixed;
      top: 10px;
      right: 10px;
      width: 360px;
      max-height: 220px;
      overflow: auto;
      z-index: 9999;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      background: var(--surface);
      color: var(--text);
      font-size: 12px;
      white-space: pre-wrap;
      box-shadow: var(--shadow-soft);
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      max-height: 260px;
      overflow: auto;
      background: #f8fafc;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 8px;
      line-height: 1.35;
      color: #0f172a;
    }
    @media (max-width: 1320px) {
      .layout { grid-template-columns: 1fr; }
      .toolbar { grid-template-columns: 1fr 1fr; }
      #toast { width: min(92vw, 360px); }
      .hero { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div id="toast">Last result: Ready.</div>
  <div class="topbar">
    <div class="logo">AF</div>
    <div class="repo-path"><span id="repoPathNs">dev-a</span> / <span id="repoPathProject">research-agent</span></div>
    <div class="split"></div>
    <button class="ghost" id="reloadWorkspace">Sync workspace</button>
  </div>
  <div class="toolbar">
    <label class="field"><span>Auth token</span><input id="token" placeholder="Bearer token (POST /auth/token/issue)" /></label>
    <label class="field"><span>Namespace</span><input id="namespace" value="dev-a" placeholder="namespace" /></label>
    <label class="field"><span>Repository</span><input id="projectId" value="research-agent" placeholder="project id" /></label>
    <button id="listProjects">Browse repos</button>
    <button id="loadWorkspace">Open repo</button>
  </div>
  <div class="tabs">
    <a class="tab" href="#">Code</a>
    <a class="tab active" href="#">Pull requests</a>
    <a class="tab" href="#">Branches</a>
    <a class="tab" href="#">Releases</a>
    <a class="tab" href="#">Settings</a>
  </div>
  <div class="repo-meta">
    <span class="chip">Visibility: Internal</span>
    <span class="chip">Main branch: main</span>
    <span class="chip">Model: Depth-first agent project</span>
    <span class="chip" id="statusFilterLabel">Filter: all pull requests</span>
  </div>
  <section class="hero">
    <div>
      <div class="hero-eyebrow">AgentForge</div>
      <h1>Clean pull-request workflow for agent projects.</h1>
      <p>Branch, submit, evaluate, merge, and confirm release with minimal UI noise.</p>
    </div>
    <div class="hero-grid">
      <div class="hero-kpi"><div class="num" id="heroTotalRepos">1</div><div class="txt">Active repository</div></div>
      <div class="hero-kpi"><div class="num" id="heroOpenPrs">0</div><div class="txt">Open pull requests</div></div>
      <div class="hero-kpi"><div class="num" id="heroMergedPrs">0</div><div class="txt">Merged pull requests</div></div>
      <div class="hero-kpi"><div class="num" id="heroLatestRelease">-</div><div class="txt">Latest stable release</div></div>
    </div>
  </section>
  <section class="flow">
    <div class="flow-head">
      <h2>Coder flow</h2>
      <span id="flowHint">Start by creating/opening a pull request.</span>
    </div>
    <div class="flow-steps">
      <div id="flowStep1" class="flow-step"><strong>1. Branch <span id="flowState1" class="flow-state">pending</span></strong>Create or select a target branch.</div>
      <div id="flowStep2" class="flow-step"><strong>2. Pull request <span id="flowState2" class="flow-state">pending</span></strong>Submit contribution package.</div>
      <div id="flowStep3" class="flow-step"><strong>3. Checks <span id="flowState3" class="flow-state">pending</span></strong>Run automated evaluation gate.</div>
      <div id="flowStep4" class="flow-step"><strong>4. Merge <span id="flowState4" class="flow-state">pending</span></strong>Apply maintainer decision.</div>
    </div>
    <pre class="api-map">UI -> API map
branch: POST /projects/{namespace}/{project_id}/branches
pull request: POST /projects/{namespace}/{project_id}/contributions
checks: POST /projects/{namespace}/{project_id}/contributions/{id}/evaluate
merge/reject: POST /projects/{namespace}/{project_id}/contributions/{id}/review
releases: GET /projects/{namespace}/{project_id}/releases</pre>
  </section>

  <div class="layout">
    <aside class="card">
      <h3>Repository setup</h3>
      <div class="label">Display name</div>
      <input id="displayName" value="Research Agent" />
      <div class="label">Description</div>
      <textarea id="description">Depth-first managed agent project.</textarea>
      <div class="label">Contribution zones (csv)</div>
      <input id="zones" value="prompts,tool_adapters,workflow_steps,domain_packs,safety_constraints" />
      <div class="label">Merge policy JSON</div>
      <textarea id="mergePolicy">{"min_improvements":1,"allowed_latency_regression_pct":5.0,"allowed_cost_regression_pct":5.0,"must_pass_safety":true,"must_pass_regression_tests":true}</textarea>
      <div class="row" style="margin-top:8px;">
        <button class="primary" id="createProject">Initialize repo</button>
        <button id="addMaintainer">Add maintainer</button>
      </div>
      <div class="label">Maintainer principal_id</div>
      <input id="maintainerId" placeholder="contrib-2" />

      <h3 style="margin-top:14px;">Branch</h3>
      <div class="label">New branch name</div>
      <input id="branchName" value="improved-citation-module" />
      <div class="label">Base ref</div>
      <input id="baseRef" value="main" />
      <div class="helper">POST /projects/{namespace}/{project_id}/branches</div>
      <button id="createBranch" style="margin-top:8px;">Create branch</button>
    </aside>

    <section>
      <div class="card">
        <h3>Pull requests (contributions)</h3>
        <div class="pr-stats">
          <div class="stat"><div id="statTotal" class="num">0</div><div class="txt">Total</div></div>
          <div class="stat"><div id="statPending" class="num">0</div><div class="txt">Pending</div></div>
          <div class="stat"><div id="statMerged" class="num">0</div><div class="txt">Merged</div></div>
          <div class="stat"><div id="statRejected" class="num">0</div><div class="txt">Rejected</div></div>
        </div>
        <div class="row">
          <button id="refreshPrs">Refresh pull requests</button>
          <button id="filterRejected">Show rejected only</button>
          <button id="clearFilter">Clear filter</button>
        </div>
        <div id="prList" style="margin-top:10px;"></div>
      </div>

      <div class="card" style="margin-top:12px;">
        <h3>Open pull request</h3>
        <div class="helper">POST /projects/{namespace}/{project_id}/contributions</div>
        <div class="label">Title</div>
        <input id="contribTitle" value="Improve citation quality" />
        <div class="label">Summary</div>
        <textarea id="contribSummary">Adds citation normalization and confidence thresholding.</textarea>
        <div class="row">
          <div>
            <div class="label">Contribution zone</div>
            <select id="contribZone">
              <option>workflow_steps</option>
              <option>tool_adapters</option>
              <option>prompts</option>
              <option>domain_packs</option>
              <option>safety_constraints</option>
            </select>
          </div>
          <div>
            <div class="label">Target branch</div>
            <input id="contribBranch" value="improved-citation-module" />
          </div>
        </div>
        <div class="label">Contribution manifest JSON</div>
        <textarea id="contribManifest">{"what_changed":["citation normalization"],"why_it_matters":"Higher citation precision."}</textarea>
        <div class="row">
          <div>
            <div class="label">Metrics JSON</div>
            <textarea id="contribMetrics">{"improvements":{"accuracy":0.06,"reliability":0.03},"safety_passed":true,"regression_tests_passed":true,"evaluation_score":90.5}</textarea>
          </div>
          <div>
            <div class="label">Regressions JSON</div>
            <textarea id="contribRegressions">{"latency_regression_pct":1.2,"cost_regression_pct":0.7}</textarea>
          </div>
        </div>
        <button class="primary" id="submitContribution">Open pull request</button>
      </div>

      <div class="card" style="margin-top:12px;">
        <h3>Checks and merge</h3>
        <div class="helper">evaluate -> /contributions/{id}/evaluate · review -> /contributions/{id}/review</div>
        <div class="row">
          <div>
            <div class="label">Contribution ID</div>
            <input id="contribId" placeholder="Auto-filled from latest submit" />
          </div>
          <div>
            <div class="label">Decision</div>
            <select id="decision">
              <option value="merge">merge</option>
              <option value="reject">reject</option>
            </select>
          </div>
        </div>
        <div class="row">
          <div>
            <div class="label">Release version</div>
            <input id="releaseVersion" value="1.1.0" />
          </div>
          <div>
            <div class="label">Release channel</div>
            <select id="releaseChannel">
              <option>stable</option>
              <option>beta</option>
              <option>nightly</option>
              <option>enterprise-certified</option>
            </select>
          </div>
        </div>
        <div class="label">Review notes</div>
        <textarea id="decisionNotes">Improves quality without unacceptable regressions.</textarea>
        <div class="row" style="margin-top:8px;">
          <button id="evaluateContribution" class="blue">Run checks</button>
          <button id="reviewContribution" class="primary">Merge pull request</button>
        </div>
      </div>
    </section>

    <aside>
      <div class="card">
        <h3>Releases</h3>
        <button id="listReleases">Refresh releases</button>
        <pre id="releaseList" style="margin-top:8px;">[]</pre>
      </div>
      <div class="card" style="margin-top:12px;">
        <h3>Activity feed</h3>
        <div id="activity" class="activity"></div>
      </div>
      <div class="card" style="margin-top:12px;">
        <h3>Raw API output</h3>
        <pre id="result">Ready.</pre>
      </div>
    </aside>
  </div>

  <script>
    const state = {
      lastContributionId: null,
      statusFilter: null,
      flow: { branchReady: false, prOpened: false, checksPassed: false, merged: false, releaseVisible: false },
    };

    function value(id) { return document.getElementById(id).value.trim(); }
    function jsonValue(id, fallback) { const raw = value(id); return raw ? JSON.parse(raw) : fallback; }

    function ns() { return value("namespace"); }
    function pid() { return value("projectId"); }

    function authHeaders() {
      const headers = { "Content-Type": "application/json" };
      const token = value("token");
      if (token) { headers["Authorization"] = "Bearer " + token; }
      return headers;
    }

    function setResult(label, data, ok = true) {
      const rendered = label + "\\n\\n" + JSON.stringify(data, null, 2);
      document.getElementById("result").textContent = rendered;
      document.getElementById("toast").textContent = "Last result\\n\\n" + rendered;
      logEvent(label, data, ok);
      updateFlowState(label, data, ok);
      renderFlowGuide();
    }

    function logEvent(title, payload, ok = true) {
      const entry = document.createElement("div");
      entry.className = "event " + (ok ? "ok" : "err");
      const stamp = new Date().toISOString();
      entry.textContent = "[" + stamp + "] " + title + "\\n" + JSON.stringify(payload, null, 2);
      const feed = document.getElementById("activity");
      feed.prepend(entry);
    }

    function renderBadge(status) {
      const normalized = (status || "pending").toLowerCase();
      const allowed = ["pending", "evaluated", "merged", "rejected"];
      const klass = allowed.includes(normalized) ? normalized : "pending";
      return "<span class=\\"badge " + klass + "\\">" + normalized + "</span>";
    }

    function updateRepoHeader() {
      document.getElementById("repoPathNs").textContent = ns() || "namespace";
      document.getElementById("repoPathProject").textContent = pid() || "project";
    }

    function updateFlowState(label, data, ok) {
      if (!ok) { return; }
      if (label === "Branch created") { state.flow.branchReady = true; }
      if (label === "Pull request opened") {
        state.flow.branchReady = true;
        state.flow.prOpened = true;
      }
      if (label === "Checks completed" && data && data.gate_passed === true) { state.flow.checksPassed = true; }
      if (label === "Pull request decision applied" && data && data.status === "merged") { state.flow.merged = true; }
      if (label === "Releases refreshed" && data && data.items && data.items.length > 0) { state.flow.releaseVisible = true; }
    }

    function renderFlowGuide() {
      const steps = [
        { id: "flowStep1", done: state.flow.branchReady, active: !state.flow.branchReady },
        { id: "flowStep2", done: state.flow.prOpened, active: state.flow.branchReady && !state.flow.prOpened },
        { id: "flowStep3", done: state.flow.checksPassed, active: state.flow.prOpened && !state.flow.checksPassed },
        { id: "flowStep4", done: state.flow.merged, active: state.flow.checksPassed && !state.flow.merged },
      ];
      steps.forEach(function(step) {
        const node = document.getElementById(step.id);
        node.classList.toggle("done", step.done);
        node.classList.toggle("active", step.active);
      });
      const states = [
        { id: "flowState1", done: steps[0].done, active: steps[0].active },
        { id: "flowState2", done: steps[1].done, active: steps[1].active },
        { id: "flowState3", done: steps[2].done, active: steps[2].active },
        { id: "flowState4", done: steps[3].done, active: steps[3].active },
      ];
      states.forEach(function(step) {
        const node = document.getElementById(step.id);
        if (step.done) { node.textContent = "done"; return; }
        if (step.active) { node.textContent = "active"; return; }
        node.textContent = "pending";
      });
      let hint = "Start by creating/opening a pull request.";
      if (state.flow.branchReady && !state.flow.prOpened) { hint = "Branch ready. Next: open a pull request."; }
      if (state.flow.prOpened && !state.flow.checksPassed) { hint = "PR opened. Next: run checks."; }
      if (state.flow.checksPassed && !state.flow.merged) { hint = "Checks passed. Next: merge the pull request."; }
      if (state.flow.merged && !state.flow.releaseVisible) { hint = "Merged. Next: refresh releases to verify stable release."; }
      if (state.flow.releaseVisible) { hint = "Release confirmed. Flow complete."; }
      document.getElementById("flowHint").textContent = hint;
    }

    function renderPullRequests(items) {
      const root = document.getElementById("prList");
      const totals = { total: 0, pending: 0, evaluated: 0, merged: 0, rejected: 0 };
      (items || []).forEach(function(item) {
        totals.total += 1;
        const status = (item.status || "").toLowerCase();
        if (status === "pending") { totals.pending += 1; }
        if (status === "evaluated") { totals.evaluated += 1; }
        if (status === "merged") { totals.merged += 1; }
        if (status === "rejected") { totals.rejected += 1; }
      });
      document.getElementById("statTotal").textContent = String(totals.total);
      document.getElementById("statPending").textContent = String(totals.pending);
      document.getElementById("statMerged").textContent = String(totals.merged);
      document.getElementById("statRejected").textContent = String(totals.rejected);
      document.getElementById("heroOpenPrs").textContent = String(totals.pending + totals.evaluated);
      document.getElementById("heroMergedPrs").textContent = String(totals.merged);
      if (!items || items.length === 0) {
        root.innerHTML = "<div class=\\"muted\\">No pull requests found for this repository.</div>";
        return;
      }
      root.innerHTML = items.map(function(item) {
        return "<div class=\\"pr-item\\">" +
          "<div class=\\"pr-head\\"><strong>#" + item.contribution_id + " " + (item.title || "Contribution") + "</strong>" + renderBadge(item.status) + "</div>" +
          "<div class=\\"muted\\">" + (item.summary || "No summary") + "</div>" +
          "<div class=\\"muted\\">branch: <strong>" + item.branch_name + "</strong> · zone: " + item.contribution_zone + " · by " + item.submitter_id + "</div>" +
          "<div class=\\"muted\\">eval: " + (item.evaluation_gate_passed === null || item.evaluation_gate_passed === undefined ? "n/a" : item.evaluation_gate_passed) +
          " · score: " + (item.evaluation_score === null || item.evaluation_score === undefined ? "n/a" : item.evaluation_score) + "</div>" +
          "<div class=\\"row\\" style=\\"margin-top:8px;\\">" +
            "<button onclick=\\"selectContribution(" + item.contribution_id + ")\\">Select</button>" +
            "<button onclick=\\"quickEvaluate(" + item.contribution_id + ")\\">Run checks</button>" +
          "</div>" +
        "</div>";
      }).join("");
    }

    function updateReleaseList(items) {
      document.getElementById("releaseList").textContent = JSON.stringify(items || [], null, 2);
      const latest = (items && items.length > 0 && items[0].version) ? items[0].version : "-";
      document.getElementById("heroLatestRelease").textContent = latest;
    }

    async function api(method, path, body) {
      const opts = { method: method, headers: authHeaders() };
      if (body !== undefined) { opts.body = JSON.stringify(body); }
      const response = await fetch(path, opts);
      const text = await response.text();
      let data = text;
      try { data = JSON.parse(text); } catch (error) {}
      if (!response.ok) { throw { status: response.status, data: data }; }
      return data;
    }

    async function loadWorkspace() {
      updateRepoHeader();
      try {
        const project = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()));
        const statusQuery = state.statusFilter ? ("?status=" + encodeURIComponent(state.statusFilter)) : "";
        const contributions = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions" + statusQuery);
        const releases = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/releases");
        renderPullRequests(contributions.items || []);
        updateReleaseList(releases.items || []);
        setResult("Repository loaded", { project: project, contributions: contributions, releases: releases }, true);
      } catch (error) {
        setResult("Error loading repository", error, false);
      }
    }

    async function refreshPullRequests() {
      try {
        const statusQuery = state.statusFilter ? ("?status=" + encodeURIComponent(state.statusFilter)) : "";
        const contributions = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions" + statusQuery);
        renderPullRequests(contributions.items || []);
        setResult("Pull requests refreshed", contributions, true);
      } catch (error) {
        setResult("Error refreshing pull requests", error, false);
      }
    }

    async function refreshReleases() {
      try {
        const channel = value("releaseChannel");
        const releases = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/releases?channel=" + encodeURIComponent(channel));
        updateReleaseList(releases.items || []);
        setResult("Releases refreshed", releases, true);
      } catch (error) {
        setResult("Error refreshing releases", error, false);
      }
    }

    function selectContribution(id) {
      document.getElementById("contribId").value = String(id);
      state.lastContributionId = id;
      logEvent("Contribution selected", { contribution_id: id }, true);
    }

    async function quickEvaluate(id) {
      selectContribution(id);
      await runChecks();
    }

    async function initializeRepo() {
      try {
        const payload = {
          namespace: ns(),
          project_id: pid(),
          display_name: value("displayName"),
          description: value("description"),
          contribution_zones: value("zones").split(",").map(function(v) { return v.trim(); }).filter(Boolean),
          merge_policy: jsonValue("mergePolicy", {}),
        };
        const created = await api("POST", "/projects", payload);
        setResult("Repository initialized", created, true);
        await loadWorkspace();
      } catch (error) {
        setResult("Error initializing repository", error, false);
      }
    }

    async function createBranch() {
      try {
        const branch = await api(
          "POST",
          "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/branches",
          { branch_name: value("branchName"), base_ref: value("baseRef") },
        );
        setResult("Branch created", branch, true);
      } catch (error) {
        setResult("Error creating branch", error, false);
      }
    }

    async function addMaintainer() {
      try {
        const resp = await api(
          "POST",
          "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/maintainers",
          { principal_id: value("maintainerId") },
        );
        setResult("Maintainer updated", resp, true);
      } catch (error) {
        setResult("Error adding maintainer", error, false);
      }
    }

    async function openPullRequest() {
      try {
        const contribution = await api(
          "POST",
          "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions",
          {
            branch_name: value("contribBranch"),
            title: value("contribTitle"),
            summary: value("contribSummary"),
            contribution_zone: value("contribZone"),
            contribution_manifest: jsonValue("contribManifest", {}),
            metrics: jsonValue("contribMetrics", {}),
            regressions: jsonValue("contribRegressions", {}),
          },
        );
        state.lastContributionId = contribution.contribution_id;
        document.getElementById("contribId").value = String(contribution.contribution_id);
        setResult("Pull request opened", contribution, true);
        await refreshPullRequests();
      } catch (error) {
        setResult("Error opening pull request", error, false);
      }
    }

    async function runChecks() {
      const contributionId = value("contribId") || (state.lastContributionId ? String(state.lastContributionId) : "");
      if (!contributionId) {
        setResult("Missing contribution id", { detail: "Select or submit a contribution first." }, false);
        return;
      }
      try {
        const evaluation = await api(
          "POST",
          "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions/" + encodeURIComponent(contributionId) + "/evaluate",
        );
        setResult("Checks completed", evaluation, true);
        await refreshPullRequests();
      } catch (error) {
        setResult("Error running checks", error, false);
      }
    }

    async function mergePullRequest() {
      const contributionId = value("contribId") || (state.lastContributionId ? String(state.lastContributionId) : "");
      if (!contributionId) {
        setResult("Missing contribution id", { detail: "Select or submit a contribution first." }, false);
        return;
      }
      try {
        const decision = await api(
          "POST",
          "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions/" + encodeURIComponent(contributionId) + "/review",
          {
            decision: value("decision"),
            decision_notes: value("decisionNotes"),
            release_version: value("releaseVersion"),
            release_channel: value("releaseChannel"),
          },
        );
        setResult("Pull request decision applied", decision, true);
        await refreshPullRequests();
        await refreshReleases();
      } catch (error) {
        setResult("Error applying pull request decision", error, false);
      }
    }

    document.getElementById("listProjects").onclick = async function() {
      try {
        const repos = await api("GET", "/projects");
        setResult("Repositories", repos, true);
      } catch (error) {
        setResult("Error listing repositories", error, false);
      }
    };
    document.getElementById("loadWorkspace").onclick = loadWorkspace;
    document.getElementById("reloadWorkspace").onclick = loadWorkspace;
    document.getElementById("createProject").onclick = initializeRepo;
    document.getElementById("createBranch").onclick = createBranch;
    document.getElementById("addMaintainer").onclick = addMaintainer;
    document.getElementById("submitContribution").onclick = openPullRequest;
    document.getElementById("evaluateContribution").onclick = runChecks;
    document.getElementById("reviewContribution").onclick = mergePullRequest;
    document.getElementById("refreshPrs").onclick = refreshPullRequests;
    document.getElementById("listReleases").onclick = refreshReleases;
    document.getElementById("filterRejected").onclick = function() { state.statusFilter = "rejected"; refreshPullRequests(); };
    document.getElementById("clearFilter").onclick = function() { state.statusFilter = null; refreshPullRequests(); };

    const originalRefreshPullRequests = refreshPullRequests;
    refreshPullRequests = async function() {
      document.getElementById("statusFilterLabel").textContent = "Filter: " + (state.statusFilter || "all pull requests");
      await originalRefreshPullRequests();
    };

    const originalLoadWorkspace = loadWorkspace;
    loadWorkspace = async function() {
      document.getElementById("statusFilterLabel").textContent = "Filter: " + (state.statusFilter || "all pull requests");
      await originalLoadWorkspace();
    };

    updateRepoHeader();
    renderFlowGuide();
  </script>
</body>
</html>
"""
