"""Lightweight browser UI for AgentForge project workflows."""

from __future__ import annotations


def render_forge_ui() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AgentForge Interface</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 0; background: #0e1116; color: #e6edf3; }
    header { padding: 16px 20px; border-bottom: 1px solid #30363d; background: #161b22; }
    h1 { margin: 0 0 8px 0; font-size: 24px; }
    .subtitle { margin: 0; color: #9da7b3; }
    main { display: grid; gap: 14px; padding: 14px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
    section { border: 1px solid #30363d; border-radius: 8px; padding: 12px; background: #161b22; }
    h2 { margin: 0 0 10px 0; font-size: 16px; }
    label { display: block; font-size: 12px; color: #9da7b3; margin: 8px 0 4px; }
    input, textarea, select, button { width: 100%; box-sizing: border-box; border-radius: 6px; border: 1px solid #30363d; background: #0d1117; color: #e6edf3; padding: 8px; }
    button { cursor: pointer; background: #1f6feb; border: none; font-weight: 600; margin-top: 8px; }
    button.secondary { background: #2f3742; }
    pre { margin: 0; white-space: pre-wrap; max-height: 380px; overflow: auto; }
    pre.compact { max-height: 180px; font-size: 12px; margin-top: 8px; }
    .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    #toast {
      position: fixed;
      top: 10px;
      right: 10px;
      width: 340px;
      max-height: 200px;
      overflow: auto;
      z-index: 9999;
      border: 1px solid #2ea043;
      border-radius: 8px;
      padding: 8px;
      background: #0d1f16;
      color: #b7f7c6;
      font-size: 12px;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <div id="toast">Last result: Ready.</div>
  <header>
    <h1>AgentForge</h1>
    <p class="subtitle">GitHub + App Store workflow for living agent projects: core branch, contribution packages, eval gates, and release channels.</p>
  </header>
  <main>
    <section>
      <h2>Auth + Project Explorer</h2>
      <label>Bearer token (from /auth/token/issue)</label>
      <input id="token" placeholder="Paste bearer token" />
      <label>Project search query</label>
      <input id="projectQuery" placeholder="research-agent" />
      <button id="listProjects">List Agent Projects</button>
      <button id="loadProject" class="secondary">Load Workspace Project</button>
    </section>

    <section>
      <h2>Agent Repository (Core)</h2>
      <div class="two-col">
        <div>
          <label>Namespace</label>
          <input id="namespace" value="dev-a" />
        </div>
        <div>
          <label>Project ID</label>
          <input id="projectId" value="research-agent" />
        </div>
      </div>
      <label>Display name</label>
      <input id="displayName" value="Research Agent" />
      <label>Description</label>
      <textarea id="description">Depth-first managed agent project.</textarea>
      <label>Contribution zones (csv)</label>
      <input id="zones" value="prompts,tool_adapters,workflow_steps,domain_packs,safety_constraints" />
      <label>Merge policy JSON</label>
      <textarea id="mergePolicy">{"min_improvements":1,"allowed_latency_regression_pct":5.0,"allowed_cost_regression_pct":5.0,"must_pass_safety":true,"must_pass_regression_tests":true}</textarea>
      <button id="createProject">Create Project</button>
      <label>Add maintainer principal_id</label>
      <input id="maintainerId" placeholder="contrib-2" />
      <button id="addMaintainer" class="secondary">Add Maintainer</button>
    </section>

    <section>
      <h2>Branch Workshop</h2>
      <label>Branch name</label>
      <input id="branchName" value="improved-citation-module" />
      <label>Base ref</label>
      <input id="baseRef" value="main" />
      <button id="createBranch">Create Branch</button>
    </section>

    <section>
      <h2>Contribution Package</h2>
      <label>Contribution title</label>
      <input id="contribTitle" value="Improve citation quality" />
      <label>Summary</label>
      <textarea id="contribSummary">Adds citation normalization and confidence thresholding.</textarea>
      <label>Contribution zone</label>
      <select id="contribZone">
        <option>workflow_steps</option>
        <option>tool_adapters</option>
        <option>prompts</option>
        <option>domain_packs</option>
        <option>safety_constraints</option>
      </select>
      <label>Manifest JSON</label>
      <textarea id="contribManifest">{"what_changed":["citation normalization"],"why_it_matters":"Higher citation precision."}</textarea>
      <label>Metrics JSON</label>
      <textarea id="contribMetrics">{"improvements":{"accuracy":0.06,"reliability":0.03},"safety_passed":true,"regression_tests_passed":true,"evaluation_score":90.5}</textarea>
      <label>Regressions JSON</label>
      <textarea id="contribRegressions">{"latency_regression_pct":1.2,"cost_regression_pct":0.7}</textarea>
      <button id="submitContribution">Submit Contribution</button>
      <button id="listContributions" class="secondary">List Contributions</button>
    </section>

    <section>
      <h2>Eval Gate + Maintainer Merge</h2>
      <label>Contribution ID</label>
      <input id="contribId" placeholder="1" />
      <button id="evaluateContribution">Run Automated Evaluation</button>
      <label>Decision</label>
      <select id="decision">
        <option value="merge">merge</option>
        <option value="reject">reject</option>
      </select>
      <label>Decision notes</label>
      <textarea id="decisionNotes">Improves quality without unacceptable regressions.</textarea>
      <div class="two-col">
        <div>
          <label>Release version</label>
          <input id="releaseVersion" value="1.1.0" />
        </div>
        <div>
          <label>Release channel</label>
          <select id="releaseChannel">
            <option>stable</option>
            <option>beta</option>
            <option>nightly</option>
            <option>enterprise-certified</option>
          </select>
        </div>
      </div>
      <button id="reviewContribution">Review + Apply Decision</button>
      <button id="listReleases" class="secondary">List Releases</button>
      <pre id="resultMirror" class="compact">Mirror: Ready.</pre>
    </section>

    <section>
      <h2>Output</h2>
      <pre id="result">Ready.</pre>
    </section>
  </main>

  <script>
    function value(id) { return document.getElementById(id).value.trim(); }
    function jsonValue(id, fallback) {
      const raw = value(id);
      if (!raw) { return fallback; }
      return JSON.parse(raw);
    }
    function setResult(label, data) {
      const rendered = label + "\\n\\n" + JSON.stringify(data, null, 2);
      document.getElementById("result").textContent = rendered;
      document.getElementById("resultMirror").textContent = rendered;
      document.getElementById("toast").textContent = "Last result\\n\\n" + rendered;
    }
    function authHeaders() {
      const headers = {"Content-Type": "application/json"};
      const token = value("token");
      if (token) {
        headers["Authorization"] = "Bearer " + token;
      }
      return headers;
    }
    async function api(method, path, body) {
      const opts = { method, headers: authHeaders() };
      if (body !== undefined) {
        opts.body = JSON.stringify(body);
      }
      const response = await fetch(path, opts);
      const text = await response.text();
      let data = text;
      try { data = JSON.parse(text); } catch (error) {}
      if (!response.ok) {
        throw { status: response.status, data };
      }
      return data;
    }
    function ns() { return value("namespace"); }
    function pid() { return value("projectId"); }

    document.getElementById("listProjects").onclick = async () => {
      try {
        const query = value("projectQuery");
        const suffix = query ? ("?query=" + encodeURIComponent(query)) : "";
        const data = await api("GET", "/projects" + suffix);
        setResult("Projects", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("createProject").onclick = async () => {
      try {
        const data = await api("POST", "/projects", {
          namespace: ns(),
          project_id: pid(),
          display_name: value("displayName"),
          description: value("description"),
          contribution_zones: value("zones").split(",").map(v => v.trim()).filter(Boolean),
          merge_policy: jsonValue("mergePolicy", {})
        });
        setResult("Project created", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("loadProject").onclick = async () => {
      try {
        const project = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()));
        const contributions = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions");
        const releases = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/releases");
        setResult("Project workspace", { project, contributions, releases });
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("addMaintainer").onclick = async () => {
      try {
        const data = await api("POST", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/maintainers", {
          principal_id: value("maintainerId")
        });
        setResult("Maintainer updated", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("createBranch").onclick = async () => {
      try {
        const data = await api("POST", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/branches", {
          branch_name: value("branchName"),
          base_ref: value("baseRef")
        });
        setResult("Branch created", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("submitContribution").onclick = async () => {
      try {
        const data = await api("POST", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions", {
          branch_name: value("branchName"),
          title: value("contribTitle"),
          summary: value("contribSummary"),
          contribution_zone: value("contribZone"),
          contribution_manifest: jsonValue("contribManifest", {}),
          metrics: jsonValue("contribMetrics", {}),
          regressions: jsonValue("contribRegressions", {})
        });
        setResult("Contribution submitted", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("listContributions").onclick = async () => {
      try {
        const data = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions");
        setResult("Contributions", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("evaluateContribution").onclick = async () => {
      try {
        const id = value("contribId");
        const data = await api("POST", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions/" + encodeURIComponent(id) + "/evaluate");
        setResult("Evaluation", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("reviewContribution").onclick = async () => {
      try {
        const id = value("contribId");
        const payload = {
          decision: value("decision"),
          decision_notes: value("decisionNotes"),
          release_version: value("releaseVersion"),
          release_channel: value("releaseChannel")
        };
        const data = await api("POST", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/contributions/" + encodeURIComponent(id) + "/review", payload);
        setResult("Review outcome", data);
      } catch (error) { setResult("Error", error); }
    };

    document.getElementById("listReleases").onclick = async () => {
      try {
        const channel = value("releaseChannel");
        const data = await api("GET", "/projects/" + encodeURIComponent(ns()) + "/" + encodeURIComponent(pid()) + "/releases?channel=" + encodeURIComponent(channel));
        setResult("Releases", data);
      } catch (error) { setResult("Error", error); }
    };
  </script>
</body>
</html>
"""
