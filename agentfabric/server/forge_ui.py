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
      --bg: #0d1117;
      --panel: #161b22;
      --muted: #8b949e;
      --border: #30363d;
      --text: #e6edf3;
      --accent: #1f6feb;
      --green: #238636;
      --purple: #8957e5;
      --red: #da3633;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--bg); color: var(--text); font-family: Arial, sans-serif; }
    input, textarea, select {
      width: 100%; padding: 8px; border: 1px solid var(--border); border-radius: 6px;
      background: #0b0f14; color: var(--text);
    }
    button {
      border: 1px solid var(--border); border-radius: 6px; color: var(--text);
      background: #21262d; padding: 8px 10px; cursor: pointer; font-weight: 600;
    }
    button.primary { background: var(--green); border-color: #2ea043; }
    button.blue { background: var(--accent); border-color: #1f6feb; }
    button.ghost { background: transparent; }
    .topbar {
      border-bottom: 1px solid var(--border); background: #010409;
      padding: 10px 16px; display: flex; align-items: center; gap: 12px;
    }
    .logo {
      width: 28px; height: 28px; border-radius: 50%; display: inline-flex;
      align-items: center; justify-content: center; background: var(--purple); font-weight: 700;
    }
    .repo-path { font-size: 15px; font-weight: 700; }
    .topbar .split { flex: 1; }
    .toolbar {
      border-bottom: 1px solid var(--border); background: var(--panel);
      padding: 10px 16px; display: grid; gap: 10px; grid-template-columns: 1.6fr 1fr 1fr auto auto;
    }
    .tabs {
      border-bottom: 1px solid var(--border); display: flex; gap: 12px;
      padding: 0 16px; background: var(--panel);
    }
    .tab {
      padding: 10px 6px; color: var(--muted); border-bottom: 2px solid transparent;
      font-size: 14px; text-decoration: none;
    }
    .tab.active { color: var(--text); border-bottom-color: #f78166; }
    .layout {
      display: grid; gap: 12px; padding: 12px 16px;
      grid-template-columns: 260px minmax(580px, 1fr) 320px;
    }
    .card {
      background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 12px;
    }
    .card h3 { margin: 0 0 10px 0; font-size: 15px; }
    .label { color: var(--muted); font-size: 12px; margin: 8px 0 4px 0; }
    .muted { color: var(--muted); font-size: 12px; }
    .row { display: flex; gap: 8px; }
    .row > * { flex: 1; }
    .pr-item {
      border: 1px solid var(--border); border-radius: 8px; padding: 10px; margin-bottom: 8px; background: #0d1117;
    }
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
      position: fixed; top: 10px; right: 10px; width: 360px; max-height: 220px; overflow: auto;
      z-index: 9999; border: 1px solid #2ea043; border-radius: 8px; padding: 8px; background: #0d1f16; color: #b7f7c6;
      font-size: 12px; white-space: pre-wrap;
    }
    pre { margin: 0; white-space: pre-wrap; max-height: 260px; overflow: auto; background: #0d1117; border: 1px solid var(--border); border-radius: 8px; padding: 8px; }
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
    <input id="token" placeholder="Bearer token (POST /auth/token/issue)" />
    <input id="namespace" value="dev-a" placeholder="namespace" />
    <input id="projectId" value="research-agent" placeholder="project id" />
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

    updateRepoHeader();
  </script>
</body>
</html>
"""
