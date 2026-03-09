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
      --bg: #f3f5f8;
      --bg-grad-1: rgba(62, 99, 221, 0.18);
      --bg-grad-2: rgba(139, 92, 246, 0.16);
      --surface: rgba(255, 255, 255, 0.72);
      --surface-strong: rgba(255, 255, 255, 0.9);
      --surface-dark: #0f1729;
      --muted: #667085;
      --border: rgba(15, 23, 42, 0.14);
      --text: #0f172a;
      --text-on-dark: #e5e7eb;
      --accent: #2563eb;
      --green: #17a34a;
      --purple: #7c3aed;
      --red: #dc2626;
      --ring: rgba(37, 99, 235, 0.24);
      --shadow-soft: 0 10px 30px rgba(15, 23, 42, 0.08);
      --shadow-strong: 0 18px 48px rgba(15, 23, 42, 0.16);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background:
        radial-gradient(circle at 20% -10%, var(--bg-grad-1), transparent 30%),
        radial-gradient(circle at 80% -20%, var(--bg-grad-2), transparent 33%),
        var(--bg);
      color: var(--text-on-dark);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", Helvetica, Arial, sans-serif;
      min-height: 100vh;
    }
    input, textarea, select {
      width: 100%;
      padding: 8px 10px;
      border: 1px solid var(--border);
      border-radius: 10px;
      background: rgba(255, 255, 255, 0.9);
      color: #111827;
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
      border-radius: 10px;
      color: #111827;
      background: rgba(255, 255, 255, 0.9);
      padding: 9px 12px;
      cursor: pointer;
      font-weight: 600;
      transition: transform .05s ease, background .15s ease, border-color .15s ease, box-shadow .15s ease;
      box-shadow: 0 1px 0 rgba(15, 23, 42, 0.04);
    }
    button:hover { background: #fff; border-color: rgba(15, 23, 42, 0.24); }
    button:active { transform: translateY(1px); }
    button.primary { background: linear-gradient(160deg, #23be5c, #149647); border-color: #149647; color: #f8fffb; box-shadow: 0 8px 18px rgba(23, 163, 74, 0.26); }
    button.primary:hover { background: linear-gradient(160deg, #2bca67, #129245); }
    button.blue { background: linear-gradient(160deg, #3b82f6, #2563eb); border-color: #1e40af; color: #eef6ff; box-shadow: 0 8px 18px rgba(37, 99, 235, 0.26); }
    button.blue:hover { background: linear-gradient(160deg, #4a8ff7, #285ee2); }
    button.ghost { background: transparent; border-color: transparent; color: #cbd5e1; }
    .topbar {
      border-bottom: 1px solid rgba(255, 255, 255, 0.12);
      background: linear-gradient(120deg, #0f172a, #111f39);
      backdrop-filter: blur(14px);
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
      border-radius: 10px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: #f8fafc;
      background: linear-gradient(140deg, #a855f7, #3b82f6);
      font-weight: 700;
      box-shadow: 0 10px 24px rgba(91, 77, 255, 0.28);
    }
    .repo-path { font-size: 15px; font-weight: 700; letter-spacing: .1px; color: #f8fafc; }
    .topbar .split { flex: 1; }
    .toolbar {
      border-bottom: 1px solid rgba(15, 23, 42, 0.06);
      background: var(--surface);
      backdrop-filter: blur(10px);
      padding: 14px 20px;
      display: grid;
      gap: 10px;
      grid-template-columns: 1.9fr 1fr 1fr auto auto;
      align-items: end;
    }
    .field > span {
      display: block;
      font-size: 11px;
      color: #6b7280;
      margin: 0 0 4px;
      font-weight: 600;
      letter-spacing: .3px;
      text-transform: uppercase;
    }
    .tabs {
      border-bottom: 1px solid rgba(15, 23, 42, 0.08);
      display: flex;
      gap: 12px;
      padding: 0 20px;
      background: var(--surface);
      backdrop-filter: blur(10px);
    }
    .tab {
      padding: 11px 8px;
      color: var(--muted);
      border-bottom: 2px solid transparent;
      font-size: 14px;
      text-decoration: none;
      font-weight: 600;
    }
    .tab.active { color: #111827; border-bottom-color: #2563eb; }
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
      background: rgba(255, 255, 255, 0.84);
      border-radius: 999px;
      padding: 3px 9px;
    }
    .hero {
      margin: 10px 20px 0;
      border: 1px solid rgba(255, 255, 255, 0.52);
      border-radius: 18px;
      background:
        linear-gradient(120deg, rgba(255, 255, 255, 0.72), rgba(255, 255, 255, 0.48)),
        radial-gradient(circle at 12% 10%, rgba(37, 99, 235, 0.22), transparent 32%);
      backdrop-filter: blur(10px);
      box-shadow: var(--shadow-strong);
      padding: 16px;
      display: grid;
      grid-template-columns: 1.45fr 1fr;
      gap: 12px;
    }
    .hero h1 {
      margin: 6px 0 8px;
      font-size: 24px;
      color: #0f172a;
      line-height: 1.15;
      letter-spacing: -0.4px;
    }
    .hero p {
      margin: 0;
      color: #475467;
      line-height: 1.5;
      font-size: 13px;
    }
    .hero-eyebrow {
      font-size: 11px;
      letter-spacing: .5px;
      text-transform: uppercase;
      color: #475467;
      font-weight: 700;
    }
    .hero-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .hero-kpi {
      border: 1px solid rgba(15, 23, 42, 0.1);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.88);
      padding: 10px;
    }
    .hero-kpi .num { font-size: 20px; font-weight: 800; color: #0f172a; line-height: 1.1; }
    .hero-kpi .txt { font-size: 11px; color: #667085; text-transform: uppercase; }
    .layout {
      display: grid;
      gap: 12px;
      padding: 12px 20px 18px;
      grid-template-columns: 260px minmax(580px, 1fr) 320px;
    }
    .card {
      background: var(--surface);
      border: 1px solid rgba(255, 255, 255, 0.64);
      border-radius: 14px;
      padding: 12px;
      box-shadow: var(--shadow-soft);
      backdrop-filter: blur(8px);
    }
    .card h3 { margin: 0 0 10px 0; font-size: 15px; letter-spacing: .2px; color: #0f172a; }
    .label { color: #667085; font-size: 12px; margin: 8px 0 4px 0; }
    .muted { color: #64748b; font-size: 12px; line-height: 1.45; }
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
      background: rgba(255, 255, 255, 0.88);
      padding: 8px;
      text-align: center;
    }
    .stat .num { font-size: 18px; font-weight: 700; line-height: 1.1; color: #0f172a; }
    .stat .txt { font-size: 11px; color: #64748b; text-transform: uppercase; letter-spacing: .4px; }
    .pr-item {
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 10px;
      margin-bottom: 8px;
      background: rgba(255, 255, 255, 0.9);
      transition: border-color .15s ease, transform .05s ease;
    }
    .pr-item:hover { border-color: #4b5561; transform: translateY(-1px); }
    .pr-head { display: flex; justify-content: space-between; align-items: center; gap: 10px; }
    .badge {
      padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; text-transform: uppercase;
    }
    .badge.pending { background: #9e6a0333; color: #f2cc60; }
    .badge.evaluated { background: #1f6feb33; color: #79c0ff; }
    .badge.merged { background: #23863633; color: #3fb950; }
    .badge.rejected { background: #da363333; color: #ff7b72; }
    .activity {
      max-height: 420px; overflow: auto; background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 8px;
    }
    .event {
      border-left: 2px solid var(--border); padding: 8px 8px 8px 10px; margin: 6px 0; font-size: 12px;
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
      border: 1px solid rgba(16, 185, 129, 0.7);
      border-radius: 10px;
      padding: 8px;
      background: rgba(6, 28, 23, 0.9);
      color: #b7f7c6;
      font-size: 12px;
      white-space: pre-wrap;
      box-shadow: var(--shadow-strong);
    }
    pre {
      margin: 0;
      white-space: pre-wrap;
      max-height: 260px;
      overflow: auto;
      background: rgba(255, 255, 255, 0.84);
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
      <div class="hero-eyebrow">AgentForge Marketplace Experience</div>
      <h1>Modern GitHub workflows with premium product polish.</h1>
      <p>Manage living agent repositories with pull-request rigor, automated checks, maintainers, and release channels in a clean Apple-style control surface.</p>
    </div>
    <div class="hero-grid">
      <div class="hero-kpi"><div class="num" id="heroTotalRepos">1</div><div class="txt">Active repository</div></div>
      <div class="hero-kpi"><div class="num" id="heroOpenPrs">0</div><div class="txt">Open pull requests</div></div>
      <div class="hero-kpi"><div class="num" id="heroMergedPrs">0</div><div class="txt">Merged pull requests</div></div>
      <div class="hero-kpi"><div class="num" id="heroLatestRelease">-</div><div class="txt">Latest stable release</div></div>
    </div>
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
    const state = { lastContributionId: null, statusFilter: null };

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
  </script>
</body>
</html>
"""
