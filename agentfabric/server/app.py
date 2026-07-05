"""FastAPI application with auth middleware and OpenAPI docs."""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import shutil
import time
from collections import defaultdict
from uuid import uuid4

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, Response as FastAPIResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from agent_connectors import (
    ConnectorExecutionPolicy as EnterpriseConnectorPolicy,
    ConnectorManifest as EnterpriseConnectorManifest,
    EnterpriseConnectorService,
)
from agent_observability import AgentMetric, OperationalIntelligenceService
from agentfabric.audit_bundle import AuditBundleExporter
from agentfabric.build_workers import BuildWorkerService
from agentfabric.cloud import CloudRuntime, RuntimeConfig, RuntimeJob, Worker
from agentfabric.cloud.queue_backends import MemoryJobQueue, RedisJobQueue, SQLiteJobQueue
from agentfabric.cloud.scheduler import ScheduledJob, SchedulerService
from agentfabric.config import validate_production_safety
from agentfabric.collaboration import CollaborationCoordinator, ContextStore, MeshWorkflowEngine, TaskNode
from agentfabric.connectors import ConnectorCredentials, ConnectorManifest, ConnectorPolicy, ConnectorRegistry
from agentfabric.economics import CostTracker, MarginAnalyzer, PackageRevenue, PricingPolicy, RevenueTracker, TenantProfitability
from agentfabric.enterprise import Membership, MembershipService, Team, TenantContext, TenantIsolation, TenantService
from agentfabric.errors import AgentFabricError, AuthorizationError, ConflictError, NotFoundError, ValidationError
from agentfabric.evaluation import EvaluationCase, EvaluationDataset, EvaluationRunner, QualityGateService
from agentfabric.feedback import FeedbackService
from agentfabric.events import EventStore, EventType
from agentfabric.federation import (
    FederatedOrg,
    FederationService,
    RemoteAgent,
    RemoteCapability,
    RemoteDelegation,
    TrustAgreement,
)
from agentfabric.federation.messaging import FederatedMessage
from agentfabric.governance import (
    AgentOrganization,
    AgentTeam,
    Charter,
    ConsensusPolicy,
    GovernancePolicy,
    GovernanceService,
    HumanApprovalQueue,
    Proposal,
    ProposalStatus,
    Vote,
)
from agentfabric.identity import AgentCertificate, AgentIdentity, AgentPassport
from agentfabric.marketplace import (
    InstallService,
    MarketplaceRegistryService,
    PackageDependency,
    PackageManifest,
    PackageMetadata,
    PackageSignature,
    PublishService,
    SignatureVerifier,
    SigningKey,
    TrustedPublisherRegistry,
)
from agentfabric.marketplace.reviews import PackageReview, PublisherReputationService, RatingService
from agentfabric.marketplace.scanning import MarketplaceScanner
from agentfabric.memory import DurableMemoryStore
from agentfabric.metering import MeteringService
from agentfabric.mesh import AgentDirectory, AgentDiscovery, MeshMessage, MessageBus, MessageType
from agentfabric.migrations import MigrationRunner
from agentfabric.observability import DeploymentHealth, MetricsRegistry, TenantUsageMetrics
from agentfabric.phase2.models import Rating
from agentfabric.persistence import MemoryPersistenceStore, SQLitePersistenceStore
from agentfabric.production.control_plane import ProductionControlPlane
from agentfabric.quotas import LimitEnforcer, QuotaPolicy, QuotaTracker
from agentfabric.reputation import ReputationService
from agentfabric.recovery import ReplayRecoveryEngine
from agentfabric.repository_execution import RepositoryExecutionEngine
from agentfabric.domain_platforms import DomainPlatformDefinition
from agentfabric.software_factory import SoftwareFoundryService
from agentfabric.server.auth import AuthService, require_scopes
from agentfabric.server.config import Settings, get_settings
from agentfabric.server.database import build_session_factory, run_migrations
from agentfabric.server.errors import domain_exception_response, http_exception_response
from agentfabric.server.models import Principal
from agentfabric.server.payments import MockPaymentProcessor, StripePaymentProcessor, get_billing_plan, parse_stripe_webhook_event
from agentfabric.server.queue import InMemoryQueueBackend, RedisQueueBackend
from agentfabric.server.schemas import (
    BillingEventRequest,
    HealthResponse,
    InstallPackageRequest,
    InvoiceResponse,
    IssueTokenRequest,
    ListPackagesResponse,
    PackageResponse,
    PublishPackageRequest,
    QueueEnqueueRequest,
    QueueMessageResponse,
    RegisterPrincipalRequest,
    RotateTokenRequest,
    TokenResponse,
)
from agentfabric.server.services import AuditService, BillingService, PackageService, QueueService
from agentfabric.server.signing import CosignVerifier, DigestFallbackVerifier
from agentfabric.tools import ToolManifest, ToolPermission, ToolRegistry, ToolRouter
from agentfabric.verticals.renovation import RenovationFoundationService
from agentfabric.verticals.renovation.mvp import RenovationMvpWorkflow
from agentfabric.verticals.renovation.operator import RenovationOperatorCockpit
from agentfabric.verticals.renovation.saas import LocalAttachmentStore
from veil_client import MockVeilClient

HTTP_REQUEST_COUNT = Counter(
    "agentfabric_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)
HTTP_REQUEST_LATENCY = Histogram(
    "agentfabric_http_request_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)


def choose_queue_backend(settings: Settings):
    if settings.redis_url.startswith("redis://"):
        try:
            return RedisQueueBackend(settings.redis_url)
        except Exception:
            return InMemoryQueueBackend()
    return InMemoryQueueBackend()


def choose_signing_verifier(settings: Settings):
    if shutil.which("cosign") is not None:
        return CosignVerifier()
    if settings.strict_signing:
        raise RuntimeError("strict signing is enabled but cosign is not available")
    return DigestFallbackVerifier()


def choose_cloud_queue(settings: Settings):
    if settings.cloud_queue_backend == "sqlite":
        return SQLiteJobQueue(settings.cloud_queue_sqlite_path)
    if settings.cloud_queue_backend == "redis":
        return RedisJobQueue(settings.redis_url, fallback=settings.environment != "production")
    return MemoryJobQueue()


def _sqlite_path_from_url(database_url: str) -> Path | None:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        return None
    raw_path = database_url[len(prefix) :]
    if raw_path == ":memory:":
        return None
    return Path(raw_path)


def _is_sqlite_memory_url(database_url: str) -> bool:
    return database_url == "sqlite:///:memory:"


def choose_state_store(settings: Settings):
    backend = settings.state_store_backend.lower()
    if backend == "memory":
        return MemoryPersistenceStore()
    if backend != "sqlite":
        raise RuntimeError("AGENTFABRIC_STATE_STORE_BACKEND must be memory or sqlite")
    if settings.state_store_path:
        path = Path(settings.state_store_path)
    else:
        database_path = _sqlite_path_from_url(settings.database_url)
        if database_path is None and _is_sqlite_memory_url(settings.database_url):
            return MemoryPersistenceStore()
        path = (
            database_path.with_name(f"{database_path.stem}.state.db")
            if database_path is not None
            else Path("agentfabric_state.db")
        )
    store = SQLitePersistenceStore(path)
    store.initialize()
    return store


def _renovation_app_html_legacy() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RenovationOS Cockpit</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #1d2630;
      --muted: #657180;
      --line: #d8dee6;
      --panel: #ffffff;
      --page: #f4f6f8;
      --accent: #176b5c;
      --accent-strong: #0f4d42;
      --soft: #e8f3f0;
      --warn: #a35412;
      --bad: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--page);
      color: var(--ink);
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 16px 24px;
      border-bottom: 1px solid var(--line);
      background: var(--panel);
    }
    h1 { margin: 0; font-size: 20px; font-weight: 650; letter-spacing: 0; }
    main { display: grid; grid-template-columns: 360px 1fr; min-height: calc(100vh - 65px); }
    aside {
      padding: 20px;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }
    section { padding: 20px; }
    label { display: block; margin: 14px 0 6px; color: var(--muted); font-size: 13px; }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      background: white;
      color: var(--ink);
    }
    textarea { min-height: 118px; resize: vertical; }
    button {
      margin-top: 16px;
      border: 0;
      border-radius: 6px;
      padding: 11px 14px;
      font: inherit;
      font-weight: 650;
      color: white;
      background: var(--accent);
      cursor: pointer;
    }
    button:hover { background: var(--accent-strong); }
    button:disabled { cursor: wait; opacity: .65; }
    .button-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .button-row button { width: 100%; }
    .secondary { background: #3f4f5f; }
    .secondary:hover { background: #2f3d4a; }
    .hint { color: var(--muted); font-size: 13px; line-height: 1.45; margin: 12px 0 0; }
    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 16px;
    }
    .metric, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
    }
    .metric span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .metric strong { font-size: 18px; overflow-wrap: anywhere; }
    .panel { margin-top: 12px; }
    .panel h2 { margin: 0 0 10px; font-size: 15px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { border-bottom: 1px solid var(--line); padding: 9px 7px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 650; }
    tr[data-run-id] { cursor: pointer; }
    tr[data-run-id]:hover { background: var(--soft); }
    .timeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
    .step { border: 1px solid var(--line); border-radius: 6px; padding: 9px; background: #fbfcfd; }
    .step strong { display: block; font-size: 12px; overflow-wrap: anywhere; }
    .step span { color: var(--muted); font-size: 12px; }
    .completed { border-color: #8abfaf; background: #eef8f4; }
    .failed { border-color: #e09a91; background: #fff1ef; }
    .running { border-color: #d8ad5b; background: #fff8e8; }
    pre {
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: #29333d;
      font-size: 12px;
      line-height: 1.45;
    }
    .empty { color: var(--muted); }
    .error { color: var(--bad); }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .timeline { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
  </style>
</head>
<body>
  <header>
    <h1>RenovationOS Operator Cockpit</h1>
  </header>
  <main>
    <aside>
      <label for="token">Bearer token</label>
      <input id="token" type="password" autocomplete="off" placeholder="Paste an AgentFabric token">
      <label for="idempotency">Idempotency key</label>
      <input id="idempotency" autocomplete="off" placeholder="demo-run-001">
      <label for="payload">Custom run JSON</label>
      <textarea id="payload" spellcheck="false">{
  "lead": {"name": "Morgan Homeowner"},
  "project": {"title": "Kitchen Remodel"}
}</textarea>
      <div class="button-row">
        <button id="run-demo">Run Demo</button>
        <button id="run-custom" class="secondary">Create Run</button>
      </div>
      <div class="button-row">
        <button id="replay" class="secondary">Replay</button>
        <button id="resume" class="secondary">Resume</button>
      </div>
      <button id="refresh" class="secondary">Refresh Cockpit</button>
      <p class="hint">Use the cockpit for live operating records, and the MVP panel for replayable end-to-end demos.</p>
      <p id="error" class="hint error"></p>
    </aside>
    <section>
      <div class="grid">
        <div class="metric"><span>Total leads</span><strong id="metric-leads">-</strong></div>
        <div class="metric"><span>Active jobs</span><strong id="metric-jobs">-</strong></div>
        <div class="metric"><span>Invoiced revenue</span><strong id="metric-invoiced">-</strong></div>
        <div class="metric"><span>Outstanding</span><strong id="metric-outstanding">-</strong></div>
      </div>
      <div class="panel">
        <h2>Dashboard Summary</h2>
        <pre id="metrics">Loading metrics...</pre>
      </div>
      <div class="grid">
        <div class="panel">
          <h2>Lead Intake</h2>
          <textarea id="lead-json" spellcheck="false">{
  "name": "Morgan Homeowner",
  "email": "morgan@example.com",
  "phone": "555-0140",
  "property_address": "200 Oak Street",
  "project_type": "kitchen_remodel",
  "description": "Replace cabinets, counters, and flooring.",
  "created_date": "2026-08-01",
  "source": {"source_type": "website", "source_name": "renovationos-contact-form"}
}</textarea>
          <button id="create-lead">Create Lead</button>
        </div>
        <div class="panel">
          <h2>Estimate Builder</h2>
          <textarea id="estimate-json" spellcheck="false">{
  "project_id": "project-kitchen-1",
  "scope_description": "Cabinet replacement\\nFlooring replacement",
  "rooms": [{"name": "Kitchen", "length_ft": 20, "width_ft": 15, "quantity": 1}],
  "quantities": {"cabinetry": 10, "flooring": 300},
  "labor_rate": 65,
  "contingency_percentage": 10,
  "tax_percentage": 6
}</textarea>
          <button id="create-estimate">Create Estimate</button>
        </div>
        <div class="panel">
          <h2>Job Action</h2>
          <label for="job-select">Selected job</label>
          <select id="job-select"></select>
          <label for="job-status">Status</label>
          <input id="job-status" value="in_progress">
          <button id="update-status">Update Status</button>
        </div>
        <div class="panel">
          <h2>Cost / Invoice</h2>
          <textarea id="finance-json" spellcheck="false">{"amount": 5000, "invoice_date": "2026-07-01", "due_date": "2026-07-15", "description": "Project deposit"}</textarea>
          <div class="button-row">
            <button id="create-cost" class="secondary">Cost</button>
            <button id="create-invoice">Invoice</button>
          </div>
        </div>
      </div>
      <div class="panel">
        <h2>Customer List</h2>
        <table><thead><tr><th>Customer</th><th>Email</th><th>Phone</th></tr></thead><tbody id="customers"><tr><td colspan="3" class="empty">Loading customers...</td></tr></tbody></table>
      </div>
      <div class="panel">
        <h2>Lead Pipeline</h2>
        <table><thead><tr><th>Lead</th><th>Status</th><th>Project</th><th>Customer</th></tr></thead><tbody id="leads"><tr><td colspan="4" class="empty">Loading leads...</td></tr></tbody></table>
      </div>
      <div class="panel">
        <h2>Proposal View</h2>
        <table><thead><tr><th>Proposal</th><th>Status</th><th>Customer</th><th>Total</th></tr></thead><tbody id="proposals"><tr><td colspan="4" class="empty">Loading proposals...</td></tr></tbody></table>
      </div>
      <div class="panel">
        <h2>Job Board</h2>
        <table><thead><tr><th>Job</th><th>Status</th><th>Project</th><th>Customer</th></tr></thead><tbody id="jobs"><tr><td colspan="4" class="empty">Loading jobs...</td></tr></tbody></table>
      </div>
      <div class="grid">
        <div class="panel">
          <h2>Schedule View</h2>
          <textarea id="schedule-json" spellcheck="false">{"start_date": "2026-07-06"}</textarea>
          <button id="create-schedule">Add Schedule</button>
          <pre id="schedule-view">No job selected.</pre>
        </div>
        <div class="panel">
          <h2>Cost / Profitability</h2>
          <pre id="profitability">No job selected.</pre>
        </div>
        <div class="panel">
          <h2>Invoice / Payment</h2>
          <label for="invoice-select">Invoice</label>
          <select id="invoice-select"></select>
          <textarea id="payment-json" spellcheck="false">{"payment_date": "2026-07-05", "amount": 1000, "method": "ach"}</textarea>
          <button id="record-payment">Record Payment</button>
        </div>
        <div class="panel">
          <h2>Customer Portal Preview</h2>
          <pre id="job-portal">No job selected.</pre>
        </div>
      </div>
      <div class="grid">
        <div class="metric"><span>MVP status</span><strong id="status">Idle</strong></div>
        <div class="metric"><span>MVP run</span><strong id="run-id">-</strong></div>
        <div class="metric"><span>Invoice balance</span><strong id="balance">-</strong></div>
        <div class="metric"><span>Margin</span><strong id="margin">-</strong></div>
      </div>
      <div class="panel">
        <h2>MVP Runs / Replay / Resume</h2>
        <table>
          <thead><tr><th>Run</th><th>Status</th><th>Job</th><th>Failed Step</th></tr></thead>
          <tbody id="runs"><tr><td colspan="4" class="empty">No runs loaded.</td></tr></tbody>
        </table>
      </div>
      <div class="panel">
        <h2>Workflow Timeline</h2>
        <div id="timeline" class="timeline"><div class="empty">Select or create a run.</div></div>
      </div>
      <div class="panel">
        <h2>Financial Summary</h2>
        <pre id="financial">No financial summary yet.</pre>
      </div>
      <div class="panel">
        <h2>Portal Preview</h2>
        <pre id="portal">No portal view yet.</pre>
      </div>
      <div class="panel">
        <h2>Run Detail</h2>
        <pre id="raw">{}</pre>
      </div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let selectedRunId = "";
    function headers() {
      const token = $("token").value.trim();
      return {"Content-Type": "application/json", ...(token ? {"Authorization": `Bearer ${token}`} : {})};
    }
    async function api(path, options = {}) {
      $("error").textContent = "";
      const response = await fetch(path, {...options, headers: {...headers(), ...(options.headers || {})}});
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || response.statusText);
      return data;
    }
    function customPayload() {
      const body = JSON.parse($("payload").value || "{}");
      const key = $("idempotency").value.trim();
      return key ? {...body, idempotency_key: key} : body;
    }
    function money(value) {
      return `$${Number(value || 0).toFixed(2)}`;
    }
    function artifact(record) {
      return record?.artifact || record || {};
    }
    function tableEmpty(id, cols, text) {
      $(id).innerHTML = `<tr><td colspan="${cols}" class="empty">${text}</td></tr>`;
    }
    function selectedJobId() {
      return $("job-select").value;
    }
    async function loadCockpit() {
      try {
        $("metrics").textContent = "Loading metrics...";
        const [metrics, customers, leads, proposals, jobs, account, accounts, files, notifications, company] = await Promise.all([
          api("/renovation/metrics"),
          api("/renovation/customers"),
          api("/renovation/leads"),
          api("/renovation/proposals"),
          api("/renovation/jobs"),
          api("/renovation/account"),
          api("/renovation/accounts"),
          api("/renovation/files"),
          api("/renovation/notifications"),
          api("/renovation/settings/company"),
        ]);
        $("metric-leads").textContent = metrics.total_leads;
        $("metric-jobs").textContent = metrics.active_jobs;
        $("metric-invoiced").textContent = money(metrics.invoiced_revenue);
        $("metric-outstanding").textContent = money(metrics.outstanding_receivables);
        $("metrics").textContent = JSON.stringify(metrics, null, 2);
        if (!customers.items.length) tableEmpty("customers", 3, "No customers yet.");
        else $("customers").innerHTML = customers.items.map((record) => {
          const item = artifact(record);
          return `<tr><td>${item.name || item.customer_id}</td><td>${item.email || "-"}</td><td>${item.phone || "-"}</td></tr>`;
        }).join("");
        if (!leads.items.length) tableEmpty("leads", 4, "No leads yet.");
        else $("leads").innerHTML = leads.items.map((record) => {
          const item = artifact(record);
          return `<tr><td>${item.name || item.lead_id}</td><td>${item.status || "-"}</td><td>${item.project_type || "-"}</td><td>${item.customer_id || "-"}</td></tr>`;
        }).join("");
        if (!proposals.items.length) tableEmpty("proposals", 4, "No proposals yet.");
        else $("proposals").innerHTML = proposals.items.map((record) => {
          const item = artifact(record);
          const customer = item.customer || {};
          const estimate = item.estimate || {};
          return `<tr><td>${item.proposal_id}</td><td>${record.status || item.status || "-"}</td><td>${customer.name || customer.customer_id || "-"}</td><td>${money(estimate.total)}</td></tr>`;
        }).join("");
        if (!jobs.items.length) {
          tableEmpty("jobs", 4, "No jobs yet.");
          $("job-select").innerHTML = "";
        } else {
          $("jobs").innerHTML = jobs.items.map((record) => {
            const item = artifact(record);
            return `<tr data-job-id="${item.job_id}"><td>${item.job_id}</td><td>${item.status}</td><td>${item.project_id || "-"}</td><td>${item.customer_id || "-"}</td></tr>`;
          }).join("");
          $("job-select").innerHTML = jobs.items.map((record) => {
            const item = artifact(record);
            return `<option value="${item.job_id}">${item.job_id} (${item.status})</option>`;
          }).join("");
          document.querySelectorAll("tr[data-job-id]").forEach((row) => {
            row.addEventListener("click", async () => {
              $("job-select").value = row.dataset.jobId;
              await loadJobPanels();
            });
          });
          if (!$("job-select").value) $("job-select").value = artifact(jobs.items[0]).job_id;
          await loadJobPanels();
        }
      } catch (err) {
        $("metrics").textContent = "Unable to load cockpit.";
        $("error").textContent = err.message;
      }
    }
    async function loadJobPanels() {
      const jobId = selectedJobId();
      if (!jobId) return;
      try {
        const [schedule, costs, profitability, invoices, portal] = await Promise.all([
          api(`/renovation/jobs/${jobId}/schedule`),
          api(`/renovation/jobs/${jobId}/costs`),
          api(`/renovation/jobs/${jobId}/profitability`).catch((err) => ({error: err.message})),
          api(`/renovation/jobs/${jobId}/invoices`),
          api(`/renovation/jobs/${jobId}/portal`).catch((err) => ({error: err.message})),
        ]);
        $("schedule-view").textContent = JSON.stringify(schedule, null, 2);
        $("profitability").textContent = JSON.stringify({costs, profitability}, null, 2);
        $("job-portal").textContent = JSON.stringify(portal, null, 2);
        $("invoice-select").innerHTML = invoices.items.map((record) => {
          const item = artifact(record);
          return `<option value="${item.invoice_id}">${item.invoice_id} (${money(item.outstanding_balance)})</option>`;
        }).join("");
      } catch (err) {
        $("error").textContent = err.message;
      }
    }
    function renderRun(run) {
      selectedRunId = run.run_id;
      $("status").textContent = run.status;
      $("run-id").textContent = run.run_id;
      $("balance").textContent = run.steps?.invoice_payment?.output?.invoice
        ? `$${Number(run.steps.invoice_payment.output.invoice.outstanding_balance).toFixed(2)}`
        : "-";
      $("margin").textContent = run.financial_summary?.actual_margin_percentage !== undefined
        ? `${Number(run.financial_summary.actual_margin_percentage).toFixed(2)}%`
        : "-";
      $("financial").textContent = JSON.stringify(run.financial_summary || {}, null, 2);
      $("portal").textContent = JSON.stringify({portal: run.portal || {}, customer_status: run.customer_status || {}}, null, 2);
      $("raw").textContent = JSON.stringify(run, null, 2);
      const steps = run.steps || {};
      $("timeline").innerHTML = Object.keys(steps).map((name) => {
        const status = steps[name].status || "pending";
        return `<div class="step ${status}"><strong>${name}</strong><span>${status}</span></div>`;
      }).join("");
    }
    async function refreshRuns() {
      try {
        const data = await api("/renovation/mvp/runs");
        if (!data.items.length) {
          $("runs").innerHTML = `<tr><td colspan="4" class="empty">No MVP runs yet.</td></tr>`;
          return;
        }
        $("runs").innerHTML = data.items.map((run) => `
          <tr data-run-id="${run.run_id}">
            <td>${run.run_id}</td>
            <td>${run.status}</td>
            <td>${run.entity_ids?.job_id || "-"}</td>
            <td>${run.failed_step || "-"}</td>
          </tr>`).join("");
        document.querySelectorAll("tr[data-run-id]").forEach((row) => {
          row.addEventListener("click", async () => renderRun(await api(`/renovation/mvp/runs/${row.dataset.runId}`)));
        });
      } catch (err) {
        $("error").textContent = err.message;
      }
    }
    async function createRun(payload) {
      $("status").textContent = "Running";
      const run = await api("/renovation/mvp/runs", {method: "POST", body: JSON.stringify(payload)});
      renderRun(run);
      await refreshRuns();
      await loadCockpit();
    }
    $("run-demo").addEventListener("click", async () => {
      try { await createRun($("idempotency").value.trim() ? {idempotency_key: $("idempotency").value.trim()} : {}); }
      catch (err) { $("status").textContent = "Error"; $("error").textContent = err.message; }
    });
    $("run-custom").addEventListener("click", async () => {
      try { await createRun(customPayload()); }
      catch (err) { $("status").textContent = "Error"; $("error").textContent = err.message; }
    });
    $("replay").addEventListener("click", async () => {
      if (!selectedRunId) return;
      try { renderRun(await api(`/renovation/mvp/runs/${selectedRunId}/replay`, {method: "POST", body: "{}"})); await refreshRuns(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("resume").addEventListener("click", async () => {
      if (!selectedRunId) return;
      try { renderRun(await api(`/renovation/mvp/runs/${selectedRunId}/resume`, {method: "POST", body: "{}"})); await refreshRuns(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("refresh").addEventListener("click", async () => {
      await loadCockpit();
      await refreshRuns();
    });
    $("job-select").addEventListener("change", loadJobPanels);
    $("create-lead").addEventListener("click", async () => {
      try { await api("/renovation/leads", {method: "POST", body: $("lead-json").value}); await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("create-estimate").addEventListener("click", async () => {
      try { await api("/renovation/estimates", {method: "POST", body: $("estimate-json").value}); await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("update-status").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try {
        await api(`/renovation/jobs/${jobId}/status`, {method: "PATCH", body: JSON.stringify({status: $("job-status").value})});
        await loadCockpit();
      } catch (err) { $("error").textContent = err.message; }
    });
    $("create-schedule").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try { await api(`/renovation/jobs/${jobId}/schedule`, {method: "POST", body: $("schedule-json").value}); await loadJobPanels(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("create-cost").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try {
        await api(`/renovation/jobs/${jobId}/costs`, {method: "POST", body: JSON.stringify({
          cost_date: "2026-07-10",
          category: "overhead",
          description: "Manual cockpit cost",
          amount: Number(JSON.parse($("finance-json").value).amount || 0)
        })});
        await loadCockpit();
      } catch (err) { $("error").textContent = err.message; }
    });
    $("create-invoice").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try { await api(`/renovation/jobs/${jobId}/invoices`, {method: "POST", body: $("finance-json").value}); await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("record-payment").addEventListener("click", async () => {
      const invoiceId = $("invoice-select").value;
      if (!invoiceId) return;
      try { await api(`/renovation/invoices/${invoiceId}/payments`, {method: "POST", body: $("payment-json").value}); await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    loadCockpit();
    refreshRuns();
  </script>
</body>
</html>"""


def _renovation_app_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RenovationOS Cockpit</title>
  <style>
    :root {
      color-scheme: light;
      --ink: #202833;
      --muted: #657282;
      --line: #d9e0e8;
      --panel: #ffffff;
      --panel-soft: #fbfcfd;
      --page: #f5f7f9;
      --accent: #176e5f;
      --accent-strong: #105044;
      --soft: #e7f3f0;
      --info: #245b9a;
      --good: #14784f;
      --warn: #a35412;
      --bad: #b42318;
      --shadow: 0 8px 24px rgba(32, 40, 51, .07);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--page);
      color: var(--ink);
    }
    header {
      position: sticky;
      top: 0;
      z-index: 10;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      padding: 14px 24px;
      border-bottom: 1px solid var(--line);
      background: rgba(255, 255, 255, .96);
      backdrop-filter: blur(10px);
    }
    h1 { margin: 0; font-size: 21px; letter-spacing: 0; }
    h2 { margin: 0 0 12px; font-size: 16px; }
    h3 { margin: 14px 0 8px; font-size: 13px; color: var(--muted); }
    .subhead { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
    .header-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      min-height: 28px;
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 5px 10px;
      color: var(--muted);
      background: #f7f9fb;
      font-size: 12px;
      font-weight: 650;
    }
    .status-pill.connected {
      border-color: #9dcbbd;
      color: var(--accent-strong);
      background: var(--soft);
    }
    main { display: grid; grid-template-columns: 316px minmax(0, 1fr); min-height: calc(100vh - 61px); }
    aside {
      padding: 20px;
      border-right: 1px solid var(--line);
      background: var(--panel);
    }
    section { padding: 22px; }
    nav { display: grid; gap: 8px; margin: 18px 0; }
    nav a {
      color: var(--ink);
      text-decoration: none;
      padding: 9px 11px;
      border-radius: 6px;
      border: 1px solid transparent;
      border-left: 3px solid transparent;
      font-size: 13px;
    }
    nav a:hover { background: var(--soft); border-color: var(--line); border-left-color: var(--accent); }
    label { display: block; margin: 12px 0 6px; color: var(--muted); font-size: 13px; }
    input, textarea, select {
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px 11px;
      font: inherit;
      background: white;
      color: var(--ink);
    }
    input:focus, textarea:focus, select:focus {
      outline: 2px solid rgba(23, 110, 95, .2);
      border-color: #8abfaf;
    }
    textarea { min-height: 78px; resize: vertical; }
    button {
      margin-top: 14px;
      border: 0;
      border-radius: 6px;
      padding: 11px 14px;
      font: inherit;
      font-weight: 650;
      color: white;
      background: var(--accent);
      cursor: pointer;
    }
    button:hover { background: var(--accent-strong); }
    button:disabled { cursor: wait; opacity: .65; }
    .button-row { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .button-row button { width: 100%; }
    .secondary { background: #3f4f5f; }
    .secondary:hover { background: #2f3d4a; }
    .quiet { background: #edf2f5; color: var(--ink); }
    .quiet:hover { background: #dfe8ee; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 16px; }
    .form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; }
    .full { grid-column: 1 / -1; }
    .section-title {
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 12px;
      margin: 0 0 14px;
    }
    .section-title h2 { margin: 0; font-size: 18px; }
    .section-title span { color: var(--muted); font-size: 12px; }
    .metric, .panel, .notice {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: var(--shadow);
    }
    .panel { margin: 14px 0 0; scroll-margin-top: 82px; }
    .panel h2 {
      display: flex;
      align-items: center;
      min-height: 24px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--line);
    }
    .tool-panel { min-height: 100%; }
    .metric {
      position: relative;
      min-height: 88px;
      border-top: 4px solid var(--accent);
    }
    .metric:nth-child(2) { border-top-color: var(--info); }
    .metric:nth-child(3) { border-top-color: var(--good); }
    .metric:nth-child(4) { border-top-color: var(--warn); }
    .metric span { display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
    .metric strong { display: block; font-size: 20px; overflow-wrap: anywhere; line-height: 1.2; }
    .notice { color: var(--muted); font-size: 13px; line-height: 1.45; }
    .notice strong { color: var(--ink); display: block; margin-bottom: 4px; }
    .hint { color: var(--muted); font-size: 13px; line-height: 1.45; margin: 12px 0 0; }
    .table-wrap { overflow-x: auto; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; min-width: 560px; }
    th, td { border-bottom: 1px solid var(--line); padding: 10px 9px; text-align: left; vertical-align: top; }
    th { color: var(--muted); font-weight: 650; background: var(--panel-soft); }
    tbody tr:last-child td { border-bottom: 0; }
    tr[data-run-id], tr[data-job-id] { cursor: pointer; }
    tbody tr:hover { background: #f9fbfc; }
    tr[data-run-id]:hover, tr[data-job-id]:hover { background: var(--soft); }
    .badge {
      display: inline-block;
      border-radius: 999px;
      padding: 3px 8px;
      background: #eef2f6;
      color: #384454;
      font-size: 12px;
      font-weight: 650;
      text-transform: capitalize;
    }
    .badge.good { background: #e5f5ec; color: var(--good); }
    .badge.warn { background: #fff4df; color: var(--warn); }
    .badge.bad { background: #fff0ee; color: var(--bad); }
    .timeline { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
    .step { border: 1px solid var(--line); border-radius: 6px; padding: 9px; background: #fbfcfd; }
    .step strong { display: block; font-size: 12px; overflow-wrap: anywhere; text-transform: capitalize; }
    .step span { color: var(--muted); font-size: 12px; }
    .completed { border-color: #8abfaf; background: #eef8f4; }
    .failed { border-color: #e09a91; background: #fff1ef; }
    .running { border-color: #d8ad5b; background: #fff8e8; }
    .summary-list { display: grid; gap: 7px; font-size: 13px; }
    .summary-line { display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid var(--line); padding: 7px 0; }
    .summary-line span { color: var(--muted); }
    .summary-line strong { text-align: right; }
    .empty {
      color: var(--muted);
      padding: 13px;
      border: 1px dashed var(--line);
      border-radius: 6px;
      background: var(--panel-soft);
    }
    td.empty { border: 0; }
    .error { color: var(--bad); }
    .success { color: var(--good); }
    @media (max-width: 900px) {
      header { position: static; align-items: flex-start; }
      main { grid-template-columns: 1fr; }
      aside { border-right: 0; border-bottom: 1px solid var(--line); }
      .grid, .form-grid, .timeline { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .panel { scroll-margin-top: 16px; }
    }
    @media (max-width: 620px) {
      header, .section-title { flex-direction: column; align-items: flex-start; }
      .grid, .form-grid, .timeline { grid-template-columns: 1fr; }
      .full { grid-column: auto; }
      table { min-width: 480px; }
    }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>RenovationOS</h1>
      <p class="subhead">Operator cockpit</p>
    </div>
    <div class="header-actions">
      <span id="header-access" class="status-pill">Not connected</span>
      <span class="badge">Local demo</span>
    </div>
  </header>
  <main>
    <aside>
      <div class="notice">
        <strong>Local access</strong>
        <div id="access-state">Connect the local demo account to load records and take actions.</div>
      </div>
      <label for="bootstrap-token">Local setup key</label>
      <input id="bootstrap-token" type="password" autocomplete="off" value="bootstrap-dev">
      <label for="principal-id">User</label>
      <input id="principal-id" autocomplete="off" value="owner-a">
      <button id="connect-access">Connect Workspace</button>
      <button id="refresh" class="secondary">Refresh Workspace</button>
      <nav>
        <a href="#dashboard">Dashboard</a>
        <a href="#lead-panel">Lead Intake</a>
        <a href="#estimate-panel">Estimate Builder</a>
        <a href="#job-panel">Jobs & Schedule</a>
        <a href="#finance-panel">Costs & Invoices</a>
        <a href="#portal-panel">Customer Portal</a>
        <a href="#files-panel">Files</a>
        <a href="#settings-panel">Settings</a>
        <a href="#demo-panel">Demo Runs</a>
      </nav>
      <label for="idempotency">Demo run name</label>
      <input id="idempotency" autocomplete="off" placeholder="kitchen-demo-001">
      <div class="button-row">
        <button id="run-demo">Run Sample Job</button>
        <button id="resume" class="secondary">Resume Run</button>
      </div>
      <button id="replay" class="quiet">Replay Selected Run</button>
      <p id="error" class="hint error"></p>
      <p id="success" class="hint success"></p>
    </aside>
    <section>
      <div class="section-title">
        <h2>Today</h2>
        <span id="last-updated">Not loaded</span>
      </div>
      <div id="dashboard" class="grid">
        <div class="metric"><span>Total leads</span><strong id="metric-leads">-</strong></div>
        <div class="metric"><span>Active jobs</span><strong id="metric-jobs">-</strong></div>
        <div class="metric"><span>Invoiced revenue</span><strong id="metric-invoiced">-</strong></div>
        <div class="metric"><span>Outstanding</span><strong id="metric-outstanding">-</strong></div>
      </div>
      <div class="panel">
        <h2>Dashboard Summary</h2>
        <div id="metrics" class="summary-list"><div class="empty">Connect the local workspace to load dashboard metrics.</div></div>
      </div>
      <div class="grid">
        <div id="lead-panel" class="panel tool-panel">
          <h2>Lead Intake</h2>
          <label for="lead-name">Customer name</label>
          <input id="lead-name" value="Morgan Homeowner">
          <label for="lead-email">Email</label>
          <input id="lead-email" value="morgan@example.com">
          <label for="lead-phone">Phone</label>
          <input id="lead-phone" value="555-0140">
          <label for="lead-address">Property address</label>
          <input id="lead-address" value="200 Oak Street">
          <label for="lead-project">Project type</label>
          <select id="lead-project">
            <option value="kitchen_remodel">Kitchen remodel</option>
            <option value="bathroom_remodel">Bathroom remodel</option>
            <option value="basement_finish">Basement finish</option>
            <option value="whole_home">Whole home</option>
          </select>
          <label for="lead-description">Project notes</label>
          <textarea id="lead-description">Replace cabinets, counters, and flooring.</textarea>
          <button id="create-lead">Create Lead</button>
        </div>
        <div id="estimate-panel" class="panel tool-panel">
          <h2>Estimate Builder</h2>
          <label for="estimate-title">Project name</label>
          <input id="estimate-title" value="Kitchen Remodel">
          <label for="room-name">Room</label>
          <input id="room-name" value="Kitchen">
          <div class="form-grid">
            <div><label for="room-length">Length ft</label><input id="room-length" type="number" value="20"></div>
            <div><label for="room-width">Width ft</label><input id="room-width" type="number" value="15"></div>
            <div><label for="cabinet-count">Cabinets</label><input id="cabinet-count" type="number" value="10"></div>
            <div><label for="flooring-sqft">Flooring sqft</label><input id="flooring-sqft" type="number" value="300"></div>
            <div><label for="labor-rate">Labor rate</label><input id="labor-rate" type="number" value="65"></div>
            <div><label for="tax-rate">Tax %</label><input id="tax-rate" type="number" value="6"></div>
          </div>
          <label for="scope-description">Scope</label>
          <textarea id="scope-description">Cabinet replacement
Flooring replacement</textarea>
          <button id="create-estimate">Create Estimate</button>
        </div>
        <div id="job-panel" class="panel tool-panel">
          <h2>Job Action</h2>
          <label for="job-select">Selected job</label>
          <select id="job-select"></select>
          <label for="job-status">Status</label>
          <select id="job-status">
            <option value="planned">Planned</option>
            <option value="active">Active</option>
            <option value="on_hold">On hold</option>
            <option value="completed">Completed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button id="update-status">Update Status</button>
        </div>
        <div id="finance-panel" class="panel tool-panel">
          <h2>Cost / Invoice</h2>
          <label for="finance-description">Description</label>
          <input id="finance-description" value="Project deposit">
          <label for="finance-amount">Amount</label>
          <input id="finance-amount" type="number" value="5000">
          <label for="finance-date">Date</label>
          <input id="finance-date" type="date" value="2026-07-01">
          <label for="finance-due">Invoice due date</label>
          <input id="finance-due" type="date" value="2026-07-15">
          <div class="button-row">
            <button id="create-cost" class="secondary">Record Cost</button>
            <button id="create-invoice">Create Invoice</button>
          </div>
        </div>
      </div>
      <div class="panel">
        <h2>Customer List</h2>
        <div class="table-wrap"><table><thead><tr><th>Customer</th><th>Email</th><th>Phone</th></tr></thead><tbody id="customers"><tr><td colspan="3" class="empty">Connect workspace to load customers.</td></tr></tbody></table></div>
      </div>
      <div class="panel">
        <h2>Lead Pipeline</h2>
        <div class="table-wrap"><table><thead><tr><th>Lead</th><th>Status</th><th>Project</th><th>Next action</th></tr></thead><tbody id="lead-table"><tr><td colspan="4" class="empty">Create a lead or run the sample job.</td></tr></tbody></table></div>
      </div>
      <div class="panel">
        <h2>Proposal View</h2>
        <div class="table-wrap"><table><thead><tr><th>Proposal</th><th>Status</th><th>Customer</th><th>Total</th><th>Actions</th></tr></thead><tbody id="proposals"><tr><td colspan="5" class="empty">Approved estimates and proposals will appear here.</td></tr></tbody></table></div>
      </div>
      <div class="panel">
        <h2>Job Board</h2>
        <div class="table-wrap"><table><thead><tr><th>Job</th><th>Status</th><th>Project</th><th>Customer</th></tr></thead><tbody id="job-table"><tr><td colspan="4" class="empty">Accepted proposals become jobs.</td></tr></tbody></table></div>
      </div>
      <div id="files-panel" class="panel">
        <h2>Files</h2>
        <div class="form-grid">
          <div>
            <label for="file-entity-type">Record type</label>
            <select id="file-entity-type">
              <option value="customer">Customer</option>
              <option value="lead">Lead</option>
              <option value="estimate">Estimate</option>
              <option value="proposal">Proposal</option>
              <option value="job">Job</option>
              <option value="invoice">Invoice</option>
              <option value="payment">Payment</option>
            </select>
          </div>
          <div><label for="file-entity-id">Record ID</label><input id="file-entity-id" placeholder="Paste record ID"></div>
          <div class="full"><label for="file-upload">Attachment</label><input id="file-upload" type="file"></div>
        </div>
        <button id="upload-file">Upload File</button>
        <div class="table-wrap"><table><thead><tr><th>File</th><th>Record</th><th>Size</th><th>Actions</th></tr></thead><tbody id="files"><tr><td colspan="4" class="empty">No files loaded.</td></tr></tbody></table></div>
      </div>
      <div id="settings-panel" class="panel">
        <h2>Settings</h2>
        <div id="account-context" class="summary-list"><div class="empty">Connect workspace to see account permissions.</div></div>
        <div class="form-grid">
          <div><label for="company-name">Company name</label><input id="company-name" value="RenovationOS Demo Co."></div>
          <div><label for="company-email">Company email</label><input id="company-email" value="office@example.com"></div>
          <div><label for="account-id">Account ID</label><input id="account-id" value="operator-a"></div>
          <div>
            <label for="account-role">Role</label>
            <select id="account-role">
              <option value="operator">Operator</option>
              <option value="viewer">Viewer</option>
              <option value="owner">Owner</option>
            </select>
          </div>
        </div>
        <button id="save-company">Save Branding</button>
        <button id="assign-role" class="secondary">Assign Role</button>
        <div class="table-wrap"><table><thead><tr><th>Account</th><th>Role</th><th>Status</th></tr></thead><tbody id="accounts"><tr><td colspan="3" class="empty">No accounts loaded.</td></tr></tbody></table></div>
        <h3>Integrations</h3>
        <div class="notice">
          <strong>Local-safe provider mode</strong>
          Email, SMS, calendar, and payment providers use deterministic shells unless live provider credentials are configured.
        </div>
        <div class="table-wrap"><table><thead><tr><th>Provider</th><th>Mode</th><th>Status</th><th>Required setup</th><th>Last error</th><th>Action</th></tr></thead><tbody id="integrations"><tr><td colspan="6" class="empty">No integration status loaded.</td></tr></tbody></table></div>
        <div id="integration-result" class="summary-list"><div class="empty">Validation results will appear here.</div></div>
        <h3>Notification History</h3>
        <div class="table-wrap"><table><thead><tr><th>Event</th><th>Channel</th><th>Status</th></tr></thead><tbody id="notifications"><tr><td colspan="3" class="empty">No notifications loaded.</td></tr></tbody></table></div>
      </div>
      <div class="grid">
        <div class="panel">
          <h2>Schedule View</h2>
          <label for="schedule-date">Start date</label>
          <input id="schedule-date" type="date" value="2026-07-06">
          <button id="create-schedule">Add Schedule</button>
          <button id="sync-calendar" class="secondary">Sync Calendar</button>
          <div id="schedule-view" class="summary-list"><div class="empty">Select a job to see schedule items.</div></div>
          <div id="calendar-status" class="summary-list"><div class="empty">No calendar sync yet.</div></div>
        </div>
        <div class="panel">
          <h2>Cost / Profitability</h2>
          <div id="profitability" class="summary-list"><div class="empty">Select a job to see costs and margin.</div></div>
        </div>
        <div class="panel">
          <h2>Invoice / Payment</h2>
          <label for="invoice-select">Invoice</label>
          <select id="invoice-select"></select>
          <label for="payment-amount">Payment amount</label>
          <input id="payment-amount" type="number" value="1000">
          <label for="payment-date">Payment date</label>
          <input id="payment-date" type="date" value="2026-07-05">
          <label for="payment-method">Method</label>
          <select id="payment-method">
            <option value="ach">ACH</option>
            <option value="card">Card</option>
            <option value="check">Check</option>
            <option value="cash">Cash</option>
          </select>
          <button id="record-payment">Record Payment</button>
          <button id="create-payment-link" class="secondary">Create Payment Link</button>
          <button id="invoice-pdf" class="quiet">Invoice PDF</button>
        </div>
        <div id="portal-panel" class="panel">
          <h2>Customer Portal Preview</h2>
          <div id="job-portal" class="summary-list"><div class="empty">Select a job to preview customer-facing status.</div></div>
        </div>
      </div>
      <div id="demo-panel" class="grid">
        <div class="metric"><span>MVP status</span><strong id="status">Idle</strong></div>
        <div class="metric"><span>MVP run</span><strong id="run-id">-</strong></div>
        <div class="metric"><span>Invoice balance</span><strong id="balance">-</strong></div>
        <div class="metric"><span>Margin</span><strong id="margin">-</strong></div>
      </div>
      <div class="panel">
        <h2>MVP Runs / Replay / Resume</h2>
        <div class="table-wrap"><table>
          <thead><tr><th>Run</th><th>Status</th><th>Job</th><th>Failed Step</th></tr></thead>
          <tbody id="runs"><tr><td colspan="4" class="empty">No runs loaded.</td></tr></tbody>
        </table></div>
      </div>
      <div class="panel">
        <h2>Workflow Timeline</h2>
        <div id="timeline" class="timeline"><div class="empty">Select or create a run.</div></div>
      </div>
      <div class="panel">
        <h2>Financial Summary</h2>
        <div id="financial" class="summary-list"><div class="empty">Run a sample job to see revenue, cost, and margin.</div></div>
      </div>
      <div class="panel">
        <h2>Run Notes</h2>
        <div id="run-notes" class="summary-list"><div class="empty">Selected run details will appear as plain-language notes.</div></div>
      </div>
    </section>
  </main>
  <script>
    const $ = (id) => document.getElementById(id);
    let accessToken = "";
    let selectedRunId = "";

    function headers() {
      return {"Content-Type": "application/json", ...(accessToken ? {"Authorization": `Bearer ${accessToken}`} : {})};
    }
    async function api(path, options = {}) {
      $("error").textContent = "";
      $("success").textContent = "";
      const response = await fetch(path, {...options, headers: {...headers(), ...(options.headers || {})}});
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(readableError(data, response.status));
      return data;
    }
    function readableError(data, status) {
      if (status === 401) return "Connect the local workspace before loading or changing records.";
      if (status === 403) return "This user can view records but cannot make that change.";
      if (status === 404) return "That record was not found. Refresh the workspace and try again.";
      return data?.error?.message || data?.detail || "Something went wrong.";
    }
    function money(value) { return `$${Number(value || 0).toFixed(2)}`; }
    function pct(value) { return `${Number(value || 0).toFixed(1)}%`; }
    function artifact(record) { return record?.artifact || record || {}; }
    function selectedJobId() { return $("job-select").value; }
    function line(label, value) {
      return `<div class="summary-line"><span>${label}</span><strong>${value ?? "-"}</strong></div>`;
    }
    function tableEmpty(id, cols, text) {
      $(id).innerHTML = `<tr><td colspan="${cols}" class="empty">${text}</td></tr>`;
    }
    function statusBadge(status) {
      const normalized = String(status || "unknown");
      const good = ["completed", "paid", "accepted", "approved", "won"];
      const warn = ["planned", "active", "new", "contacted", "sent", "partial"];
      const cls = good.includes(normalized) ? "good" : warn.includes(normalized) ? "warn" : "";
      return `<span class="badge ${cls}">${normalized.replaceAll("_", " ")}</span>`;
    }
    async function connectAccess() {
      const bootstrap = $("bootstrap-token").value.trim();
      const principal = $("principal-id").value.trim() || "owner-a";
      $("access-state").textContent = "Connecting...";
      try {
        let issued = await fetch("/auth/token/issue", {
          method: "POST",
          headers: {"Content-Type": "application/json", "X-AgentFabric-Bootstrap-Token": bootstrap},
          body: JSON.stringify({principal_id: principal})
        });
        if (issued.status === 404) {
          await fetch("/auth/principals/register", {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-AgentFabric-Bootstrap-Token": bootstrap},
            body: JSON.stringify({principal_id: principal, tenant_id: "tenant-a", role: "owner", scopes: []})
          });
          issued = await fetch("/auth/token/issue", {
            method: "POST",
            headers: {"Content-Type": "application/json", "X-AgentFabric-Bootstrap-Token": bootstrap},
            body: JSON.stringify({principal_id: principal})
          });
        }
        const token = await issued.json();
        if (!issued.ok) throw new Error(readableError(token, issued.status));
      accessToken = token.access_token;
      await api("/tenants", {method: "POST", body: JSON.stringify({tenant_id: "tenant-a", organization_id: "org-a", name: "Tenant A", billing_plan: "enterprise"})}).catch(() => undefined);
      $("access-state").textContent = `Connected as ${principal}.`;
      $("header-access").textContent = `Connected: ${principal}`;
      $("header-access").classList.add("connected");
      $("success").textContent = "Workspace connected.";
      await loadCockpit();
      await refreshRuns();
    } catch (err) {
      $("access-state").textContent = "Not connected.";
      $("header-access").textContent = "Not connected";
      $("header-access").classList.remove("connected");
      $("error").textContent = err.message;
    }
    }
    function leadPayload() {
      return {
        name: $("lead-name").value,
        email: $("lead-email").value,
        phone: $("lead-phone").value,
        property_address: $("lead-address").value,
        project_type: $("lead-project").value,
        description: $("lead-description").value,
        created_date: new Date().toISOString().slice(0, 10),
        source: {source_type: "website", source_name: "cockpit"}
      };
    }
    function estimatePayload() {
      const slug = $("estimate-title").value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "renovation";
      return {
        project_id: `project-${slug}`,
        scope_description: $("scope-description").value,
        rooms: [{name: $("room-name").value, length_ft: Number($("room-length").value), width_ft: Number($("room-width").value), quantity: 1}],
        quantities: {cabinetry: Number($("cabinet-count").value), flooring: Number($("flooring-sqft").value)},
        labor_rate: Number($("labor-rate").value),
        contingency_percentage: 10,
        tax_percentage: Number($("tax-rate").value),
        notes: $("estimate-title").value
      };
    }
    function invoicePayload() {
      return {
        invoice_date: $("finance-date").value,
        due_date: $("finance-due").value,
        description: $("finance-description").value,
        amount: Number($("finance-amount").value),
        tax: 0
      };
    }
    function costPayload() {
      return {
        cost_date: $("finance-date").value,
        category: "overhead",
        description: $("finance-description").value,
        amount: Number($("finance-amount").value),
        allocation_method: "direct"
      };
    }
    async function loadCockpit() {
      try {
        $("metrics").innerHTML = `<div class="empty">Loading dashboard...</div>`;
        const [metrics, customers, leads, proposals, jobs, account, accounts, files, notifications, company, integrations] = await Promise.all([
          api("/renovation/metrics"),
          api("/renovation/customers"),
          api("/renovation/leads"),
          api("/renovation/proposals"),
          api("/renovation/jobs"),
          api("/renovation/account"),
          api("/renovation/accounts"),
          api("/renovation/files"),
          api("/renovation/notifications"),
          api("/renovation/settings/company"),
          api("/renovation/integrations"),
        ]);
        $("metric-leads").textContent = metrics.total_leads;
        $("metric-jobs").textContent = metrics.active_jobs;
        $("metric-invoiced").textContent = money(metrics.invoiced_revenue);
        $("metric-outstanding").textContent = money(metrics.outstanding_receivables);
        $("last-updated").textContent = `Updated ${new Date().toLocaleTimeString([], {hour: "numeric", minute: "2-digit"})}`;
        $("metrics").innerHTML = [
          line("Converted leads", `${metrics.converted_leads} of ${metrics.total_leads}`),
          line("Completed jobs", metrics.completed_jobs),
          line("Estimated revenue", money(metrics.estimated_revenue)),
          line("Paid revenue", money(metrics.paid_revenue)),
          line("Total costs", money(metrics.total_costs)),
          line("Gross profit", money(metrics.gross_profit)),
          line("Gross margin", pct(metrics.gross_margin_percentage)),
          line("Jobs at risk", metrics.jobs_at_risk),
          line("Average estimate", money(metrics.average_estimate_value)),
          line("Average job margin", pct(metrics.average_job_margin))
        ].join("");
        if (!customers.items.length) tableEmpty("customers", 3, "No customers yet.");
        else $("customers").innerHTML = customers.items.map((record) => {
          const item = artifact(record);
          return `<tr><td>${item.name || item.customer_id}</td><td>${item.email || "-"}</td><td>${item.phone || "-"}</td></tr>`;
        }).join("");
        if (!leads.items.length) tableEmpty("lead-table", 4, "No leads yet. Create one from Lead Intake.");
        else $("lead-table").innerHTML = leads.items.map((record) => {
          const item = artifact(record);
          return `<tr><td>${item.name || item.lead_id}</td><td>${statusBadge(item.status)}</td><td>${String(item.project_type || "-").replaceAll("_", " ")}</td><td>${item.customer_id ? "Converted to customer" : "Follow up"}</td></tr>`;
        }).join("");
        if (!proposals.items.length) tableEmpty("proposals", 5, "No proposals yet.");
        else $("proposals").innerHTML = proposals.items.map((record) => {
          const item = artifact(record);
          const customer = item.customer || {};
          const estimate = item.estimate || {};
          return `<tr><td>${item.proposal_id}</td><td>${statusBadge(record.status || item.status)}</td><td>${customer.name || customer.customer_id || "-"}</td><td>${money(estimate.total)}</td><td><button class="quiet proposal-pdf" data-proposal-id="${item.proposal_id}">PDF</button></td></tr>`;
        }).join("");
        if (!jobs.items.length) {
          tableEmpty("job-table", 4, "No jobs yet. Run a sample job to populate this board.");
          $("job-select").innerHTML = `<option value="">No jobs yet</option>`;
        } else {
          $("job-table").innerHTML = jobs.items.map((record) => {
            const item = artifact(record);
            return `<tr data-job-id="${item.job_id}"><td>${item.title || item.job_id}</td><td>${statusBadge(item.status)}</td><td>${item.project_id || "-"}</td><td>${item.customer_id || "-"}</td></tr>`;
          }).join("");
          $("job-select").innerHTML = jobs.items.map((record) => {
            const item = artifact(record);
            return `<option value="${item.job_id}">${item.title || item.job_id}</option>`;
          }).join("");
          document.querySelectorAll("tr[data-job-id]").forEach((row) => {
            row.addEventListener("click", async () => {
              $("job-select").value = row.dataset.jobId;
              await loadJobPanels();
            });
          });
          await loadJobPanels();
        }
        $("account-context").innerHTML = [
          line("Tenant", account.tenant_id),
          line("User", account.principal_id),
          line("Role", account.role),
          line("Can operate", account.permissions?.can_operate ? "Yes" : "No")
        ].join("");
        if (!accounts.items.length) tableEmpty("accounts", 3, "No accounts assigned yet.");
        else $("accounts").innerHTML = accounts.items.map((record) => {
          const item = artifact(record);
          return `<tr><td>${item.account_id}</td><td>${statusBadge(item.role)}</td><td>${item.status || "active"}</td></tr>`;
        }).join("");
        renderFiles(files.items || []);
        renderNotifications(notifications.items || []);
        renderIntegrations(integrations.items || []);
        $("company-name").value = company.artifact?.company_name || "";
        $("company-email").value = company.artifact?.email || "";
      } catch (err) {
        $("metrics").innerHTML = `<div class="empty">Connect the local workspace to load metrics.</div>`;
        $("error").textContent = err.message;
      }
    }
    function renderFiles(items) {
      if (!items.length) {
        tableEmpty("files", 4, "No files uploaded yet.");
        return;
      }
      $("files").innerHTML = items.map((record) => {
        const item = artifact(record);
        return `<tr><td>${item.filename}</td><td>${item.entity_type} / ${item.entity_id}</td><td>${item.size_bytes} bytes</td><td><button class="quiet file-download" data-file-id="${item.attachment_id}">Download</button><button class="secondary file-delete" data-file-id="${item.attachment_id}">Archive</button></td></tr>`;
      }).join("");
    }
    function renderNotifications(items) {
      if (!items.length) {
        tableEmpty("notifications", 3, "No notifications sent yet.");
        return;
      }
      $("notifications").innerHTML = items.map((record) => {
        const item = artifact(record);
        const payload = item.payload || {};
        return `<tr><td>${payload.event_type || "-"}</td><td>${payload.channel || "-"}</td><td>${statusBadge(item.status)}</td></tr>`;
      }).join("");
    }
    function renderIntegrations(items) {
      if (!items.length) {
        tableEmpty("integrations", 6, "No integration status loaded.");
        return;
      }
      $("integrations").innerHTML = items.map((item) => {
        const mode = item.stub_mode ? "Local / stub" : "Configured";
        const status = item.valid ? (item.status || "ready") : "needs setup";
        const checklist = (item.checklist || []).map((entry) => `${entry.configured ? "Ready" : "Missing"}: ${entry.label}${entry.optional ? " (optional)" : ""}`).join("<br>");
        const provider = item.provider_type === "email" ? "smtp" : item.provider_type === "sms" ? "twilio" : item.provider_type === "payment" ? "stripe" : "google";
        const validateType = item.provider_type === "email" || item.provider_type === "sms" ? "notification" : item.provider_type;
        return `<tr data-provider-type="${item.provider_type}" data-validate-type="${validateType}" data-provider="${provider}"><td><strong>${item.provider_type}</strong><div class="hint">${item.setup_instructions || ""}</div></td><td>${mode}</td><td>${statusBadge(status)}</td><td>${checklist || "-"}</td><td>${item.last_error || "-"}</td><td><button class="quiet validate-provider">Validate</button></td></tr>`;
      }).join("");
    }
    async function loadJobPanels() {
      const jobId = selectedJobId();
      if (!jobId) return;
      try {
        const [schedule, costs, profitability, invoices, portal] = await Promise.all([
          api(`/renovation/jobs/${jobId}/schedule`),
          api(`/renovation/jobs/${jobId}/costs`),
          api(`/renovation/jobs/${jobId}/profitability`).catch((err) => ({error: err.message})),
          api(`/renovation/jobs/${jobId}/invoices`),
          api(`/renovation/jobs/${jobId}/portal`).catch((err) => ({error: err.message})),
        ]);
        $("schedule-view").innerHTML = schedule.items?.length
          ? schedule.items.map((record) => {
              const item = artifact(record);
              return line(item.start_date || "Schedule", item.status || item.schedule_id);
            }).join("")
          : `<div class="empty">No schedule yet. Choose a start date and add one.</div>`;
        $("profitability").innerHTML = [
          line("Recorded costs", costs.total || 0),
          line("Estimate margin", profitability.error ? "Not ready" : pct(profitability.estimated_margin_percentage)),
          line("Actual margin", profitability.error ? "Not ready" : pct(profitability.actual_margin_percentage)),
          line("Status", profitability.error ? "Add costs and invoices to calculate" : "Current")
        ].join("");
        $("job-portal").innerHTML = portal.error
          ? `<div class="empty">Portal preview is not ready for this job yet.</div>`
          : [
              line("Project status", portal.project_status),
              line("Last update", portal.generated_date),
              line("Customer-safe summary", portal.summary || "Available")
            ].join("");
        $("invoice-select").innerHTML = invoices.items.length ? invoices.items.map((record) => {
          const item = artifact(record);
          return `<option value="${item.invoice_id}">${item.description || item.invoice_id} - ${money(item.outstanding_balance)} due</option>`;
        }).join("") : `<option value="">No invoices yet</option>`;
        $("calendar-status").innerHTML = `<div class="empty">Use Sync Calendar after adding schedule items.</div>`;
      } catch (err) {
        $("error").textContent = err.message;
      }
    }
    function renderRun(run) {
      selectedRunId = run.run_id;
      $("status").textContent = run.status;
      $("run-id").textContent = run.run_id;
      $("balance").textContent = run.steps?.invoice_payment?.output?.invoice ? money(run.steps.invoice_payment.output.invoice.outstanding_balance) : "-";
      $("margin").textContent = run.financial_summary?.actual_margin_percentage !== undefined ? pct(run.financial_summary.actual_margin_percentage) : "-";
      const financial = run.financial_summary || {};
      $("financial").innerHTML = [
        line("Contract value", money(financial.contract_value)),
        line("Actual costs", money(financial.actual_costs)),
        line("Actual margin", pct(financial.actual_margin_percentage)),
        line("Receivables", money(financial.receivables)),
        line("Payables", money(financial.payables))
      ].join("");
      $("run-notes").innerHTML = [
        line("Run", run.run_id),
        line("Status", run.status),
        line("Job", run.entity_ids?.job_id || "-"),
        line("Customer portal", run.portal?.view_hash ? "Ready" : "Not ready")
      ].join("");
      const steps = run.steps || {};
      $("timeline").innerHTML = Object.keys(steps).map((name) => {
        const status = steps[name].status || "pending";
        return `<div class="step ${status}"><strong>${name.replaceAll("_", " ")}</strong><span>${status}</span></div>`;
      }).join("");
    }
    async function refreshRuns() {
      try {
        const data = await api("/renovation/mvp/runs");
        if (!data.items.length) {
          tableEmpty("runs", 4, "No MVP runs yet.");
          return;
        }
        $("runs").innerHTML = data.items.map((run) => `
          <tr data-run-id="${run.run_id}">
            <td>${run.run_id}</td>
            <td>${statusBadge(run.status)}</td>
            <td>${run.entity_ids?.job_id || "-"}</td>
            <td>${run.failed_step || "-"}</td>
          </tr>`).join("");
        document.querySelectorAll("tr[data-run-id]").forEach((row) => {
          row.addEventListener("click", async () => renderRun(await api(`/renovation/mvp/runs/${row.dataset.runId}`)));
        });
      } catch (err) {
        $("error").textContent = err.message;
      }
    }
    async function createRun(payload) {
      $("status").textContent = "Running";
      const run = await api("/renovation/mvp/runs", {method: "POST", body: JSON.stringify(payload)});
      renderRun(run);
      await refreshRuns();
      await loadCockpit();
    }
    $("connect-access").addEventListener("click", connectAccess);
    $("refresh").addEventListener("click", async () => { await loadCockpit(); await refreshRuns(); });
    $("run-demo").addEventListener("click", async () => {
      try { await createRun($("idempotency").value.trim() ? {idempotency_key: $("idempotency").value.trim()} : {}); }
      catch (err) { $("status").textContent = "Error"; $("error").textContent = err.message; }
    });
    $("replay").addEventListener("click", async () => {
      if (!selectedRunId) return;
      try { renderRun(await api(`/renovation/mvp/runs/${selectedRunId}/replay`, {method: "POST", body: "{}"})); await refreshRuns(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("resume").addEventListener("click", async () => {
      if (!selectedRunId) return;
      try { renderRun(await api(`/renovation/mvp/runs/${selectedRunId}/resume`, {method: "POST", body: "{}"})); await refreshRuns(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("job-select").addEventListener("change", loadJobPanels);
    $("create-lead").addEventListener("click", async () => {
      try { await api("/renovation/leads", {method: "POST", body: JSON.stringify(leadPayload())}); $("success").textContent = "Lead created."; await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("create-estimate").addEventListener("click", async () => {
      try { await api("/renovation/estimates", {method: "POST", body: JSON.stringify(estimatePayload())}); $("success").textContent = "Estimate created."; await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("update-status").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try { await api(`/renovation/jobs/${jobId}/status`, {method: "PATCH", body: JSON.stringify({status: $("job-status").value})}); $("success").textContent = "Job status updated."; await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("create-schedule").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try { await api(`/renovation/jobs/${jobId}/schedule`, {method: "POST", body: JSON.stringify({start_date: $("schedule-date").value})}); $("success").textContent = "Schedule added."; await loadJobPanels(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("create-cost").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try { await api(`/renovation/jobs/${jobId}/costs`, {method: "POST", body: JSON.stringify(costPayload())}); $("success").textContent = "Cost recorded."; await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("create-invoice").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try { await api(`/renovation/jobs/${jobId}/invoices`, {method: "POST", body: JSON.stringify(invoicePayload())}); $("success").textContent = "Invoice created."; await loadCockpit(); }
      catch (err) { $("error").textContent = err.message; }
    });
    $("record-payment").addEventListener("click", async () => {
      const invoiceId = $("invoice-select").value;
      if (!invoiceId) return;
      try {
        await api(`/renovation/invoices/${invoiceId}/payments`, {method: "POST", body: JSON.stringify({payment_date: $("payment-date").value, amount: Number($("payment-amount").value), method: $("payment-method").value})});
        $("success").textContent = "Payment recorded.";
        await loadCockpit();
      } catch (err) { $("error").textContent = err.message; }
    });
    $("create-payment-link").addEventListener("click", async () => {
      const invoiceId = $("invoice-select").value;
      if (!invoiceId) return;
      try {
        const link = await api(`/renovation/invoices/${invoiceId}/payment-link`, {method: "POST", body: JSON.stringify({idempotency_key: invoiceId})});
        $("success").textContent = `Payment link ready: ${link.artifact?.payload?.payment_url || "created"}`;
      } catch (err) { $("error").textContent = err.message; }
    });
    $("invoice-pdf").addEventListener("click", () => {
      const invoiceId = $("invoice-select").value;
      if (!invoiceId || !accessToken) return;
      downloadWithAuth(`/renovation/invoices/${invoiceId}/pdf`, `${invoiceId}.pdf`);
    });
    $("upload-file").addEventListener("click", async () => {
      const file = $("file-upload").files[0];
      const entityId = $("file-entity-id").value.trim();
      if (!file || !entityId) return;
      const form = new FormData();
      form.append("file", file);
      try {
        const response = await fetch(`/renovation/files/${$("file-entity-type").value}/${entityId}`, {
          method: "POST",
          headers: accessToken ? {"Authorization": `Bearer ${accessToken}`} : {},
          body: form
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(readableError(data, response.status));
        $("success").textContent = "File uploaded.";
        await loadCockpit();
      } catch (err) { $("error").textContent = err.message; }
    });
    $("assign-role").addEventListener("click", async () => {
      try {
        await api("/renovation/accounts/roles", {method: "POST", body: JSON.stringify({account_id: $("account-id").value.trim(), principal_id: $("account-id").value.trim(), role: $("account-role").value})});
        $("success").textContent = "Role assigned.";
        await loadCockpit();
      } catch (err) { $("error").textContent = err.message; }
    });
    $("save-company").addEventListener("click", async () => {
      try {
        await api("/renovation/settings/company", {method: "PATCH", body: JSON.stringify({company_name: $("company-name").value, email: $("company-email").value})});
        $("success").textContent = "Branding saved.";
        await loadCockpit();
      } catch (err) { $("error").textContent = err.message; }
    });
    $("sync-calendar").addEventListener("click", async () => {
      const jobId = selectedJobId();
      if (!jobId) return;
      try {
        const schedule = await api(`/renovation/jobs/${jobId}/schedule`);
        const first = schedule.items?.[0]?.artifact;
        if (!first) return;
        const sync = await api(`/renovation/schedule/${first.schedule_id}/sync`, {method: "POST", body: JSON.stringify({provider: "local"})});
        $("calendar-status").innerHTML = [line("Status", sync.artifact?.status), line("External event", sync.artifact?.payload?.external_event_id || "-")].join("");
      } catch (err) { $("error").textContent = err.message; }
    });
    $("files").addEventListener("click", async (event) => {
      const fileId = event.target?.dataset?.fileId;
      if (!fileId) return;
      if (event.target.classList.contains("file-download")) {
        downloadWithAuth(`/renovation/files/${fileId}`, "renovation-attachment");
        return;
      }
      if (event.target.classList.contains("file-delete")) {
        try {
          await api(`/renovation/files/${fileId}`, {method: "DELETE"});
          $("success").textContent = "File archived.";
          await loadCockpit();
        } catch (err) { $("error").textContent = err.message; }
      }
    });
    $("integrations").addEventListener("click", async (event) => {
      if (!event.target.classList.contains("validate-provider")) return;
      const row = event.target.closest("tr");
      const providerType = row?.dataset?.providerType;
      const validateType = row?.dataset?.validateType;
      const provider = row?.dataset?.provider;
      if (!providerType || !validateType || !provider) return;
      const payload = {provider};
      if (providerType === "email") {
        payload.channel = "email";
        payload.sender = $("company-email").value || "office@example.com";
        payload.smtp_host = provider === "smtp" ? "smtp.example.com" : "";
      }
      if (providerType === "sms") {
        payload.channel = "sms";
        payload.sender_id = "RENOS";
        payload.account_sid = "configured-locally";
        payload.auth_token = "configured-locally";
      }
      try {
        const result = await api(`/renovation/integrations/${validateType}/validate`, {method: "POST", body: JSON.stringify(payload)});
        $("integration-result").innerHTML = [line("Provider", result.provider), line("Validation", result.valid ? "Ready" : "Needs setup"), line("Missing", (result.missing || []).join(", ") || "-")].join("");
        await loadCockpit();
      } catch (err) { $("error").textContent = err.message; }
    });
    $("proposals").addEventListener("click", (event) => {
      const proposalId = event.target?.dataset?.proposalId;
      if (!proposalId || !event.target.classList.contains("proposal-pdf")) return;
      downloadWithAuth(`/renovation/proposals/${proposalId}/pdf`, `${proposalId}.pdf`);
    });
    async function downloadWithAuth(path, filename) {
      try {
        const response = await fetch(path, {headers: accessToken ? {"Authorization": `Bearer ${accessToken}`} : {}});
        if (!response.ok) throw new Error(readableError(await response.json().catch(() => ({})), response.status));
        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (err) { $("error").textContent = err.message; }
    }
    loadCockpit();
    refreshRuns();
  </script>
</body>
</html>"""


def _mesh_passport(
    *,
    agent_id: str,
    name: str,
    version: str,
    owner: str,
    organization: str,
    capabilities: list[str],
    fingerprint: str,
) -> AgentPassport:
    identity = AgentIdentity.create(
        agent_id=agent_id,
        name=name,
        version=version,
        owner=owner,
        organization=organization,
        capabilities=capabilities,
        signing_fingerprint=fingerprint,
    )
    return AgentPassport(
        identity=identity,
        certificate=AgentCertificate.issue(agent_id=agent_id, signing_fingerprint=fingerprint),
    )


def _build_default_directory() -> AgentDirectory:
    directory = AgentDirectory()
    for passport in [
        _mesh_passport(
            agent_id="planner-agent",
            name="PlannerAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["planning"],
            fingerprint="planner-fp",
        ),
        _mesh_passport(
            agent_id="research-agent",
            name="ResearchAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["research", "retrieval"],
            fingerprint="research-fp",
        ),
        _mesh_passport(
            agent_id="web-agent",
            name="WebAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["research", "retrieval"],
            fingerprint="web-fp",
        ),
        _mesh_passport(
            agent_id="document-agent",
            name="DocumentAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["research", "analysis", "retrieval"],
            fingerprint="document-fp",
        ),
        _mesh_passport(
            agent_id="code-agent",
            name="CodeAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["coding", "execution"],
            fingerprint="code-fp",
        ),
        _mesh_passport(
            agent_id="compliance-agent",
            name="ComplianceAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["analysis", "review"],
            fingerprint="compliance-fp",
        ),
        _mesh_passport(
            agent_id="reviewer-agent",
            name="ReviewerAgent",
            version="1.0.0",
            owner="agentfabric",
            organization="agentfabric",
            capabilities=["review"],
            fingerprint="reviewer-fp",
        ),
    ]:
        directory.register(passport)
    return directory


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    validate_production_safety(settings)
    try:
        from agentfabric.observability.logging_config import configure_logging
        configure_logging(level=settings.log_level, json_logs=settings.json_logs)
    except Exception:
        pass
    if settings.auto_migrate:
        run_migrations(settings.database_url)
    session_factory, _ = build_session_factory(settings)
    control_plane = ProductionControlPlane(db_path=settings.production_db_path)
    auth = AuthService(settings)
    queue_backend = choose_queue_backend(settings)
    signing_verifier = choose_signing_verifier(settings)
    payment_processor = StripePaymentProcessor(settings.stripe_api_key) if settings.stripe_api_key else MockPaymentProcessor()
    durable_store = choose_state_store(settings)
    migration_result = MigrationRunner(durable_store).apply()
    tenant_service = TenantService(durable_store)
    membership_service = MembershipService(durable_store)
    isolation = TenantIsolation()
    quota_tracker = QuotaTracker()
    limit_enforcer = LimitEnforcer(quota_tracker)
    metering = MeteringService(durable_store)
    cost_tracker = CostTracker(durable_store)
    revenue_tracker = RevenueTracker(durable_store)
    margin_analyzer = MarginAnalyzer(costs=cost_tracker, revenue=revenue_tracker)
    tenant_profitability = TenantProfitability(margin_analyzer)
    package_revenue = PackageRevenue(durable_store)
    pricing_policy = PricingPolicy()
    mesh_directory = _build_default_directory()
    mesh_discovery = AgentDiscovery(mesh_directory)
    veil = MockVeilClient()
    event_store = EventStore(persistence=durable_store)
    operational_intelligence = OperationalIntelligenceService(durable_store, event_store)
    software_foundry = SoftwareFoundryService(durable_store, event_store)
    repository_execution = RepositoryExecutionEngine(
        persistence=durable_store,
        event_store=event_store,
        output_root=Path(settings.factory_output_root),
        platform_root=Path(__file__).resolve().parents[2] / "platforms" / "renovation_os",
    )
    build_workers = BuildWorkerService(
        persistence=durable_store,
        event_store=event_store,
        execution_engine=repository_execution,
        output_root=Path(settings.factory_output_root),
    )
    renovation = RenovationFoundationService(durable_store, event_store)
    renovation_mvp = RenovationMvpWorkflow(renovation, durable_store, event_store)
    renovation_operator = RenovationOperatorCockpit(renovation, durable_store, event_store)
    renovation_attachments = LocalAttachmentStore(
        settings.renovation_storage_dir,
        durable_store,
        max_bytes=settings.renovation_max_upload_bytes,
    )

    def _renovation_integration_statuses() -> dict[str, object]:
        email_config = {
            "provider": "smtp" if settings.renovation_email_provider == "smtp" else "local",
            "channel": "email",
            "smtp_host": settings.renovation_smtp_host,
            "smtp_port": settings.renovation_smtp_port,
            "sender": settings.renovation_email_sender,
            "reply_to": settings.renovation_email_reply_to,
            "smtp_username": settings.renovation_smtp_username,
            "smtp_password": settings.renovation_smtp_password,
            "live_enabled": settings.renovation_smtp_live_enabled,
        }
        sms_config = {
            "provider": settings.renovation_sms_provider,
            "channel": "sms",
            "sender_id": settings.renovation_sms_sender_id,
            "account_sid": settings.renovation_sms_account_sid,
            "auth_token": settings.renovation_sms_auth_token,
        }
        calendar_config = {
            "provider": settings.renovation_calendar_provider,
            "oauth_client_id": settings.renovation_calendar_oauth_client_id,
            "oauth_client_secret": settings.renovation_calendar_oauth_client_secret,
        }
        payment_config = {
            "provider": settings.renovation_payment_provider,
            "secret_key": settings.renovation_payment_secret_key,
            "webhook_secret": settings.renovation_payment_webhook_secret,
        }
        items = [
            {"provider_type": "email", **renovation_operator.notification_provider.validate_config(email_config)},
            {"provider_type": "sms", **renovation_operator.notification_provider.validate_config(sms_config)},
            {"provider_type": "calendar", **renovation_operator.calendar_provider.validate_config(calendar_config)},
            {"provider_type": "payment", **renovation_operator.payment_provider.validate_config(payment_config)},
        ]
        for item in items:
            item["stub_mode"] = item.get("mode") in {"stub", "oauth-ready-stub"} or str(item.get("provider", "")).startswith("local")
            item["last_error"] = "" if item.get("valid") else f"Missing {', '.join(item.get('missing', []))}"
            item.setdefault("checklist", [{"key": "local_mode", "label": "Local deterministic mode", "configured": True}])
            item.setdefault(
                "setup_instructions",
                "Local mode is ready for demos. Configure a production provider and secrets before live customer use.",
            )
            item.setdefault("mode", "stub" if item["stub_mode"] else "configured")
            item.setdefault("status", "local_stub" if item["stub_mode"] else "configured")
        return {"items": items, "total": len(items)}

    enterprise_connectors = EnterpriseConnectorService(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        production=settings.environment == "production",
    )
    governance_approvals = HumanApprovalQueue(durable_store)
    governance = GovernanceService(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        approvals=governance_approvals,
    )
    federation = FederationService(persistence=durable_store, event_store=event_store, veil_client=veil)
    runtime_config = RuntimeConfig(
        queue_backend=settings.cloud_queue_backend,
        sqlite_path=settings.cloud_queue_sqlite_path,
        redis_url=settings.redis_url,
        max_attempts=settings.queue_max_attempts,
        worker_lease_seconds=settings.worker_lease_seconds,
        heartbeat_timeout_seconds=settings.worker_heartbeat_timeout_seconds,
        production_fail_closed=settings.environment == "production",
    )
    cloud_queue = choose_cloud_queue(settings)
    context_store = ContextStore(persistence=durable_store)
    reputation = ReputationService(persistence=durable_store)
    evaluation_runner = EvaluationRunner(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        reputation=reputation,
    )
    quality_gates = QualityGateService()
    feedback_service = FeedbackService(persistence=durable_store, event_store=event_store, reputation=reputation)
    memory_store = DurableMemoryStore(durable_store)
    marketplace_registry = MarketplaceRegistryService(durable_store)
    trusted_publishers = TrustedPublisherRegistry()
    marketplace_verifier = SignatureVerifier(trusted_publishers, allow_unsigned_local=settings.environment != "production")
    marketplace_publish = PublishService(
        registry=marketplace_registry,
        verifier=marketplace_verifier,
        event_store=event_store,
    )
    marketplace_install = InstallService(
        registry=marketplace_registry,
        persistence=durable_store,
        event_store=event_store,
    )
    marketplace_reviews = RatingService(durable_store)
    publisher_reputation = PublisherReputationService(durable_store)
    message_bus = MessageBus(directory=mesh_directory, veil_client=veil, tenant_id="default")
    workflow_engine = MeshWorkflowEngine(
        context_store=context_store,
        event_store=event_store,
        reputation=reputation,
    )
    coordinator = CollaborationCoordinator(discovery=mesh_discovery, workflow_engine=workflow_engine)

    def _runtime_entitlement_check(job: RuntimeJob) -> None:
        package_id = job.payload.get("package_id")
        if package_id:
            marketplace_install.verify_runtime_entitlement(tenant_id=job.tenant_id, package_id=str(package_id))

    def _runtime_governance_check(job: RuntimeJob) -> None:
        proposal_id = job.payload.get("proposal_id")
        if not proposal_id:
            raise AuthorizationError("governance action jobs require proposal_id")
        proposal = governance.get_proposal(str(proposal_id))
        if proposal.tenant_id != job.tenant_id:
            raise AuthorizationError("cross-tenant governance job denied")
        if proposal.status not in {ProposalStatus.APPROVED.value, ProposalStatus.EXECUTED.value}:
            raise AuthorizationError("governance action is not approved")

    def _runtime_federation_check(job: RuntimeJob) -> None:
        agreement_id = job.payload.get("trust_agreement_id")
        if not agreement_id:
            raise AuthorizationError("federation runtime jobs require trust_agreement_id")
        agreement = federation.registry.get_agreement(str(agreement_id))
        if agreement.tenant_id != job.tenant_id or not agreement.is_active():
            raise AuthorizationError("active federation trust agreement is required")

    def _runtime_spend_check(job: RuntimeJob) -> None:
        category = {
            "agent_run": "agent_run",
            "workflow_step": "workflow_run",
            "tool_execution": "tool_execution",
            "connector_sync": "connector_sync",
            "connector_search": "tool_execution",
            "connector_document_fetch": "tool_execution",
            "marketplace_package": "marketplace_execution",
            "remote_delegation": "federation_delegation",
            "evaluation_run": "evaluation_run",
            "audit_export": "audit_bundle_export",
        }.get(job.job_type, "queue_worker_runtime")
        try:
            cost_tracker.enforce(job.tenant_id, category, source_id=job.job_id)
        except AuthorizationError:
            event_store.append("economics.spend_limit.exceeded", job.job_id, {"tenant_id": job.tenant_id, "job_id": job.job_id, "category": category})
            raise

    cloud_runtime = CloudRuntime(
        queue=cloud_queue,
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        config=runtime_config,
        quota_enforcer=limit_enforcer,
        quota_policy=lambda tenant_id: _tenant_policy(tenant_id),
    )
    cloud_runtime.dispatcher.entitlement_check = _runtime_entitlement_check
    cloud_runtime.dispatcher.governance_check = _runtime_governance_check
    cloud_runtime.dispatcher.federation_check = _runtime_federation_check
    cloud_runtime.dispatcher.spend_check = _runtime_spend_check
    connector_registry = ConnectorRegistry(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        runtime=cloud_runtime,
    )
    tool_router = ToolRouter(
        connector_registry=connector_registry,
        audit_exporter=AuditBundleExporter(persistence=durable_store, event_store=event_store),
    )
    tool_registry = ToolRegistry(
        persistence=durable_store,
        event_store=event_store,
        veil_client=veil,
        router=tool_router,
        runtime=cloud_runtime,
    )
    scheduler = SchedulerService(persistence=durable_store, event_store=event_store, runtime=cloud_runtime)
    metrics_registry = MetricsRegistry()
    deployment_health = DeploymentHealth(persistence=durable_store, runtime=cloud_runtime)
    if settings.environment == "production":
        readiness = deployment_health.ready(fail_closed=True)
        if readiness["status"] != "ok":
            raise RuntimeError("production readiness checks failed")

    def _tenant_context(request: Request) -> TenantContext:
        principal = require_scopes(request, [])
        tenant = tenant_service.get(principal.tenant_id)
        organization_id = tenant.organization_id if tenant else principal.tenant_id
        return isolation.require_context(
            TenantContext(
                tenant_id=principal.tenant_id,
                organization_id=organization_id,
                principal_id=principal.principal_id,
                roles=principal.scopes,
                is_global_admin="tenant.global" in principal.scopes,
            )
        )

    def _tenant_policy(tenant_id: str) -> QuotaPolicy:
        stored = durable_store.get("quota_policies", tenant_id)
        if stored:
            return QuotaPolicy.from_dict(stored)
        tenant = tenant_service.get(tenant_id)
        plan = get_billing_plan(tenant.billing_plan if tenant else "dev")
        return plan.quota_policy

    def _assert_tenant_access(request: Request, tenant_id: str, scopes: list[str]):
        principal = require_scopes(request, scopes)
        if principal.tenant_id != tenant_id and "tenant.global" not in principal.scopes:
            raise HTTPException(status_code=403, detail="cross-tenant access denied")
        return principal

    def _workflow_owner(workflow_id: str) -> dict[str, object] | None:
        return durable_store.get("workflows", workflow_id)

    def _assert_workflow_tenant(ctx: TenantContext, workflow_id: str) -> None:
        owner = _workflow_owner(workflow_id)
        if owner is None:
            return
        isolation.assert_tenant(ctx, owner)

    def _marketplace_plan_allows(ctx: TenantContext, permission: str) -> None:
        tenant = tenant_service.get(ctx.tenant_id)
        plan = get_billing_plan(tenant.billing_plan if tenant else "dev")
        if permission not in plan.marketplace_permissions and "admin" not in plan.marketplace_permissions:
            raise HTTPException(status_code=403, detail=f"billing plan does not allow marketplace {permission}")

    def _governance_policy(ctx: TenantContext, policy_id: str = "default") -> GovernancePolicy:
        stored = durable_store.get("governance_policies", f"{ctx.tenant_id}:{policy_id}")
        if stored:
            return GovernancePolicy.from_dict(stored)
        return GovernancePolicy(
            policy_id=policy_id,
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
        )

    def _assert_governance_tenant(ctx: TenantContext, item: dict[str, object]) -> None:
        try:
            isolation.assert_tenant(ctx, item)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    def _manifest_from_payload(payload: dict, ctx: TenantContext) -> PackageManifest:
        return PackageManifest(
            package_id=payload["package_id"],
            name=payload.get("name", payload["package_id"]),
            version=payload["version"],
            publisher_tenant_id=ctx.tenant_id,
            agent_identity_id=payload["agent_identity_id"],
            runtime_requirements=payload.get("runtime_requirements", {}),
            tool_permissions=tuple(payload.get("tool_permissions", ())),
            connector_requirements=tuple(payload.get("connector_requirements", ())),
            connector_permissions=tuple(payload.get("connector_permissions", ())),
            dependencies=tuple(PackageDependency.from_dict(item) for item in payload.get("dependencies", ())),
            license_type=payload.get("license_type", "free"),
            pricing_model=payload.get("pricing_model", "free"),
        )

    def _connector_manifest_from_payload(payload: dict) -> ConnectorManifest:
        return ConnectorManifest(
            connector_type=payload["connector_type"],
            display_name=payload.get("display_name", payload["connector_type"]),
            capabilities=tuple(payload.get("capabilities", ("sync", "search", "fetch"))),
            scopes=tuple(payload.get("scopes", ())),
            data_classes=tuple(payload.get("data_classes", ())),
            webhook_supported=bool(payload.get("webhook_supported", False)),
            metadata=dict(payload.get("metadata", {})),
        )

    def _connector_credentials_from_payload(payload: dict) -> ConnectorCredentials:
        credentials = dict(payload.get("credentials", {}))
        return ConnectorCredentials(
            credential_ref=str(credentials.get("credential_ref", "")),
            provider=str(credentials.get("provider", payload.get("connector_type", ""))),
        )

    def _connector_policy_from_payload(payload: dict) -> ConnectorPolicy:
        policy = dict(payload.get("policy", {}))
        return ConnectorPolicy(
            allowed_operations=tuple(policy.get("allowed_operations", ("sync", "search", "fetch", "webhook", "health"))),
            allowed_data_classes=tuple(policy.get("allowed_data_classes", payload.get("data_classes", ()))),
            max_results=int(policy.get("max_results", 100)),
            require_veil=bool(policy.get("require_veil", True)),
        )

    def _tool_manifest_from_payload(payload: dict) -> ToolManifest:
        return ToolManifest(
            name=payload.get("name", payload["tool_type"]),
            tool_type=payload["tool_type"],
            description=payload.get("description", ""),
            version=payload.get("version", "1.0.0"),
            required_connector_type=payload.get("required_connector_type"),
            metadata=dict(payload.get("metadata", {})),
        )

    def _tool_permission_from_payload(payload: dict) -> ToolPermission:
        permission = dict(payload.get("permission", {}))
        return ToolPermission(
            required_rbac_scope=str(permission.get("required_rbac_scope", "tools.execute")),
            required_tenant_context=bool(permission.get("required_tenant_context", True)),
            required_connector_policy=bool(permission.get("required_connector_policy", True)),
            required_veil_policy_check=bool(permission.get("required_veil_policy_check", True)),
            governance_approval_required=bool(permission.get("governance_approval_required", False)),
            result_persistence_allowed=bool(permission.get("result_persistence_allowed", True)),
            allowed_output_classifications=tuple(permission.get("allowed_output_classifications", ("public", "internal"))),
        )

    def _latest_quality(ctx: TenantContext, target_type: str, target_id: str) -> dict[str, object]:
        results = [
            item for item in durable_store.list_tenant("evaluation_results", ctx.tenant_id)
            if item.get("target_type") == target_type and item.get("target_id") == target_id
        ]
        if not results:
            return {"target_type": target_type, "target_id": target_id, "status": "unknown", "overall_score": None}
        latest = sorted(results, key=lambda item: str(item.get("created_at", "")))[-1]
        return {
            "target_type": target_type,
            "target_id": target_id,
            "status": "measured",
            "run_id": latest["run_id"],
            "overall_score": latest["overall_score"],
            "metrics": latest["metrics"],
        }

    def _enforce_quality_gate(ctx: TenantContext, gate_type: str, target_type: str, target_id: str, *, required: bool = False) -> None:
        quality = _latest_quality(ctx, target_type, target_id)
        if quality["overall_score"] is None:
            if required:
                raise AuthorizationError(f"quality gate failed: {gate_type}")
            return
        scorecard = evaluation_runner.scorecard(ctx, str(quality["run_id"]))
        quality_gates.enforce(gate_type, scorecard)

    def _enforce_connector_publish_gate(
        ctx: TenantContext,
        manifest: PackageManifest,
        metadata: PackageMetadata,
        payload: dict,
    ) -> None:
        declared = set(manifest.connector_permissions)
        connector_like = {
            permission for permission in manifest.tool_permissions
            if permission.split(".", 1)[0] in {
                "gmail", "calendar", "github", "jira", "slack", "servicenow", "s3",
                "custom_http", "teams", "salesforce", "sharepoint",
            }
        }
        if not connector_like.issubset(declared):
            raise AuthorizationError("marketplace connector permissions are undeclared")
        minimum_trust = float(payload.get("minimum_connector_trust_score", 0.8))
        covered: set[str] = set()
        for requirement in manifest.connector_requirements:
            try:
                connector = enterprise_connectors.registry.get(ctx, requirement)
            except NotFoundError as exc:
                raise AuthorizationError("required connector is not registered") from exc
            requested = {
                permission for permission in declared
                if permission in set(connector.required_permissions)
            }
            covered.update(requested)
            if connector.trust_score < minimum_trust:
                raise AuthorizationError("required connector trust score is too low")
            if connector.risk_level in {"high", "critical"} and not metadata.high_risk_approved:
                raise AuthorizationError("risky connector requires marketplace review")
        if declared - covered:
            raise AuthorizationError("connector permissions exceed declared connector manifests")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield

    common_error_responses = {
        400: {"description": "Validation error"},
        401: {"description": "Authentication failure"},
        403: {"description": "RBAC, tenant isolation, policy, or trust denial"},
        404: {"description": "Resource not found"},
        409: {"description": "Conflict, quota, approval, integrity, or state failure"},
        503: {"description": "Dependency unavailable"},
    }

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        description="AgentFabric production API with Postgres/migrations queue auth and billing integrations.",
        lifespan=lifespan,
        responses=common_error_responses,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["*"],
        )

    auth_rate_buckets: dict[tuple[str, int], int] = defaultdict(int)

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        import uuid
        start = time.perf_counter()
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16]
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000)
        principal_id = getattr(getattr(request.state, "principal", None), "principal_id", None)
        client_ip = request.client.host if request.client else "unknown"
        if request.headers.get("X-Forwarded-For"):
            client_ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
        try:
            from agentfabric.observability import get_logger
            log = get_logger("http")
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=client_ip,
                request_id=request_id,
                principal_id=principal_id,
            )
        except Exception:
            pass
        response.headers["X-Request-ID"] = request_id
        return response

    @app.middleware("http")
    async def security_headers_middleware(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if settings.environment == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    @app.middleware("http")
    async def rate_limit_auth_middleware(request: Request, call_next):
        if request.url.path not in {"/auth/principals/register", "/auth/token/issue"}:
            return await call_next(request)
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        minute_bucket = int(time.time() // 60)
        key = (client_ip, minute_bucket)
        auth_rate_buckets[key] += 1
        if auth_rate_buckets[key] > settings.rate_limit_auth_per_minute:
            return JSONResponse(status_code=429, content={"detail": "too many auth attempts"})
        to_drop = [k for k in list(auth_rate_buckets) if minute_bucket - (k[1]) > 1]
        for k in to_drop:
            auth_rate_buckets.pop(k, None)
        return await call_next(request)

    @app.exception_handler(AuthorizationError)
    async def _handle_authz_error(_: Request, exc: AuthorizationError):
        return domain_exception_response(exc)

    @app.exception_handler(NotFoundError)
    async def _handle_not_found(_: Request, exc: NotFoundError):
        return domain_exception_response(exc)

    @app.exception_handler(ConflictError)
    async def _handle_conflict(_: Request, exc: ConflictError):
        return domain_exception_response(exc)

    @app.exception_handler(ValidationError)
    async def _handle_validation(_: Request, exc: ValidationError):
        return domain_exception_response(exc)

    @app.exception_handler(AgentFabricError)
    async def _handle_agentfabric(_: Request, exc: AgentFabricError):
        return domain_exception_response(exc)

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(_: Request, exc: HTTPException):
        return http_exception_response(exc)

    def get_db():
        db = session_factory()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        unauthenticated_paths = {
            "/",
            "/health",
            "/ready",
            "/favicon.ico",
            "/auth/principals/register",
            "/auth/token/issue",
            "/billing/webhooks/stripe",
            "/openapi.json",
            "/docs",
            "/redoc",
            "/renovation/app",
        }
        if settings.metrics_public:
            unauthenticated_paths = unauthenticated_paths | {"/metrics"}
        if request.url.path in unauthenticated_paths:
            return await call_next(request)
        try:
            token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
            with session_factory() as db:
                request.state.principal = auth.authenticate(db, token)
            return await call_next(request)
        except HTTPException as exc:
            return http_exception_response(exc)

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        timer = HTTP_REQUEST_LATENCY.labels(request.method, request.url.path).time()
        with timer:
            response = await call_next(request)
        HTTP_REQUEST_COUNT.labels(request.method, request.url.path, str(response.status_code)).inc()
        return response

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health():
        return HealthResponse()

    @app.get("/health/persistence", tags=["system"])
    def persistence_health(request: Request):
        require_scopes(request, ["persistence.read"])
        health_result = durable_store.health()
        health_result["schema_version"] = migration_result["current_version"]
        return health_result

    @app.get("/health/runtime", tags=["system"])
    def runtime_health(request: Request):
        require_scopes(request, ["runtime.jobs.read"])
        return cloud_runtime.health()

    @app.get("/health/workers", tags=["system"])
    def workers_health(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        workers = cloud_runtime.workers.list(None if ctx.is_global_admin else ctx.tenant_id)
        return {"status": "ok", "items": [worker.as_dict() for worker in workers], "total": len(workers)}

    @app.get("/health/queues", tags=["system"])
    def queues_health(request: Request):
        require_scopes(request, ["runtime.jobs.read"])
        return cloud_queue.health()

    @app.get("/ready", tags=["system"])
    def ready(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            raise HTTPException(status_code=503, detail="database unavailable")
        if settings.redis_url.startswith("redis://"):
            try:
                import redis as redis_client
                r = redis_client.from_url(settings.redis_url)
                r.ping()
            except Exception:
                raise HTTPException(status_code=503, detail="redis unavailable")
        return {"status": "ready"}

    @app.get("/", tags=["system"])
    def root():
        return {
            "service": settings.app_name,
            "message": "API is running. Open /docs for interactive API documentation.",
            "docs": "/docs",
            "renovation_mvp": "/renovation/app",
            "health": "/health",
            "ready": "/ready",
            "openapi": "/openapi.json",
        }

    @app.get("/renovation/app", response_class=HTMLResponse, include_in_schema=False)
    def renovation_app():
        return _renovation_app_html()

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return Response(status_code=204)

    def _principal_count(db: Session) -> int:
        return int(db.execute(select(func.count(Principal.principal_id))).scalar_one())

    def _require_bootstrap_token(request: Request) -> None:
        if not settings.bootstrap_token:
            raise HTTPException(status_code=503, detail="bootstrap token is not configured")
        provided = request.headers.get("X-AgentFabric-Bootstrap-Token")
        if provided != settings.bootstrap_token:
            raise HTTPException(status_code=401, detail="invalid bootstrap token")

    @app.post("/auth/principals/register", tags=["auth"])
    def register_principal(payload: RegisterPrincipalRequest, request: Request, db: Session = Depends(get_db)):
        if _principal_count(db) == 0:
            _require_bootstrap_token(request)
        else:
            token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
            principal = auth.authenticate(db, token)
            if "auth.admin" not in principal.scopes:
                raise HTTPException(status_code=403, detail="insufficient scope")
            if principal.tenant_id != payload.tenant_id:
                raise HTTPException(status_code=403, detail="cross-tenant registration denied")
        principal = auth.register_principal(
            db,
            principal_id=payload.principal_id,
            tenant_id=payload.tenant_id,
            principal_type=payload.principal_type,
            scopes=payload.scopes,
            role=payload.role,
        )
        return {"principal_id": principal.principal_id, "tenant_id": principal.tenant_id, "role": principal.role}

    @app.post("/auth/token/issue", response_model=TokenResponse, tags=["auth"])
    def issue_token(payload: IssueTokenRequest, request: Request, db: Session = Depends(get_db)):
        target = db.get(Principal, payload.principal_id)
        if target is None:
            raise HTTPException(status_code=404, detail="principal not found")
        auth_header = request.headers.get("Authorization")
        if auth_header:
            token = AuthService.parse_bearer_header(auth_header)
            caller = auth.authenticate(db, token)
            if "auth.token.issue" not in caller.scopes:
                raise HTTPException(status_code=403, detail="insufficient scope")
            if caller.tenant_id != target.tenant_id:
                raise HTTPException(status_code=403, detail="cross-tenant token issuance denied")
        else:
            _require_bootstrap_token(request)
        token, ttl = auth.issue_token(db, principal_id=payload.principal_id, ttl_seconds=payload.ttl_seconds)
        return TokenResponse(access_token=token, expires_in=ttl)

    @app.post("/auth/token/rotate", response_model=TokenResponse, tags=["auth"])
    def rotate_token(payload: RotateTokenRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, [])
        token = AuthService.parse_bearer_header(request.headers.get("Authorization"))
        new_token, ttl = auth.rotate_token(db, bearer_token=token, ttl_seconds=payload.ttl_seconds)
        return TokenResponse(access_token=new_token, expires_in=ttl)

    @app.post("/tenants", tags=["tenants"])
    def tenants_create(payload: dict, request: Request):
        principal = require_scopes(request, ["tenant.manage"])
        organization_id = payload.get("organization_id") or payload["tenant_id"]
        tenant = tenant_service.create_tenant(
            tenant_id=payload["tenant_id"],
            organization_id=organization_id,
            name=payload.get("name", payload["tenant_id"]),
            created_by=principal.principal_id,
            billing_plan=payload.get("billing_plan", "dev"),
        )
        membership_service.add(
            Membership(
                principal_id=principal.principal_id,
                tenant_id=tenant.tenant_id,
                organization_id=tenant.organization_id,
                role="owner",
                member_type=principal.principal_type,
                created_by=principal.principal_id,
            ),
            actor_member_type=principal.principal_type,
            actor_role="owner",
        )
        event_store.append("tenant.created", tenant.tenant_id, tenant.as_dict())
        plan_revenue = {"dev": 0.0, "team": 500.0, "enterprise": 5000.0, "internal": 0.0}.get(tenant.billing_plan, 0.0)
        revenue = revenue_tracker.record(tenant.tenant_id, "subscription", amount=plan_revenue, source_id=tenant.billing_plan)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return tenant.as_dict()

    @app.get("/tenants", tags=["tenants"])
    def tenants_list(request: Request):
        principal = require_scopes(request, ["tenant.manage"])
        items = tenant_service.list_for_principal(
            principal.tenant_id,
            global_admin="tenant.global" in principal.scopes,
        )
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/tenants/{tenant_id}", tags=["tenants"])
    def tenants_get(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["tenant.manage"])
        tenant = tenant_service.get(tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        return tenant.as_dict()

    @app.post("/tenants/{tenant_id}/teams", tags=["tenants"])
    def tenant_team_create(tenant_id: str, payload: dict, request: Request):
        principal = _assert_tenant_access(request, tenant_id, ["team.manage"])
        tenant = tenant_service.get(tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        team = Team(
            team_id=payload.get("team_id") or f"team-{uuid4().hex[:12]}",
            tenant_id=tenant_id,
            organization_id=tenant.organization_id,
            name=payload["name"],
            created_by=principal.principal_id,
        )
        durable_store.put("teams", team.team_id, team.as_dict())
        event_store.append("team.created", team.team_id, team.as_dict())
        return team.as_dict()

    @app.get("/tenants/{tenant_id}/teams", tags=["tenants"])
    def tenant_teams_list(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["team.manage"])
        items = durable_store.list_tenant("teams", tenant_id)
        return {"items": items, "total": len(items)}

    @app.post("/tenants/{tenant_id}/members", tags=["tenants"])
    def tenant_member_add(tenant_id: str, payload: dict, request: Request):
        principal = _assert_tenant_access(request, tenant_id, ["members.manage"])
        tenant = tenant_service.get(tenant_id)
        if tenant is None:
            raise HTTPException(status_code=404, detail="tenant not found")
        try:
            membership = membership_service.add(
                Membership(
                    principal_id=payload["principal_id"],
                    tenant_id=tenant_id,
                    organization_id=tenant.organization_id,
                    role=payload["role"],
                    member_type=payload.get("member_type", "user"),
                    team_id=payload.get("team_id"),
                    created_by=principal.principal_id,
                ),
                actor_member_type=principal.principal_type,
                actor_role="owner" if "tenant.manage" in principal.scopes else "admin",
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        event_store.append("member.added", membership.membership_id, membership.as_dict())
        return membership.as_dict()

    @app.get("/tenants/{tenant_id}/members", tags=["tenants"])
    def tenant_members_list(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["members.manage"])
        items = [item.as_dict() for item in membership_service.list_for_tenant(tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/tenants/{tenant_id}/usage", tags=["tenants"])
    def tenant_usage(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["usage.read"])
        persisted = metering.aggregate(tenant_id)
        reconstructed = metering.reconstruct_from_events(tenant_id, event_store)
        combined = dict(reconstructed)
        for key, value in persisted.items():
            combined[key] = combined.get(key, 0) + value
        return {"tenant_id": tenant_id, "usage": combined}

    @app.get("/tenants/{tenant_id}/quotas", tags=["tenants"])
    def tenant_quotas(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["quotas.read"])
        return {"tenant_id": tenant_id, "limits": _tenant_policy(tenant_id).as_dict(), "usage": quota_tracker.usage(tenant_id).as_dict()}

    @app.patch("/tenants/{tenant_id}/quotas", tags=["tenants"])
    def tenant_quotas_update(tenant_id: str, payload: dict, request: Request):
        _assert_tenant_access(request, tenant_id, ["quotas.manage"])
        policy = QuotaPolicy.from_dict(payload)
        durable_store.put("quota_policies", tenant_id, {"tenant_id": tenant_id, **policy.as_dict()})
        event_store.append("quota.updated", tenant_id, {"tenant_id": tenant_id, "limits": policy.as_dict()})
        return {"tenant_id": tenant_id, "limits": policy.as_dict()}

    @app.get("/tenants/{tenant_id}/billing", tags=["tenants"])
    def tenant_billing_get(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["billing.read"])
        tenant = tenant_service.get(tenant_id)
        plan_id = tenant.billing_plan if tenant else "dev"
        return {"tenant_id": tenant_id, "plan": get_billing_plan(plan_id).as_dict()}

    @app.patch("/tenants/{tenant_id}/billing", tags=["tenants"])
    def tenant_billing_update(tenant_id: str, payload: dict, request: Request):
        _assert_tenant_access(request, tenant_id, ["billing.manage"])
        target_plan = get_billing_plan(payload["billing_plan"])
        usage = quota_tracker.usage(tenant_id)
        for key, limit in target_plan.quota_policy.as_dict().items():
            if usage.get(key) > limit:
                raise HTTPException(status_code=409, detail=f"billing plan downgrade violates current usage: {key}")
        tenant = tenant_service.update_billing_plan(tenant_id, target_plan.plan_id)
        event_store.append("billing.plan_updated", tenant_id, {"tenant_id": tenant_id, "billing_plan": target_plan.plan_id})
        return {"tenant_id": tenant_id, "plan": get_billing_plan(tenant.billing_plan).as_dict()}

    @app.get("/economics/tenants/{tenant_id}", tags=["economics"])
    def economics_tenant(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        return tenant_profitability.report(tenant_id)

    @app.get("/economics/tenants/{tenant_id}/costs", tags=["economics"])
    def economics_tenant_costs(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        events = [event.as_dict() for event in cost_tracker.list_for_tenant(tenant_id)]
        return {"tenant_id": tenant_id, "total_cost": cost_tracker.total(tenant_id), "items": events}

    @app.get("/economics/tenants/{tenant_id}/revenue", tags=["economics"])
    def economics_tenant_revenue(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        events = [event.as_dict() for event in revenue_tracker.list_for_tenant(tenant_id)]
        return {"tenant_id": tenant_id, "total_revenue": revenue_tracker.total(tenant_id), "items": events}

    @app.get("/economics/tenants/{tenant_id}/margin", tags=["economics"])
    def economics_tenant_margin(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.read"])
        return margin_analyzer.tenant_margin(tenant_id).as_dict()

    @app.get("/economics/packages/{package_id}/revenue", tags=["economics"])
    def economics_package_revenue(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["economics.read"])
        return package_revenue.report(package_id, None if ctx.is_global_admin else ctx.tenant_id)

    @app.get("/economics/runtime/costs", tags=["economics"])
    def economics_runtime_costs(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["economics.read"])
        items = [event.as_dict() for event in cost_tracker.list_for_tenant(ctx.tenant_id)]
        runtime_items = [item for item in items if item["category"] in {"queue_worker_runtime", "agent_run", "workflow_run", "tool_execution", "connector_sync", "evaluation_run"}]
        return {"tenant_id": ctx.tenant_id, "items": runtime_items, "total_cost": round(sum(float(item["amount"]) for item in runtime_items), 4)}

    @app.patch("/economics/tenants/{tenant_id}/spend-limits", tags=["economics"])
    def economics_spend_limits(tenant_id: str, payload: dict, request: Request):
        _assert_tenant_access(request, tenant_id, ["economics.manage"])
        limits = cost_tracker.set_spend_limits(tenant_id, {key: float(value) for key, value in payload.items()})
        event_store.append("economics.spend_limit.updated", tenant_id, limits)
        return limits

    @app.get("/tenants/{tenant_id}/audit-export", tags=["tenants"])
    def tenant_audit_export(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["audit.export"])
        events = [event.as_dict() for event in event_store.replay() if event.payload.get("tenant_id") == tenant_id]
        memory = [item for item in durable_store.list_tenant("runtime_memory", tenant_id)]
        usage = [item for item in durable_store.list_tenant("usage_events", tenant_id)]
        decisions = [item for item in durable_store.list_tenant("governance_decision_records", tenant_id)]
        return {
            "tenant_id": tenant_id,
            "events": events,
            "memory_operations": [{"memory_id": item["memory_id"], "classification": item["classification"]} for item in memory],
            "usage_history": usage,
            "governance_decision_records": decisions,
        }

    @app.post("/registry/publish", response_model=PackageResponse, tags=["registry"])
    def publish_package(payload: PublishPackageRequest, request: Request, db: Session = Depends(get_db)):
        _tenant_context(request)
        principal = require_scopes(request, ["registry.publish"], tenant_id=payload.namespace)
        if principal.principal_id != payload.namespace:
            raise HTTPException(status_code=403, detail="principal cannot publish to this namespace")
        service = PackageService(db, signing_verifier=signing_verifier)
        package = service.publish(
            namespace=payload.namespace,
            package_id=payload.package_id,
            version=payload.version,
            category=payload.category,
            permissions=payload.permissions,
            manifest=payload.manifest,
            payload=payload.payload.encode("utf-8"),
            signature=payload.signature,
            signer_id=payload.signer_id,
        )
        metering.record(principal.tenant_id, "marketplace_publishes", metadata={"package_id": payload.package_id})
        revenue = revenue_tracker.record(principal.tenant_id, "marketplace", amount=pricing_policy.per_marketplace_package, source_id=payload.package_id, package_id=payload.package_id)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return PackageResponse(
            fqid=f"{package.namespace}/{package.package_id}:{package.version}",
            payload_digest=package.payload_digest,
        )

    @app.get("/registry/list", response_model=ListPackagesResponse, tags=["registry"])
    def list_packages(
        request: Request,
        query: str | None = None,
        category: str | None = None,
        permission: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        db: Session = Depends(get_db),
    ):
        principal = require_scopes(request, ["registry.read"])
        _tenant_context(request)
        service = PackageService(db, signing_verifier=signing_verifier)
        result = service.list_packages(
            query=query,
            category=category,
            required_permissions=set(permission or []),
            page=page,
            page_size=page_size,
            namespace_filter=principal.tenant_id if "tenant.global" not in principal.scopes else None,
        )
        return ListPackagesResponse(**result)

    @app.post("/registry/install", tags=["registry"])
    def install_package(payload: InstallPackageRequest, request: Request, db: Session = Depends(get_db)):
        _tenant_context(request)
        limit_enforcer.consume(payload.tenant_id, _tenant_policy(payload.tenant_id), "marketplace_installs")
        require_scopes(request, ["registry.install"], tenant_id=payload.tenant_id)
        service = PackageService(db, signing_verifier=signing_verifier)
        install = service.install(
            tenant_id=payload.tenant_id,
            user_id=payload.user_id,
            namespace=payload.namespace,
            package_id=payload.package_id,
            version=payload.version,
        )
        metering.record(payload.tenant_id, "marketplace_installs", metadata={"package_fqid": install.package_fqid})
        return {"id": install.id, "package_fqid": install.package_fqid}

    @app.post("/marketplace/packages", tags=["marketplace"])
    def marketplace_package_publish(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.publish"])
        _marketplace_plan_allows(ctx, "publish")
        manifest = _manifest_from_payload(payload, ctx)
        metadata = PackageMetadata.from_dict(payload.get("metadata", {}))
        try:
            operational_intelligence.enforce_marketplace_gate(
                ctx,
                manifest.agent_identity_id,
                manifest.version,
                minimum_quality=float(payload.get("minimum_quality", 0.8)),
            )
            _enforce_quality_gate(
                ctx,
                "package_publish",
                "marketplace_package",
                manifest.package_id,
                required=bool(payload.get("quality_gate_required", False)),
            )
            _enforce_connector_publish_gate(ctx, manifest, metadata, payload)
        except AuthorizationError as exc:
            event_store.append(
                "marketplace.package.rejected",
                manifest.package_id,
                {"tenant_id": ctx.tenant_id, "package_id": manifest.package_id, "reason": str(exc)},
            )
            raise HTTPException(status_code=403, detail=str(exc))
        signing_key = SigningKey(publisher_id=ctx.tenant_id, secret=payload.get("signing_secret", "local-dev-secret"))
        trusted_publishers.trust(ctx.tenant_id, signing_key.fingerprint)
        signature = payload.get("signature") or PackageSignature.sign(manifest.manifest_hash(), signing_key).signature
        try:
            package = marketplace_publish.publish(
                manifest=manifest,
                metadata=metadata,
                signature=signature,
                signing_key=signing_key,
            )
        except ValidationError as exc:
            event_store.append(
                "marketplace.package.rejected",
                manifest.package_id,
                {"tenant_id": ctx.tenant_id, "package_id": manifest.package_id, "reason": str(exc)},
            )
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_publishes", metadata={"package_id": package.package_id})
        revenue = revenue_tracker.record(ctx.tenant_id, "marketplace", amount=pricing_policy.per_marketplace_package, source_id=package.package_id, package_id=package.package_id)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return package.as_dict()

    @app.get("/marketplace/packages", tags=["marketplace"])
    def marketplace_packages_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        items = [package.as_dict() for package in marketplace_registry.list_packages(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/marketplace/packages/{package_id}", tags=["marketplace"])
    def marketplace_package_get(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        package = marketplace_registry.get(package_id)
        if package.metadata.private and package.manifest.publisher_tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant marketplace access denied")
        return package.as_dict()

    @app.post("/marketplace/packages/{package_id}/versions", tags=["marketplace"])
    def marketplace_package_version(package_id: str, payload: dict, request: Request):
        payload = {**payload, "package_id": package_id}
        return marketplace_package_publish(payload, request)

    @app.post("/marketplace/packages/{package_id}/install", tags=["marketplace"])
    def marketplace_package_install(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        _marketplace_plan_allows(ctx, "install")
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "marketplace_installs")
        try:
            install = marketplace_install.install(
                tenant_id=ctx.tenant_id,
                package_id=package_id,
                version=payload.get("version"),
                approved_permissions=bool(payload.get("approved_permissions", False)),
            )
        except (AuthorizationError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_installs", metadata={"package_id": package_id})
        revenue = revenue_tracker.record(ctx.tenant_id, "marketplace", amount=pricing_policy.per_marketplace_package, source_id=package_id, package_id=package_id)
        event_store.append("economics.revenue.recorded", revenue.event_id, revenue.as_dict())
        return install

    @app.post("/marketplace/packages/{package_id}/uninstall", tags=["marketplace"])
    def marketplace_package_uninstall(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        try:
            return marketplace_install.uninstall(tenant_id=ctx.tenant_id, package_id=package_id)
        except ValidationError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/marketplace/packages/{package_id}/upgrade", tags=["marketplace"])
    def marketplace_package_upgrade(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        try:
            result = marketplace_install.upgrade(tenant_id=ctx.tenant_id, package_id=package_id, version=payload.get("version"))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_upgrades", metadata={"package_id": package_id})
        return result

    @app.post("/marketplace/packages/{package_id}/rollback", tags=["marketplace"])
    def marketplace_package_rollback(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.install"])
        try:
            result = marketplace_install.rollback(
                tenant_id=ctx.tenant_id,
                package_id=package_id,
                version=payload["version"],
                admin_override=bool(payload.get("admin_override", False)),
            )
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "marketplace_rollbacks", metadata={"package_id": package_id})
        return result

    @app.get("/marketplace/packages/{package_id}/risk", tags=["marketplace"])
    def marketplace_package_risk(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        package = marketplace_registry.get(package_id)
        if package.metadata.private and package.manifest.publisher_tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant marketplace access denied")
        return MarketplaceScanner().scan(package, marketplace_registry.available_by_id())

    @app.get("/marketplace/packages/{package_id}/quality", tags=["marketplace"])
    def marketplace_package_quality(package_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        return _latest_quality(ctx, "marketplace_package", package_id)

    @app.get("/marketplace/installed", tags=["marketplace"])
    def marketplace_installed(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        return {"items": marketplace_install.list_installed(ctx.tenant_id)}

    @app.post("/marketplace/packages/{package_id}/reviews", tags=["marketplace"])
    def marketplace_package_review(package_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["marketplace.review"])
        marketplace_install.verify_runtime_entitlement(tenant_id=ctx.tenant_id, package_id=package_id)
        review = marketplace_reviews.submit(
            PackageReview(
                tenant_id=ctx.tenant_id,
                package_id=package_id,
                rating=int(payload["rating"]),
                review=payload.get("review", ""),
                abuse_report=bool(payload.get("abuse_report", False)),
            )
        )
        event_store.append(
            "marketplace.review.submitted",
            package_id,
            {"tenant_id": ctx.tenant_id, "package_id": package_id, "rating": review.rating},
        )
        if review.abuse_report:
            event_store.append(
                "marketplace.abuse_report.submitted",
                package_id,
                {"tenant_id": ctx.tenant_id, "package_id": package_id},
            )
        return review.as_dict()

    @app.get("/marketplace/publishers/{publisher_id}/reputation", tags=["marketplace"])
    def marketplace_publisher_reputation(publisher_id: str, request: Request):
        _tenant_context(request)
        require_scopes(request, ["marketplace.read"])
        return publisher_reputation.reputation(publisher_id)

    @app.post("/governance/orgs", tags=["governance"])
    def governance_org_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.manage"])
        org = governance.create_org(
            AgentOrganization(
                org_id=payload.get("org_id") or f"gov-org-{uuid4().hex[:12]}",
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                name=payload["name"],
                authority_boundaries=tuple(payload.get("authority_boundaries", ())),
                allowed_workflow_types=tuple(payload.get("allowed_workflow_types", ())),
                budget_limits=dict(payload.get("budget_limits", {})),
                created_by=ctx.principal_id,
            )
        )
        return org.as_dict()

    @app.get("/governance/orgs", tags=["governance"])
    def governance_orgs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        items = [org.as_dict() for org in governance.list_orgs(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/governance/orgs/{org_id}", tags=["governance"])
    def governance_org_get(org_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        org = governance.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        return org.as_dict()

    @app.post("/governance/orgs/{org_id}/teams", tags=["governance"])
    def governance_team_create(org_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.manage"])
        org = governance.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        team = governance.create_team(
            AgentTeam(
                team_id=payload.get("team_id") or f"gov-team-{uuid4().hex[:12]}",
                org_id=org_id,
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                name=payload["name"],
                roles={str(agent_id): str(role) for agent_id, role in dict(payload.get("roles", {})).items()},
                created_by=ctx.principal_id,
            )
        )
        return team.as_dict()

    @app.post("/governance/orgs/{org_id}/charter", tags=["governance"])
    def governance_charter_update(org_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.manage"])
        org = governance.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        charter = governance.update_charter(
            Charter(
                org_id=org_id,
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                purpose=payload["purpose"],
                authority_boundaries=tuple(payload.get("authority_boundaries", ())),
                allowed_workflow_types=tuple(payload.get("allowed_workflow_types", ())),
                escalation_requirements=tuple(payload.get("escalation_requirements", ())),
                budget_limits=dict(payload.get("budget_limits", {})),
                updated_by=ctx.principal_id,
            )
        )
        return charter.as_dict()

    @app.post("/governance/proposals", tags=["governance"])
    def governance_proposal_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.propose"])
        target_org_id = payload["target_org_id"]
        org = governance.get_org(target_org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        proposal = Proposal(
            proposal_id=payload.get("proposal_id") or f"proposal-{uuid4().hex[:12]}",
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            proposing_agent_id=payload["proposing_agent_id"],
            target_org_id=target_org_id,
            target_team_id=payload.get("target_team_id"),
            action_type=payload["action_type"],
            risk_level=payload.get("risk_level", "medium"),
            required_approvals=int(payload.get("required_approvals", 1)),
            veil_trust_metadata_ref=payload.get("veil_trust_metadata_ref"),
            consensus_mode=payload.get("consensus_mode", "majority"),
            created_by=ctx.principal_id,
        )
        try:
            created = governance.create_proposal(proposal, assigned_reviewer=payload.get("assigned_reviewer") or ctx.principal_id)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        metering.record(ctx.tenant_id, "governance_proposals", metadata={"proposal_id": created.proposal_id})
        return created.as_dict()

    @app.get("/governance/proposals", tags=["governance"])
    def governance_proposals_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        items = [proposal.as_dict() for proposal in governance.list_proposals(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/governance/proposals/{proposal_id}", tags=["governance"])
    def governance_proposal_get(proposal_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        proposal = governance.get_proposal(proposal_id)
        _assert_governance_tenant(ctx, proposal.as_dict())
        return proposal.as_dict()

    @app.post("/governance/proposals/{proposal_id}/vote", tags=["governance"])
    def governance_proposal_vote(proposal_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.vote"])
        proposal = governance.get_proposal(proposal_id)
        _assert_governance_tenant(ctx, proposal.as_dict())
        gov_policy = _governance_policy(ctx)
        required_roles: list[str] = list(payload.get("required_roles", ()))
        if proposal.action_type in gov_policy.security_required_actions and "security_reviewer" not in required_roles:
            required_roles.append("security_reviewer")
        if proposal.action_type in gov_policy.compliance_required_actions and "compliance_reviewer" not in required_roles:
            required_roles.append("compliance_reviewer")
        vote = Vote(
            proposal_id=proposal_id,
            tenant_id=ctx.tenant_id,
            voter_agent_id=payload["voter_agent_id"],
            voter_role=payload["voter_role"],
            vote=payload["vote"],
            weight=int(payload.get("weight", 1)),
            reason=payload.get("reason", ""),
        )
        try:
            saved, result, updated = governance.cast_vote(
                vote,
                policy=ConsensusPolicy(
                    mode=proposal.consensus_mode,
                    threshold=float(payload.get("threshold", 2 / 3 if proposal.consensus_mode == "supermajority" else 0.5)),
                    required_roles=tuple(required_roles),
                    required_approvals=proposal.required_approvals,
                ),
                governance_policy=gov_policy,
            )
        except (AuthorizationError, ConflictError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 409, detail=str(exc))
        return {"vote": saved.as_dict(), "consensus": result.as_dict(), "proposal": updated.as_dict()}

    @app.post("/governance/proposals/{proposal_id}/execute", tags=["governance"])
    def governance_proposal_execute(proposal_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.execute"])
        proposal = governance.get_proposal(proposal_id)
        _assert_governance_tenant(ctx, proposal.as_dict())
        gov_policy = _governance_policy(ctx)
        require_human = proposal.consensus_mode == "human_required" or gov_policy.requires_human(proposal.risk_level)
        try:
            record = governance.execute(
                proposal_id,
                action_payload={
                    "action_type": proposal.action_type,
                    "approved_by": ctx.principal_id,
                    "result": payload.get("result", "executed"),
                    "target_ref": payload.get("target_ref"),
                },
                require_human=require_human,
            )
        except (AuthorizationError, ConflictError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 409, detail=str(exc))
        metering.record(ctx.tenant_id, "governed_actions", metadata={"proposal_id": proposal_id})
        return record.as_dict()

    @app.get("/governance/proposals/{proposal_id}/decision-record", tags=["governance"])
    def governance_decision_record(proposal_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.read"])
        record = governance.decision_record(proposal_id)
        _assert_governance_tenant(ctx, record.as_dict())
        return record.as_dict()

    @app.get("/governance/approvals", tags=["governance"])
    def governance_approvals_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.approve"])
        items = [approval.as_dict() for approval in governance_approvals.list(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    def _resolve_governance_approval(approval_id: str, request: Request, status: str, reason: str):
        ctx = _tenant_context(request)
        require_scopes(request, ["governance.approve"])
        approval = governance_approvals.get(approval_id)
        if approval is None:
            raise HTTPException(status_code=404, detail="approval not found")
        _assert_governance_tenant(ctx, approval.as_dict())
        try:
            resolved = governance_approvals.resolve(approval_id, status=status, reason=reason)
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        event_type = {
            "approved": "governance.human_approval.granted",
            "rejected": "governance.human_approval.rejected",
            "escalated": "governance.human_approval.escalated",
        }[status]
        event_store.append(event_type, approval.proposal_id, resolved.as_dict())
        proposal = governance.get_proposal(approval.proposal_id)
        if status == "approved":
            updated = proposal.with_status(ProposalStatus.APPROVED.value)
        elif status == "rejected":
            updated = proposal.with_status(ProposalStatus.REJECTED.value)
        else:
            updated = proposal.with_status(ProposalStatus.ESCALATED.value)
        durable_store.put("governance_proposals", updated.proposal_id, updated.as_dict())
        return resolved.as_dict()

    @app.post("/governance/approvals/{approval_id}/approve", tags=["governance"])
    def governance_approval_approve(approval_id: str, payload: dict, request: Request):
        return _resolve_governance_approval(approval_id, request, "approved", payload.get("reason", "approved"))

    @app.post("/governance/approvals/{approval_id}/reject", tags=["governance"])
    def governance_approval_reject(approval_id: str, payload: dict, request: Request):
        return _resolve_governance_approval(approval_id, request, "rejected", payload.get("reason", "rejected"))

    @app.post("/governance/approvals/{approval_id}/escalate", tags=["governance"])
    def governance_approval_escalate(approval_id: str, payload: dict, request: Request):
        return _resolve_governance_approval(approval_id, request, "escalated", payload.get("reason", "escalated"))

    @app.post("/federation/orgs", tags=["federation"])
    def federation_org_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        org = federation.create_org(
            FederatedOrg(
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                remote_org_id=payload["remote_org_id"],
                name=payload.get("name", payload["remote_org_id"]),
                endpoint=payload.get("endpoint", ""),
                public_key=payload.get("public_key", ""),
                created_by=ctx.principal_id,
                org_id=payload.get("org_id") or f"fed-org-{uuid4().hex[:12]}",
            )
        )
        return org.as_dict()

    @app.get("/federation/orgs", tags=["federation"])
    def federation_orgs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        items = [org.as_dict() for org in federation.registry.list_orgs(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/federation/orgs/{org_id}", tags=["federation"])
    def federation_org_get(org_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        org = federation.registry.get_org(org_id)
        _assert_governance_tenant(ctx, org.as_dict())
        return org.as_dict()

    @app.post("/federation/agreements", tags=["federation"])
    def federation_agreement_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        expires_at = datetime.fromisoformat(payload["expires_at"]) if payload.get("expires_at") else None
        kwargs = {"expires_at": expires_at} if expires_at else {}
        try:
            agreement = federation.create_agreement(
                TrustAgreement(
                    tenant_id=ctx.tenant_id,
                    organization_id=ctx.organization_id,
                    remote_org_id=payload["remote_org_id"],
                    created_by=ctx.principal_id,
                    allowed_capabilities=tuple(payload.get("allowed_capabilities", ())),
                    denied_capabilities=tuple(payload.get("denied_capabilities", ())),
                    permitted_data_classes=tuple(payload.get("permitted_data_classes", ("public", "internal"))),
                    allowed_workflow_types=tuple(payload.get("allowed_workflow_types", ())),
                    **kwargs,
                )
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return agreement.as_dict()

    @app.get("/federation/agreements", tags=["federation"])
    def federation_agreements_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        items = [agreement.as_dict() for agreement in federation.registry.list_agreements(ctx.tenant_id)]
        return {"items": items, "total": len(items)}

    @app.get("/federation/agreements/{agreement_id}", tags=["federation"])
    def federation_agreement_get(agreement_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        agreement = federation.registry.get_agreement(agreement_id)
        _assert_governance_tenant(ctx, agreement.as_dict())
        return agreement.as_dict()

    @app.post("/federation/agreements/{agreement_id}/activate", tags=["federation"])
    def federation_agreement_activate(agreement_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(agreement_id)
        _assert_governance_tenant(ctx, agreement.as_dict())
        try:
            return federation.activate_agreement(agreement_id).as_dict()
        except ConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.post("/federation/agreements/{agreement_id}/revoke", tags=["federation"])
    def federation_agreement_revoke(agreement_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(agreement_id)
        _assert_governance_tenant(ctx, agreement.as_dict())
        return federation.revoke_agreement(agreement_id, payload.get("reason", "revoked")).as_dict()

    def _remote_agent_from_payload(payload: dict, ctx: TenantContext) -> RemoteAgent:
        return RemoteAgent(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            remote_org_id=payload["remote_org_id"],
            remote_agent_id=payload["remote_agent_id"],
            name=payload.get("name", payload["remote_agent_id"]),
            capabilities=tuple(RemoteCapability.from_dict(item) for item in payload.get("capabilities", ())),
            reputation_score=float(payload.get("reputation_score", 1.0)),
            publisher_id=payload.get("publisher_id", ""),
            blocked=bool(payload.get("blocked", False)),
        )

    @app.post("/federation/capabilities/publish", tags=["federation"])
    def federation_capabilities_publish(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        try:
            return federation.publish_capability(_remote_agent_from_payload(payload, ctx), agreement).as_dict()
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/federation/capabilities", tags=["federation"])
    def federation_capabilities(request: Request, agreement_id: str, capability: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        try:
            items = federation.discover(tenant_id=ctx.tenant_id, organization_id=ctx.organization_id, agreement_id=agreement_id, capability=capability)
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/federation/capabilities/import", tags=["federation"])
    def federation_capabilities_import(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.manage"])
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        try:
            return federation.import_capability(_remote_agent_from_payload(payload, ctx), agreement).as_dict()
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/federation/messages/send", tags=["federation"])
    def federation_message_send(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.message"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        signing_secret = payload.get("signing_secret", "local-federation-secret")
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        message = FederatedMessage.create(
            signing_secret=signing_secret,
            source_org_id=ctx.organization_id,
            source_tenant_id=ctx.tenant_id,
            destination_org_id=agreement.remote_org_id,
            destination_tenant_id=payload.get("destination_tenant_id", agreement.remote_org_id),
            source_agent_id=payload["source_agent_id"],
            destination_agent_id=payload["destination_agent_id"],
            trust_agreement_id=agreement.agreement_id,
            payload=dict(payload.get("payload", {})),
            veil_reference=payload.get("veil_reference", ""),
            ttl_seconds=int(payload.get("ttl_seconds", 300)),
            message_type=payload.get("message_type", "request"),
        )
        try:
            receipt = federation.send_message(message, signing_secret)
        except (AuthorizationError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))
        return {"message": message.as_dict(), "receipt": receipt.as_dict()}

    @app.get("/federation/messages/{message_id}", tags=["federation"])
    def federation_message_get(message_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        message = federation.get_message(message_id)
        if message.source_tenant_id != ctx.tenant_id and message.destination_tenant_id != ctx.tenant_id and not ctx.is_global_admin:
            raise HTTPException(status_code=403, detail="cross-tenant federation access denied")
        return message.as_dict()

    @app.post("/federation/messages/{message_id}/receipt", tags=["federation"])
    def federation_message_receipt(message_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.message"])
        message = federation.get_message(message_id)
        if message.source_tenant_id != ctx.tenant_id and message.destination_tenant_id != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant federation access denied")
        return federation.add_receipt(message_id, ctx.tenant_id, payload.get("status", "accepted"), payload.get("reason", "")).as_dict()

    @app.post("/federation/delegations", tags=["federation"])
    def federation_delegation_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.delegate"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        agreement = federation.registry.get_agreement(payload["trust_agreement_id"])
        _assert_governance_tenant(ctx, agreement.as_dict())
        delegation = RemoteDelegation(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            trust_agreement_id=agreement.agreement_id,
            remote_org_id=agreement.remote_org_id,
            source_agent_id=payload["source_agent_id"],
            destination_agent_id=payload["destination_agent_id"],
            task_type=payload["task_type"],
            payload=dict(payload.get("payload", {})),
            created_by=ctx.principal_id,
        )
        try:
            requested = federation.request_delegation(
                delegation,
                signing_secret=payload.get("signing_secret", "local-federation-secret"),
                governance_approved=bool(payload.get("governance_approved", False)),
            )
        except (AuthorizationError, ValidationError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))
        metering.record(ctx.tenant_id, "federation_delegations", metadata={"delegation_id": requested.delegation_id})
        return requested.as_dict()

    @app.get("/federation/delegations/{delegation_id}", tags=["federation"])
    def federation_delegation_get(delegation_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        delegation = federation.get_delegation(delegation_id)
        _assert_governance_tenant(ctx, delegation.as_dict())
        return delegation.as_dict()

    @app.post("/federation/delegations/{delegation_id}/complete", tags=["federation"])
    def federation_delegation_complete(delegation_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.delegate"])
        delegation = federation.get_delegation(delegation_id)
        _assert_governance_tenant(ctx, delegation.as_dict())
        return federation.complete_delegation(delegation_id, dict(payload.get("result", {}))).as_dict()

    @app.post("/federation/delegations/{delegation_id}/reject", tags=["federation"])
    def federation_delegation_reject(delegation_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.delegate"])
        delegation = federation.get_delegation(delegation_id)
        _assert_governance_tenant(ctx, delegation.as_dict())
        return federation.reject_delegation(delegation_id, payload.get("reason", "rejected")).as_dict()

    @app.get("/federation/reputation/{remote_org_id}", tags=["federation"])
    def federation_reputation(remote_org_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["federation.read"])
        return federation.reputation(ctx.tenant_id, remote_org_id)

    @app.post("/billing/events", tags=["billing"])
    def record_billing_event(payload: BillingEventRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["billing.write"], tenant_id=payload.tenant_id)
        service = BillingService(db, payment_processor=payment_processor)
        processed = service.record_event(
            tenant_id=payload.tenant_id,
            actor_id=payload.actor_id,
            event_type=payload.event_type,
            package_fqid=payload.package_fqid,
            idempotency_key=payload.idempotency_key,
        )
        return {"processed": processed}

    @app.get("/billing/invoice", response_model=InvoiceResponse, tags=["billing"])
    def get_invoice(tenant_id: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["billing.read"], tenant_id=tenant_id)
        service = BillingService(db, payment_processor=payment_processor)
        return InvoiceResponse(**service.build_invoice(tenant_id))

    @app.post("/billing/settle", tags=["billing"])
    def settle_invoice(tenant_id: str, currency: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["billing.write"], tenant_id=tenant_id)
        service = BillingService(db, payment_processor=payment_processor)
        result = service.settle_invoice(tenant_id, currency=currency, idempotency_key=f"settle:{tenant_id}:{currency}")
        return result

    @app.get("/billing/payments/{provider_txn_id}", tags=["billing"])
    def payment_status(provider_txn_id: str, request: Request, db: Session = Depends(get_db)):
        service = BillingService(db, payment_processor=payment_processor)
        payment = service.get_payment(provider_txn_id)
        require_scopes(request, ["billing.read"], tenant_id=payment["tenant_id"])
        return payment

    @app.post("/billing/webhooks/stripe", tags=["billing"])
    async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
        payload = await request.body()
        signature = request.headers.get("Stripe-Signature")
        event = parse_stripe_webhook_event(
            payload=payload,
            signature=signature,
            webhook_secret=settings.stripe_webhook_secret,
        )
        service = BillingService(db, payment_processor=payment_processor)
        return service.handle_stripe_webhook(event)

    @app.post("/queue/enqueue", response_model=QueueMessageResponse, tags=["queue"])
    def enqueue_job(payload: QueueEnqueueRequest, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["queue.write"])
        service = QueueService(db, backend=queue_backend)
        item = service.enqueue(payload.queue_name, payload.payload)
        return QueueMessageResponse(
            message_id=item.message_id,
            queue_name=item.queue_name,
            status="queued",
            payload=item.payload,
            attempts=item.attempts,
            created_at=item.created_at,
        )

    @app.post("/queue/dequeue", response_model=QueueMessageResponse | None, tags=["queue"])
    def dequeue_job(queue_name: str, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["queue.read"])
        service = QueueService(db, backend=queue_backend)
        item = service.dequeue(queue_name)
        if item is None:
            return None
        service.ack_success(item.message_id)
        visible_payload = {k: v for k, v in item.payload.items() if not k.startswith("__af_")}
        return QueueMessageResponse(
            message_id=item.message_id,
            queue_name=item.queue_name,
            status="done",
            payload=visible_payload,
            attempts=item.attempts,
            created_at=item.created_at,
        )

    @app.post("/mesh/send", tags=["mesh"])
    def mesh_send(payload: dict, request: Request):
        principal = require_scopes(request, ["mesh.send"])
        ctx = _tenant_context(request)
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "mesh_messages_per_minute")
        message = MeshMessage(
            source_agent=payload["source_agent"],
            destination_agent=payload["destination_agent"],
            payload={**payload.get("payload", {}), "tenant_id": ctx.tenant_id},
            message_type=payload.get("message_type", MessageType.REQUEST.value),
            correlation_id=payload.get("correlation_id") or f"corr-{uuid4().hex[:12]}",
            task_id=payload.get("task_id") or f"task-{uuid4().hex[:12]}",
        )
        sent = message_bus.send(message)
        event_store.append(
            EventType.MESSAGE.value,
            sent.correlation_id,
            {"principal_id": principal.principal_id, "tenant_id": ctx.tenant_id, "message": sent.as_dict()},
        )
        durable_store.put("mesh_messages", sent.correlation_id, {"tenant_id": ctx.tenant_id, **sent.as_dict()})
        metering.record(ctx.tenant_id, "message_sends", metadata={"correlation_id": sent.correlation_id})
        return sent.as_dict()

    @app.post("/mesh/broadcast", tags=["mesh"])
    def mesh_broadcast(payload: dict, request: Request):
        principal = require_scopes(request, ["mesh.broadcast"])
        ctx = _tenant_context(request)
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "mesh_messages_per_minute")
        messages = message_bus.broadcast(
            MeshMessage(
                source_agent=payload["source_agent"],
                destination_agent=None,
                payload={**payload.get("payload", {}), "tenant_id": ctx.tenant_id},
                message_type=MessageType.BROADCAST.value,
                correlation_id=payload.get("correlation_id") or f"corr-{uuid4().hex[:12]}",
                task_id=payload.get("task_id") or f"task-{uuid4().hex[:12]}",
            )
        )
        event_store.append(
            EventType.MESSAGE.value,
            payload.get("correlation_id", "broadcast"),
            {"principal_id": principal.principal_id, "tenant_id": ctx.tenant_id, "count": len(messages)},
        )
        metering.record(ctx.tenant_id, "message_sends", quantity=len(messages), metadata={"broadcast": True})
        return {"items": [message.as_dict() for message in messages], "count": len(messages)}

    @app.post("/workflow/start", tags=["workflow"])
    def workflow_start(payload: dict, request: Request):
        principal = require_scopes(request, ["workflow.start"])
        ctx = _tenant_context(request)
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "workflow_runs_per_day")
        existing = _workflow_owner(payload["workflow_id"])
        if existing is not None:
            isolation.assert_tenant(ctx, existing)

        def api_node_runner(node: TaskNode, node_payload: dict[str, object]) -> dict[str, object]:
            return {
                "agent_id": node.agent_id,
                "node_id": node.node_id,
                "capability": node.capability,
                "input": node_payload["initial_payload"],
                "dependency_results": node_payload["dependency_results"],
            }

        initial_payload = {
            **payload.get("initial_payload", {}),
            "tenant_id": ctx.tenant_id,
            "organization_id": ctx.organization_id,
            "created_by": principal.principal_id,
        }
        durable_store.put(
            "workflows",
            payload["workflow_id"],
            {
                "workflow_id": payload["workflow_id"],
                "tenant_id": ctx.tenant_id,
                "organization_id": ctx.organization_id,
                "created_by": principal.principal_id,
            },
        )
        result = coordinator.start_workflow(
            workflow_id=payload["workflow_id"],
            nodes=payload["nodes"],
            initial_payload=initial_payload,
            approved_nodes=set(payload.get("approved_nodes", [])),
            node_runner=api_node_runner,
        )
        metering.record(ctx.tenant_id, "workflow_runs", metadata={"workflow_id": payload["workflow_id"]})
        return result

    @app.get("/workflow/{workflow_id}", tags=["workflow"])
    def workflow_get(workflow_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["workflow.read"])
        _assert_workflow_tenant(ctx, workflow_id)
        workflow = workflow_engine.get(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        return workflow

    @app.get("/events", tags=["events"])
    def events_list(request: Request, aggregate_id: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["events.read"])
        events = [
            event for event in event_store.replay(aggregate_id)
            if event.payload.get("tenant_id") == ctx.tenant_id
        ]
        return {"items": [event.as_dict() for event in events], "total": len(events)}

    @app.get("/events/{event_id}", tags=["events"])
    def events_get(event_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["events.read"])
        event = event_store.get(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="event not found")
        if event.payload.get("tenant_id") != ctx.tenant_id:
            raise HTTPException(status_code=403, detail="cross-tenant access denied")
        return event.as_dict()

    @app.get("/workflow/{workflow_id}/events", tags=["workflow"])
    def workflow_events(workflow_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["events.read", "workflow.read"])
        _assert_workflow_tenant(ctx, workflow_id)
        events = [event for event in event_store.replay(workflow_id) if event.payload.get("tenant_id") == ctx.tenant_id]
        return {"items": [event.as_dict() for event in events], "total": len(events)}

    @app.post("/workflow/{workflow_id}/recover", tags=["workflow"])
    def workflow_recover(workflow_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["workflow.recover"])
        _assert_workflow_tenant(ctx, workflow_id)
        metering.record(ctx.tenant_id, "recovery_operations", metadata={"workflow_id": workflow_id})
        try:
            return ReplayRecoveryEngine(event_store=event_store, persistence=durable_store).recover_workflow(workflow_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="workflow not found")
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc))

    @app.get("/memory/{agent_id}", tags=["memory"])
    def memory_list(agent_id: str, request: Request):
        principal = require_scopes(request, ["memory.read"])
        _tenant_context(request)
        records = memory_store.list_for_agent(tenant_id=principal.tenant_id, owner_agent_id=agent_id)
        return {"items": [record.as_dict() for record in records], "total": len(records)}

    @app.post("/memory/{agent_id}", tags=["memory"])
    def memory_create(agent_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["memory.write"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "memory_records")
        try:
            record = memory_store.create(
                owner_agent_id=agent_id,
                tenant_id=ctx.tenant_id,
                source_workflow_id=payload.get("source_workflow_id"),
                classification=payload.get("classification", "internal"),
                content=payload.get("content", {}),
                veil_token_refs=tuple(payload.get("veil_token_refs", ())),
                memory_type=payload.get("memory_type", "short_term"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        event_store.append(
            "memory.recorded",
            agent_id,
            {"memory_id": record.memory_id, "tenant_id": ctx.tenant_id, "organization_id": ctx.organization_id},
        )
        metering.record(ctx.tenant_id, "memory_writes", metadata={"memory_id": record.memory_id})
        return record.as_dict()

    @app.delete("/memory/{agent_id}/{memory_id}", tags=["memory"])
    def memory_delete(agent_id: str, memory_id: str, request: Request):
        ctx = _tenant_context(request)
        principal = require_scopes(request, ["memory.delete"])
        try:
            deleted = memory_store.delete(
                tenant_id=principal.tenant_id,
                owner_agent_id=agent_id,
                memory_id=memory_id,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        if not deleted:
            raise HTTPException(status_code=404, detail="memory not found")
        event_store.append(
            "memory.deleted",
            agent_id,
            {"memory_id": memory_id, "tenant_id": ctx.tenant_id, "organization_id": ctx.organization_id},
        )
        return {"deleted": True, "memory_id": memory_id}

    @app.get("/agents", tags=["agents"])
    def agents_list(request: Request, capability: str | None = None, version: str | None = None, healthy_only: bool = True):
        _tenant_context(request)
        require_scopes(request, ["agents.read"])
        if capability:
            items = mesh_discovery.discover(capability=capability, version=version, healthy_only=healthy_only)
        else:
            items = [entry.as_dict() for entry in mesh_directory.list_agents()]
        return {"items": items, "total": len(items)}

    @app.get("/agents/{agent_id}", tags=["agents"])
    def agents_get(agent_id: str, request: Request):
        _tenant_context(request)
        require_scopes(request, ["agents.read"])
        entry = mesh_directory.get(agent_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return entry.as_dict()

    @app.get("/agents/{agent_id}/reputation", tags=["agents"])
    def agents_reputation(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["reputation.read"])
        if mesh_directory.get(agent_id) is None:
            raise HTTPException(status_code=404, detail="agent not found")
        return reputation.get(agent_id, tenant_id=ctx.tenant_id).as_dict()

    @app.get("/agents/{agent_id}/quality", tags=["agents"])
    def agents_quality(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        return _latest_quality(ctx, "agent_output", agent_id)

    @app.post("/factory/ideas", tags=["software-factory"])
    def factory_idea_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:write"])
        try:
            idea = software_foundry.create_idea(ctx, payload)
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "factory_ideas", metadata={"idea_id": idea.idea_id})
        return idea.as_dict()

    @app.post("/factory/repositories", tags=["software-factory"])
    def factory_repository_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:execute"])
        try:
            repository, package = software_foundry.generate_repository(ctx, payload)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(
            ctx.tenant_id,
            "factory_repositories",
            metadata={"repository_id": repository.repository_id},
        )
        return {"repository": repository.as_dict(), "package": package.as_dict()}

    @app.post("/factory/platforms", tags=["software-factory"])
    def factory_platform_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:admin"])
        try:
            if set(payload) <= {"name"}:
                platform = software_foundry.platforms.get(str(payload["name"]))
            else:
                platform = DomainPlatformDefinition.from_dict(payload)
            return software_foundry.register_platform(ctx, platform).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/factory/platforms", tags=["software-factory"])
    def factory_platforms(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        items = software_foundry.list_platforms(ctx)
        return {"items": items, "total": len(items)}

    @app.get("/factory/repositories", tags=["software-factory"])
    def factory_repositories(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        items = [item.as_dict() for item in software_foundry.lifecycle.list(ctx)]
        return {"items": items, "total": len(items)}

    @app.get("/factory/repositories/{repository_id}", tags=["software-factory"])
    def factory_repository_get(repository_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        try:
            repository = software_foundry.lifecycle.get(ctx, repository_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        package = durable_store.get("factory_repository_packages", repository_id)
        return {"repository": repository.as_dict(), "package": package}

    @app.get("/factory/lineage", tags=["software-factory"])
    def factory_lineage(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        return {"items": software_foundry.graph(ctx).lineage()}

    @app.get("/factory/dependencies", tags=["software-factory"])
    def factory_dependencies(request: Request, repository_id: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        graph = software_foundry.graph(ctx)
        if repository_id:
            try:
                return graph.impact(repository_id).as_dict()
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc))
        return {"dependencies": graph.dependencies()}

    @app.get("/factory/quality", tags=["software-factory"])
    def factory_quality(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:quality"])
        items = software_foundry.quality(ctx)
        return {"items": items, "total": len(items)}

    @app.post("/factory/execution/plan", tags=["repository-execution"])
    def factory_execution_plan(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:execute"])
        try:
            plan = repository_execution.plan(
                ctx,
                str(payload.get("repository_id") or payload["repository_name"]),
                platform_id=str(payload.get("platform_id", "RenovationOS")),
                blueprint_version=str(payload.get("blueprint_version", "1.0.0")),
                knowledge_pack_version=str(payload.get("knowledge_pack_version", "1.0.0")),
            )
            return plan.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/execution/dry-run", tags=["repository-execution"])
    def factory_execution_dry_run(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:execute"])
        try:
            return repository_execution.dry_run(ctx, str(payload["execution_id"])).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/execution/approve", tags=["repository-execution"])
    def factory_execution_approve(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:admin"])
        try:
            return repository_execution.approve(ctx, str(payload["execution_id"])).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/execution/run", tags=["repository-execution"])
    def factory_execution_run(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:execute"])
        try:
            result = repository_execution.execute(ctx, str(payload["execution_id"]))
            metering.record(
                ctx.tenant_id,
                "factory_repository_executions",
                metadata={"execution_id": result.execution_id},
            )
            return result.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/execution/rollback", tags=["repository-execution"])
    def factory_execution_rollback(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:admin"])
        try:
            return repository_execution.rollback(ctx, str(payload["execution_id"]))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/factory/execution/{execution_id}", tags=["repository-execution"])
    def factory_execution_get(execution_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        try:
            plan = repository_execution.get(ctx, execution_id)
            result = durable_store.get("factory_execution_results", execution_id)
            return {"plan": plan.as_dict(), "result": result}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/factory/execution/{execution_id}/events", tags=["repository-execution"])
    def factory_execution_events(execution_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        try:
            items = repository_execution.events(ctx, execution_id)
            return {"items": items, "total": len(items)}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/factory/execution/{execution_id}/artifacts", tags=["repository-execution"])
    def factory_execution_artifacts(execution_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        try:
            items = repository_execution.artifacts(ctx, execution_id)
            return {"items": items, "total": len(items)}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/factory/build/workers", tags=["build-workers"])
    def factory_build_workers(request: Request):
        _tenant_context(request)
        require_scopes(request, ["factory:read"])
        items = build_workers.registry.list()
        return {"items": items, "total": len(items)}

    @app.post("/factory/build/plan", tags=["build-workers"])
    def factory_build_plan(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:execute"])
        try:
            return build_workers.plan(ctx, str(payload["execution_id"]))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/build/dry-run", tags=["build-workers"])
    def factory_build_dry_run(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:execute"])
        try:
            return build_workers.dry_run(ctx, str(payload["build_id"]))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/build/approve", tags=["build-workers"])
    def factory_build_approve(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:admin"])
        try:
            return build_workers.approve(ctx, str(payload["build_id"]))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/build/run", tags=["build-workers"])
    def factory_build_run(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:execute"])
        try:
            result = build_workers.execute(ctx, str(payload["build_id"]))
            metering.record(
                ctx.tenant_id,
                "factory_repository_builds",
                metadata={"build_id": result["build_id"]},
            )
            return result
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/build/review", tags=["build-workers"])
    def factory_build_review(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:quality"])
        try:
            return build_workers.review(
                ctx,
                str(payload["build_id"]),
                approved=bool(payload.get("approved", True)),
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/factory/build/rollback", tags=["build-workers"])
    def factory_build_rollback(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:admin"])
        try:
            return build_workers.rollback(ctx, str(payload["build_id"]))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/factory/build/{build_id}", tags=["build-workers"])
    def factory_build_get(build_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        try:
            return build_workers.get(ctx, build_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/factory/build/{build_id}/events", tags=["build-workers"])
    def factory_build_events(build_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        try:
            items = build_workers.events(ctx, build_id)
            return {"items": items, "total": len(items)}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/factory/build/{build_id}/artifacts", tags=["build-workers"])
    def factory_build_artifacts(build_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["factory:read"])
        try:
            items = build_workers.artifacts(ctx, build_id)
            return {"items": items, "total": len(items)}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/mvp/demo", tags=["renovation-os"])
    def renovation_mvp_demo(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.mvp.run"])
        try:
            result = renovation_mvp.create_run(ctx, payload)
            metering.record(
                ctx.tenant_id,
                "renovation_mvp_workflows",
                metadata={"run_id": result["run_id"], "job_id": dict(result["entity_ids"]).get("job_id", "")},
            )
            return result
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/mvp/runs", tags=["renovation-os"])
    def renovation_mvp_run_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.mvp.run"])
        try:
            return renovation_mvp.create_run(ctx, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/mvp/runs", tags=["renovation-os"])
    def renovation_mvp_runs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.mvp.read"])
        return renovation_mvp.list_runs(ctx)

    @app.get("/renovation/mvp/runs/{run_id}", tags=["renovation-os"])
    def renovation_mvp_run_get(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.mvp.read"])
        try:
            return renovation_mvp.get_run(ctx, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/mvp/runs/{run_id}/replay", tags=["renovation-os"])
    def renovation_mvp_run_replay(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.mvp.run"])
        try:
            return renovation_mvp.replay_run(ctx, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/mvp/runs/{run_id}/resume", tags=["renovation-os"])
    def renovation_mvp_run_resume(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.mvp.run"])
        try:
            return renovation_mvp.resume_run(ctx, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/mvp/runs/{run_id}/portal", tags=["renovation-os"])
    def renovation_mvp_run_portal(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.mvp.read"])
        try:
            return renovation_mvp.portal(ctx, run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/renovation/health", tags=["renovation-os"])
    def renovation_health(request: Request):
        require_scopes(request, ["renovation.mvp.read"])
        return {
            "status": "ok",
            "state_store": durable_store.health(),
            "mvp_runs": len(durable_store.list("renovation_mvp_runs")),
        }

    @app.get("/renovation/metrics", tags=["renovation-os"])
    def renovation_metrics(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.metrics(ctx)

    @app.get("/renovation/account", tags=["renovation-os"])
    def renovation_account_context(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.account_context(ctx)

    @app.get("/renovation/accounts", tags=["renovation-os"])
    def renovation_accounts_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_accounts(ctx)

    @app.post("/renovation/accounts/roles", tags=["renovation-os"])
    def renovation_account_role_assign(payload: dict, request: Request, db: Session = Depends(get_db)):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            record = renovation_operator.assign_account_role(ctx, payload)
            auth.register_principal(
                db,
                principal_id=str(payload.get("principal_id") or payload.get("account_id")),
                tenant_id=ctx.tenant_id,
                principal_type=str(payload.get("principal_type", "user")),
                scopes=[],
                role=str(payload["role"]),
            )
            return record
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/settings/company", tags=["renovation-os"])
    def renovation_company_settings_get(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.company_profile(ctx)

    @app.patch("/renovation/settings/company", tags=["renovation-os"])
    def renovation_company_settings_update(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        return renovation_operator.update_company_profile(ctx, payload)

    @app.post("/renovation/customers", tags=["renovation-os"])
    def renovation_customer_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.create_customer(ctx, payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/customers", tags=["renovation-os"])
    def renovation_customers_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_customers(ctx)

    @app.get("/renovation/customers/{customer_id}", tags=["renovation-os"])
    def renovation_customer_get(customer_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        try:
            return renovation_operator.get_customer(ctx, customer_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/renovation/leads", tags=["renovation-os"])
    def renovation_leads_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_leads(ctx)

    @app.get("/renovation/estimates", tags=["renovation-os"])
    def renovation_estimates_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_estimates(ctx)

    @app.post("/renovation/estimates", tags=["renovation-os"])
    def renovation_estimates_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.create_estimate(ctx, payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/estimates/{estimate_id}", tags=["renovation-os"])
    def renovation_estimates_get(estimate_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        try:
            return renovation_operator._artifact(ctx, "renovation_estimates", estimate_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/estimates/{estimate_id}/approve", tags=["renovation-os"])
    def renovation_estimate_approve(estimate_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.approve_estimate(ctx, estimate_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/renovation/proposals", tags=["renovation-os"])
    def renovation_proposals_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_proposals(ctx)

    @app.post("/renovation/proposals", tags=["renovation-os"])
    def renovation_proposals_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.create_proposal(ctx, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/proposals/{proposal_id}", tags=["renovation-os"])
    def renovation_proposals_get(proposal_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        try:
            return renovation_operator._artifact(ctx, "renovation_proposals", proposal_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/proposals/{proposal_id}/accept", tags=["renovation-os"])
    def renovation_proposal_accept(proposal_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.accept_proposal(ctx, proposal_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/renovation/proposals/{proposal_id}/pdf", tags=["renovation-os"])
    def renovation_proposal_pdf(proposal_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        try:
            content, filename = renovation_operator.proposal_pdf(ctx, proposal_id)
            return FastAPIResponse(
                content=content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/renovation/invoices/{invoice_id}/pdf", tags=["renovation-os"])
    def renovation_invoice_pdf(invoice_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        try:
            content, filename = renovation_operator.invoice_pdf(ctx, invoice_id)
            return FastAPIResponse(
                content=content,
                media_type="application/pdf",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/renovation/jobs", tags=["renovation-os"])
    def renovation_jobs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_jobs(ctx)

    @app.patch("/renovation/jobs/{job_id}/status", tags=["renovation-os"])
    def renovation_job_status_update(job_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.update_job_status(ctx, job_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/jobs/{job_id}/schedule", tags=["renovation-os"])
    def renovation_job_schedule_create(job_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.create_schedule(ctx, job_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/jobs/{job_id}/schedule", tags=["renovation-os"])
    def renovation_job_schedules_list(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_job_schedules(ctx, job_id)

    @app.get("/renovation/jobs/{job_id}/costs", tags=["renovation-os"])
    def renovation_job_costs_list(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_costs(ctx, job_id)

    @app.post("/renovation/jobs/{job_id}/invoices", tags=["renovation-os"])
    def renovation_job_invoice_create(job_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.create_invoice(ctx, job_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/jobs/{job_id}/invoices", tags=["renovation-os"])
    def renovation_job_invoices_list(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_invoices(ctx, job_id)

    @app.post("/renovation/invoices/{invoice_id}/payments", tags=["renovation-os"])
    def renovation_invoice_payment_create(invoice_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.record_payment(ctx, invoice_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/jobs/{job_id}/portal", tags=["renovation-os"])
    def renovation_job_portal(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        try:
            return renovation_operator.portal(ctx, job_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/files/{entity_type}/{entity_id}", tags=["renovation-os"])
    async def renovation_file_upload(
        entity_type: str,
        entity_id: str,
        request: Request,
        file: UploadFile = File(...),
    ):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            content = await file.read()
            record = renovation_attachments.save(
                ctx,
                entity_type,
                entity_id,
                file.filename or "attachment.bin",
                file.content_type or "application/octet-stream",
                content,
            )
            return renovation_operator.record_attachment(ctx, record)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/files", tags=["renovation-os"])
    def renovation_files_list(
        request: Request,
        entity_type: str | None = None,
        entity_id: str | None = None,
        include_archived: bool = False,
    ):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_attachments.list(ctx, entity_type, entity_id, include_archived)

    @app.get("/renovation/files/{attachment_id}", tags=["renovation-os"])
    def renovation_file_download(attachment_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        try:
            record, content = renovation_attachments.read(ctx, attachment_id)
            artifact = dict(record["artifact"])
            renovation_operator.attachment_downloaded(ctx, attachment_id)
            return FastAPIResponse(
                content=content,
                media_type=str(artifact.get("content_type", "application/octet-stream")),
                headers={"Content-Disposition": f'attachment; filename="{artifact.get("filename", "attachment.bin")}"'},
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.delete("/renovation/files/{attachment_id}", tags=["renovation-os"])
    def renovation_file_archive(attachment_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            record = renovation_attachments.archive(ctx, attachment_id)
            return renovation_operator.attachment_archived(ctx, record)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/notifications/{event_type}", tags=["renovation-os"])
    def renovation_notification_send(event_type: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.send_notification(ctx, event_type, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/notifications", tags=["renovation-os"])
    def renovation_notifications_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return renovation_operator.list_notifications(ctx)

    @app.post("/renovation/schedule/{schedule_id}/sync", tags=["renovation-os"])
    def renovation_schedule_sync(schedule_id: str, request: Request, payload: dict | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.sync_schedule(ctx, schedule_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/integrations/{provider_type}/validate", tags=["renovation-os"])
    def renovation_provider_validate(provider_type: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.validate_provider(ctx, provider_type, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/integrations", tags=["renovation-os"])
    def renovation_integrations_list(request: Request):
        _tenant_context(request)
        require_scopes(request, ["renovation.operator.read"])
        return _renovation_integration_statuses()

    @app.post("/renovation/invoices/{invoice_id}/payment-link", tags=["renovation-os"])
    def renovation_invoice_payment_link(invoice_id: str, request: Request, payload: dict | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.payment_link(ctx, invoice_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/renovation/invoices/{invoice_id}/payment-status", tags=["renovation-os"])
    def renovation_invoice_payment_status(invoice_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.payment_status(
                ctx,
                invoice_id,
                str(payload.get("status", "pending")),
                str(payload.get("provider_reference_id", "")) or None,
                str(payload.get("idempotency_key", "")) or None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/payments/webhook", tags=["renovation-os"])
    def renovation_payment_webhook(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.operator.write"])
        try:
            return renovation_operator.payment_webhook(ctx, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/estimate", tags=["renovation-os"])
    def renovation_estimate_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.estimate.write"])
        try:
            estimate = renovation.create_estimate(ctx, payload)
            metering.record(
                ctx.tenant_id,
                "renovation_estimates",
                metadata={"estimate_id": estimate.estimate_id},
            )
            return estimate.as_dict()
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/estimate/{estimate_id}", tags=["renovation-os"])
    def renovation_estimate_get(estimate_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.estimate.read"])
        try:
            return renovation.get_estimate(ctx, estimate_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/proposal", tags=["renovation-os"])
    def renovation_proposal_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.proposal.write"])
        try:
            proposal = renovation.create_proposal(ctx, payload)
            metering.record(
                ctx.tenant_id,
                "renovation_proposals",
                metadata={"proposal_id": proposal.proposal_id},
            )
            return proposal.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/proposal/{proposal_id}", tags=["renovation-os"])
    def renovation_proposal_get(proposal_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.proposal.read"])
        try:
            return renovation.get_proposal(ctx, proposal_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/proposal/export", tags=["renovation-os"])
    def renovation_proposal_export(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.proposal.write"])
        try:
            return renovation.export_proposal(
                ctx,
                str(payload["proposal_id"]),
                str(payload.get("format", "json")),
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/jobs", tags=["renovation-os"])
    def renovation_job_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.jobs.write"])
        try:
            job = renovation.create_job(ctx, payload)
            renovation_operator._event(
                ctx,
                "renovation.operator.job.created",
                job.job_id,
                {"job_id": job.job_id},
            )
            renovation_operator._record_for("renovation_jobs", job.job_id)
            metering.record(
                ctx.tenant_id,
                "renovation_jobs",
                metadata={"job_id": job.job_id},
            )
            return job.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/jobs/{job_id}", tags=["renovation-os"])
    def renovation_job_get(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.jobs.read"])
        try:
            job = renovation.get_job(ctx, job_id)
            return {**job.as_dict(), "history": renovation.project_history(ctx, job_id)}
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/jobs/{job_id}/daily-log", tags=["renovation-os"])
    def renovation_daily_log_create(job_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.documentation.write"])
        try:
            log = renovation.add_daily_log(ctx, job_id, payload)
            return {
                "daily_log": log.as_dict(),
                "daily_summary": renovation.daily_summary(ctx, job_id, log.work_date),
            }
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/jobs/{job_id}/field-note", tags=["renovation-os"])
    def renovation_field_note_create(job_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.documentation.write"])
        try:
            return renovation.add_field_note(ctx, job_id, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/change-orders", tags=["renovation-os"])
    def renovation_change_order_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.change_orders.write"])
        try:
            order = renovation.create_change_order(ctx, payload)
            metering.record(
                ctx.tenant_id,
                "renovation_change_orders",
                metadata={"change_order_id": order.change_order_id},
            )
            return order.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/change-orders/{change_order_id}", tags=["renovation-os"])
    def renovation_change_order_get(change_order_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.change_orders.read"])
        try:
            return renovation.get_change_order(ctx, change_order_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post(
        "/renovation/change-orders/{change_order_id}/approve",
        tags=["renovation-os"],
    )
    def renovation_change_order_approve(change_order_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.change_orders.approve"])
        try:
            return renovation.decide_change_order(
                ctx,
                change_order_id,
                "approved",
                payload,
            ).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post(
        "/renovation/change-orders/{change_order_id}/reject",
        tags=["renovation-os"],
    )
    def renovation_change_order_reject(change_order_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.change_orders.approve"])
        try:
            return renovation.decide_change_order(
                ctx,
                change_order_id,
                "rejected",
                payload,
            ).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post(
        "/renovation/change-orders/{change_order_id}/export",
        tags=["renovation-os"],
    )
    def renovation_change_order_export(change_order_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.change_orders.write"])
        try:
            return renovation.export_change_order(
                ctx,
                change_order_id,
                str(payload.get("format", "json")),
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/schedules", tags=["renovation-os"])
    def renovation_schedule_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.scheduling.write"])
        try:
            schedule = renovation.create_schedule(ctx, payload)
            metering.record(
                ctx.tenant_id,
                "renovation_schedules",
                metadata={"schedule_id": schedule.schedule_id},
            )
            return schedule.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/schedules/{schedule_id}", tags=["renovation-os"])
    def renovation_schedule_get(schedule_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.scheduling.read"])
        try:
            return renovation.get_schedule(ctx, schedule_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post(
        "/renovation/schedules/{schedule_id}/recalculate",
        tags=["renovation-os"],
    )
    def renovation_schedule_recalculate(schedule_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.scheduling.write"])
        try:
            return renovation.recalculate_schedule(ctx, schedule_id, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/crews", tags=["renovation-os"])
    def renovation_crew_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crews.write"])
        try:
            return renovation.create_crew(ctx, payload).as_dict()
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/crews/{crew_id}", tags=["renovation-os"])
    def renovation_crew_get(crew_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crews.read"])
        try:
            return renovation.get_crew(ctx, crew_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post(
        "/renovation/crews/{crew_id}/availability",
        tags=["renovation-os"],
    )
    def renovation_crew_availability(crew_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crews.write"])
        try:
            return renovation.update_crew_availability(ctx, crew_id, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/crew-assignments", tags=["renovation-os"])
    def renovation_crew_assignment(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crews.write"])
        try:
            return renovation.create_crew_assignment(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/material-deliveries", tags=["renovation-os"])
    def renovation_material_delivery(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.deliveries.write"])
        try:
            return renovation.create_material_delivery(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get(
        "/renovation/jobs/{job_id}/schedule-summary",
        tags=["renovation-os"],
    )
    def renovation_schedule_summary(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.scheduling.read"])
        try:
            return renovation.schedule_summary(ctx, job_id)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/jobs/{job_id}/costs", tags=["renovation-os"])
    def renovation_job_cost_create(job_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.finance.write"])
        try:
            cost = renovation.record_job_cost(ctx, job_id, payload)
            renovation_operator._event(
                ctx,
                "renovation.operator.cost_item.created",
                cost.cost_record_id,
                {
                    "job_id": job_id,
                    "cost_record_id": cost.cost_record_id,
                    "amount": cost.amount,
                },
            )
            renovation_operator._record_for("renovation_job_costs", cost.cost_record_id)
            metering.record(
                ctx.tenant_id,
                "renovation_job_costs",
                metadata={"job_id": job_id, "cost_record_id": cost.cost_record_id},
            )
            return cost.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get(
        "/renovation/jobs/{job_id}/profitability",
        tags=["renovation-os"],
    )
    def renovation_job_profitability(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.profitability.read"])
        try:
            return renovation.job_profitability(ctx, job_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/invoices", tags=["renovation-os"])
    def renovation_invoice_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.invoicing.write"])
        try:
            invoice = renovation.create_invoice(ctx, payload)
            renovation_operator._event(
                ctx,
                "renovation.operator.invoice.created",
                invoice.invoice_id,
                {
                    "job_id": invoice.job_id,
                    "invoice_id": invoice.invoice_id,
                    "total": invoice.total,
                },
            )
            renovation_operator._record_for("renovation_invoices", invoice.invoice_id)
            return invoice.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post(
        "/renovation/invoices/{invoice_id}/payment",
        tags=["renovation-os"],
    )
    def renovation_invoice_payment(invoice_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.invoicing.write"])
        try:
            invoice = renovation.pay_invoice(ctx, invoice_id, payload)
            renovation_operator._event(
                ctx,
                "renovation.operator.payment.recorded",
                invoice_id,
                {"invoice_id": invoice_id, "paid_amount": invoice.paid_amount},
            )
            renovation_operator._record_for("renovation_invoices", invoice_id)
            return invoice.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/invoices/{invoice_id}", tags=["renovation-os"])
    def renovation_invoice_get(invoice_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.invoicing.read"])
        try:
            return renovation.get_invoice(ctx, invoice_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/payables", tags=["renovation-os"])
    def renovation_payable_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.invoicing.write"])
        try:
            return renovation.create_payable(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post(
        "/renovation/payables/{payable_id}/payment",
        tags=["renovation-os"],
    )
    def renovation_payable_payment(payable_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.invoicing.write"])
        try:
            return renovation.pay_payable(ctx, payable_id, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/cash-flow/forecast", tags=["renovation-os"])
    def renovation_cash_flow_forecast(as_of: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.cashflow.read"])
        try:
            return renovation.cash_flow_forecast(ctx, as_of).as_dict()
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/owner-summary", tags=["renovation-os"])
    def renovation_owner_summary(as_of: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.finance.read"])
        try:
            return renovation.owner_financial_summary(ctx, as_of)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/leads", tags=["renovation-os"])
    def renovation_lead_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.leads.write"])
        try:
            lead = renovation.create_lead(ctx, payload)
            renovation_operator._event(
                ctx,
                "renovation.operator.lead.created",
                lead.lead_id,
                {"lead_id": lead.lead_id},
            )
            renovation_operator._record_for("renovation_leads", lead.lead_id)
            metering.record(
                ctx.tenant_id,
                "renovation_leads",
                metadata={"lead_id": lead.lead_id},
            )
            return lead.as_dict()
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/renovation/leads/{lead_id}", tags=["renovation-os"])
    def renovation_lead_get(lead_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.leads.read"])
        try:
            return renovation.get_lead(ctx, lead_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/renovation/leads/{lead_id}/status", tags=["renovation-os"])
    def renovation_lead_status(lead_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.leads.write"])
        try:
            return renovation.update_lead(ctx, lead_id, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/leads/{lead_id}/convert", tags=["renovation-os"])
    def renovation_lead_convert(lead_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.leads.write"])
        try:
            customer = renovation.convert_lead(ctx, lead_id, payload)
            renovation_operator._event(
                ctx,
                "renovation.operator.lead.converted",
                lead_id,
                {"lead_id": lead_id, "customer_id": customer.customer_id},
            )
            renovation_operator._put_artifact(
                ctx,
                "renovation_customers",
                customer.customer_id,
                customer.as_dict(),
                "customer.created",
            )
            renovation_operator._record_for("renovation_leads", lead_id)
            return customer.as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/opportunities", tags=["renovation-os"])
    def renovation_opportunity_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crm.write"])
        try:
            return renovation.create_opportunity(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get(
        "/renovation/opportunities/{opportunity_id}",
        tags=["renovation-os"],
    )
    def renovation_opportunity_get(opportunity_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crm.read"])
        try:
            return renovation.get_opportunity(ctx, opportunity_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post(
        "/renovation/opportunities/{opportunity_id}/stage",
        tags=["renovation-os"],
    )
    def renovation_opportunity_stage(
        opportunity_id: str,
        payload: dict,
        request: Request,
    ):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crm.write"])
        try:
            return renovation.update_opportunity_stage(
                ctx,
                opportunity_id,
                str(payload["stage"]),
            ).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/follow-ups", tags=["renovation-os"])
    def renovation_follow_up_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crm.write"])
        try:
            return renovation.create_follow_up(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/appointments", tags=["renovation-os"])
    def renovation_appointment_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crm.write"])
        try:
            return renovation.create_appointment(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/site-visits", tags=["renovation-os"])
    def renovation_site_visit_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.crm.write"])
        try:
            return renovation.create_site_visit(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/renovation/customer-messages", tags=["renovation-os"])
    def renovation_customer_message_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.communications.write"])
        try:
            return renovation.record_customer_message(ctx, payload).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get(
        "/renovation/customers/{customer_id}/portal-view",
        tags=["renovation-os"],
    )
    def renovation_customer_portal_view(
        customer_id: str,
        generated_date: str,
        request: Request,
    ):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.portal.read"])
        try:
            return renovation.customer_portal_view(
                ctx,
                customer_id,
                generated_date,
            ).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get(
        "/renovation/jobs/{job_id}/customer-status",
        tags=["renovation-os"],
    )
    def renovation_customer_job_status(
        job_id: str,
        generated_date: str,
        request: Request,
    ):
        ctx = _tenant_context(request)
        require_scopes(request, ["renovation.portal.read"])
        try:
            return renovation.customer_job_status(ctx, job_id, generated_date)
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/connectors/register", tags=["enterprise-connectors"])
    def enterprise_connector_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors:write"])
        try:
            manifest = EnterpriseConnectorManifest.from_dict(payload)
            return enterprise_connectors.registry.register(
                manifest,
                tenant_id=ctx.tenant_id,
                created_by=ctx.principal_id,
            ).as_dict()
        except (ValueError, ConflictError) as exc:
            raise HTTPException(status_code=409 if isinstance(exc, ConflictError) else 400, detail=str(exc))

    @app.post("/connectors/{connector_id}/enable", tags=["enterprise-connectors"])
    def enterprise_connector_enable(connector_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors:admin"])
        try:
            credential = enterprise_connectors.vault.get(ctx.tenant_id, str(payload["credential_id"]))
            policy = EnterpriseConnectorPolicy(
                policy_id=str(payload.get("policy_id", f"policy-{connector_id}")),
                tenant_id=ctx.tenant_id,
                allowed_agents=tuple(str(item) for item in payload.get("allowed_agents", ())),
                allowed_connectors=tuple(str(item) for item in payload.get("allowed_connectors", (connector_id,))),
                allowed_actions=tuple(str(item) for item in payload.get("allowed_actions", ())),
                allowed_credential_types=tuple(str(item) for item in payload.get("allowed_credential_types", (credential.credential_type,))),
                maximum_risk=str(payload.get("maximum_risk", "medium")),
                minimum_package_trust_score=float(payload.get("minimum_package_trust_score", 0.8)),
                require_veil=bool(payload.get("require_veil", True)),
            )
            return enterprise_connectors.registry.enable(
                ctx,
                connector_id,
                version=payload.get("version"),
                credential_ref=credential.reference_id,
                policy=policy,
            ).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc}")
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except (AuthorizationError, ValueError) as exc:
            raise HTTPException(status_code=403 if isinstance(exc, AuthorizationError) else 400, detail=str(exc))

    @app.post("/connectors/{connector_id}/disable", tags=["enterprise-connectors"])
    def enterprise_connector_disable(connector_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors:admin"])
        try:
            return enterprise_connectors.registry.disable(ctx, connector_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.post("/connectors/{connector_id}/execute", tags=["enterprise-connectors"])
    def enterprise_connector_execute(connector_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        principal = require_scopes(request, ["connectors:execute"])
        try:
            result = enterprise_connectors.execution.execute(
                ctx=ctx,
                connector_id=connector_id,
                agent_id=str(payload["agent_id"]),
                action=str(payload["action"]),
                payload=dict(payload.get("payload", {})),
                agent_permissions=set(principal.scopes),
                package_trust_score=float(payload.get("package_trust_score", 1.0)),
            )
            metering.record(ctx.tenant_id, "connector_executions", metadata={"execution_id": result.execution_id})
            return result.as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=f"missing field: {exc}")
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/credentials", tags=["enterprise-connectors"])
    def connector_credential_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["credentials:write"])
        try:
            return enterprise_connectors.create_credential(ctx, payload).as_dict()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/credentials/{credential_id}/rotate", tags=["enterprise-connectors"])
    def connector_credential_rotate(credential_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["credentials:rotate"])
        try:
            return enterprise_connectors.rotate_credential(ctx, credential_id, str(payload["secret"])).as_dict()
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except (NotFoundError, AuthorizationError) as exc:
            raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 403, detail=str(exc))

    @app.post("/credentials/{credential_id}/revoke", tags=["enterprise-connectors"])
    def connector_credential_revoke(credential_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["credentials:rotate"])
        try:
            return enterprise_connectors.revoke_credential(ctx, credential_id).as_dict()
        except (NotFoundError, AuthorizationError) as exc:
            raise HTTPException(status_code=404 if isinstance(exc, NotFoundError) else 403, detail=str(exc))

    @app.post("/observability/metrics", tags=["agent-observability"])
    def observability_metric_record(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["observability:write"])
        try:
            recorded = operational_intelligence.record_metric(
                AgentMetric(
                    tenant_id=ctx.tenant_id,
                    agent_id=payload["agent_id"],
                    version=payload.get("version", "unknown"),
                    metric=payload["metric"],
                    value=float(payload["value"]),
                    metadata=dict(payload.get("metadata", {})),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "agent_observability_metrics", metadata={"metric_id": recorded.metric_id})
        return recorded.as_dict()

    @app.get("/observability/metrics", tags=["agent-observability"])
    def observability_metrics_list(
        request: Request,
        agent_id: str | None = None,
        version: str | None = None,
        metric: str | None = None,
    ):
        ctx = _tenant_context(request)
        require_scopes(request, ["observability:read"])
        items = operational_intelligence.list_metrics(ctx, agent_id=agent_id, version=version, metric=metric)
        return {
            "items": [item.as_dict() for item in items],
            "total": len(items),
            "aggregation": operational_intelligence.aggregate(ctx, agent_id=agent_id, version=version),
        }

    @app.get("/agents/{agent_id}/health", tags=["agent-observability"])
    def agent_health(agent_id: str, request: Request, version: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["health:read"])
        try:
            return operational_intelligence.latest_health(ctx, agent_id, version=version).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @app.get("/agents/{agent_id}/health/history", tags=["agent-observability"])
    def agent_health_history(agent_id: str, request: Request, version: str | None = None):
        ctx = _tenant_context(request)
        require_scopes(request, ["health:read"])
        items = operational_intelligence.health_history(ctx, agent_id, version=version)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/agents/{agent_id}/drift", tags=["agent-observability"])
    def agent_drift(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["drift:read"])
        items = operational_intelligence.list_drift(ctx, agent_id)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/agents/{agent_id}/anomalies", tags=["agent-observability"])
    def agent_anomalies(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["anomaly:read"])
        items = operational_intelligence.list_anomalies(ctx, agent_id)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.get("/agents/{agent_id}/recommendations", tags=["agent-observability"])
    def agent_recommendations(agent_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["recommendations:read"])
        items = operational_intelligence.list_recommendations(ctx, agent_id)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/agents/{agent_id}/recommendations/{recommendation_id}/approve", tags=["agent-observability"])
    def agent_recommendation_approve(agent_id: str, recommendation_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["recommendations:approve"])
        try:
            return operational_intelligence.approve_recommendation(ctx, agent_id, recommendation_id).as_dict()
        except NotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/agents/{agent_id}/compare", tags=["agent-observability"])
    def agent_version_compare(agent_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["observability:read"])
        try:
            return operational_intelligence.compare_versions(
                ctx,
                agent_id,
                str(payload["baseline_version"]),
                str(payload["candidate_version"]),
            ).as_dict()
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/connectors", tags=["connectors"])
    def connector_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            connector = connector_registry.register(
                ctx=ctx,
                manifest=_connector_manifest_from_payload(payload),
                credentials=_connector_credentials_from_payload(payload),
                policy=_connector_policy_from_payload(payload),
                connector_id=payload.get("connector_id"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "connector_registered", metadata={"connector_id": connector.connector_id})
        return connector.as_dict()

    @app.get("/connectors", tags=["connectors"])
    def connectors_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.read"])
        legacy = [item.as_dict() for item in connector_registry.list(ctx)]
        enterprise = enterprise_connectors.registry.list(ctx)
        items = [*enterprise, *legacy]
        return {"items": items, "total": len(items)}

    @app.get("/connectors/{connector_id}", tags=["connectors"])
    def connector_get(connector_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.read"])
        try:
            return enterprise_connectors.registry.get(ctx, connector_id).as_dict()
        except NotFoundError:
            try:
                return connector_registry.get(ctx, connector_id).as_dict()
            except NotFoundError:
                raise HTTPException(status_code=404, detail="connector not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/connectors/{connector_id}/sync", tags=["connectors"])
    def connector_sync(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "sync", payload, request, create_job=True)

    @app.post("/connectors/{connector_id}/search", tags=["connectors"])
    def connector_search(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "search", payload, request, create_job=True)

    @app.post("/connectors/{connector_id}/fetch", tags=["connectors"])
    def connector_fetch(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "fetch", payload, request, create_job=True)

    @app.post("/connectors/{connector_id}/webhook", tags=["connectors"])
    def connector_webhook(connector_id: str, payload: dict, request: Request):
        return _connector_operation(connector_id, "webhook", payload, request, create_job=True)

    @app.get("/connectors/{connector_id}/health", tags=["connectors"])
    def connector_health(connector_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.read"])
        try:
            return connector_registry.health(ctx=ctx, connector_id=connector_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="connector not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    def _connector_operation(connector_id: str, operation: str, payload: dict, request: Request, *, create_job: bool = False):
        ctx = _tenant_context(request)
        require_scopes(request, ["connectors.manage" if operation in {"sync", "webhook"} else "connectors.read"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            result = connector_registry.execute(ctx=ctx, connector_id=connector_id, operation=operation, payload=dict(payload))
            if create_job:
                job = connector_registry.create_job(ctx=ctx, connector_id=connector_id, operation=operation, payload=dict(payload))
                return {"result": result.as_dict(), "job": job.as_dict()}
            return result.as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="connector not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/tools", tags=["tools"])
    def tool_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            tool = tool_registry.register(
                ctx=ctx,
                manifest=_tool_manifest_from_payload(payload),
                permission=_tool_permission_from_payload(payload),
                tool_id=payload.get("tool_id"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "tool_registered", metadata={"tool_id": tool.tool_id})
        return tool.as_dict()

    @app.get("/tools", tags=["tools"])
    def tools_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        tools = tool_registry.list(ctx)
        return {"items": [tool.as_dict() for tool in tools], "total": len(tools)}

    @app.get("/tools/{tool_id}", tags=["tools"])
    def tool_get(tool_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        try:
            return tool_registry.get(ctx, tool_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/tools/{tool_id}/execute", tags=["tools"])
    def tool_execute(tool_id: str, payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.execute"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            result, job = tool_registry.execute(
                ctx=ctx,
                tool_id=tool_id,
                payload=dict(payload.get("payload", payload)),
                governance_approved=bool(payload.get("governance_approved", False)),
            )
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        except ValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "tool_executions", metadata={"tool_id": tool_id, "execution_id": result.execution_id})
        return {"result": result.as_dict(), "job": job.as_dict() if job else None}

    @app.get("/tools/{tool_id}/health", tags=["tools"])
    def tool_health(tool_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        try:
            return tool_registry.health(ctx=ctx, tool_id=tool_id)
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/tools/executions/{execution_id}", tags=["tools"])
    def tool_execution_get(execution_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["tools.read"])
        try:
            return tool_registry.get_execution(ctx, execution_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="tool execution not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/evaluations/datasets", tags=["evaluations"])
    def evaluation_dataset_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            dataset = evaluation_runner.create_dataset(
                EvaluationDataset(
                    tenant_id=ctx.tenant_id,
                    organization_id=ctx.organization_id,
                    name=payload["name"],
                    cases=tuple(EvaluationCase.from_dict(item) for item in payload.get("cases", ())),
                    created_by=ctx.principal_id,
                    dataset_id=payload.get("dataset_id", None) or f"eval-dataset-{uuid4().hex[:12]}",
                )
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        metering.record(ctx.tenant_id, "evaluation_datasets", metadata={"dataset_id": dataset.dataset_id})
        return dataset.as_dict()

    @app.get("/evaluations/datasets", tags=["evaluations"])
    def evaluation_datasets_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        items = evaluation_runner.list_datasets(ctx)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/evaluations/run", tags=["evaluations"])
    def evaluation_run(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        try:
            result = evaluation_runner.run(
                ctx=ctx,
                dataset_id=payload["dataset_id"],
                target_type=payload["target_type"],
                target_id=payload["target_id"],
                outputs=[dict(item) for item in payload.get("outputs", ())],
            )
        except NotFoundError:
            raise HTTPException(status_code=404, detail="evaluation dataset not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        metering.record(ctx.tenant_id, "evaluation_runs", metadata={"run_id": result.run_id})
        if result.target_type == "agent_output":
            operational_intelligence.record_metric(
                AgentMetric(
                    tenant_id=ctx.tenant_id,
                    agent_id=result.target_id,
                    version=str(payload.get("version", "unknown")),
                    metric="evaluation_score",
                    value=result.overall_score,
                    metadata={"run_id": result.run_id},
                )
            )
        return result.as_dict()

    @app.get("/evaluations/runs/{run_id}/scorecard", tags=["evaluations"])
    def evaluation_scorecard(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        try:
            return evaluation_runner.scorecard(ctx, run_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.get("/evaluations/runs/{run_id}", tags=["evaluations"])
    def evaluation_run_get(run_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["evaluations.read"])
        try:
            return evaluation_runner.get_result(ctx, run_id).as_dict()
        except NotFoundError:
            raise HTTPException(status_code=404, detail="evaluation run not found")
        except AuthorizationError as exc:
            raise HTTPException(status_code=403, detail=str(exc))

    @app.post("/feedback", tags=["feedback"])
    def feedback_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["feedback.write"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        record = feedback_service.create(ctx, payload)
        metering.record(ctx.tenant_id, "feedback_records", metadata={"feedback_id": record.feedback_id})
        if payload.get("target_type") == "agent" and payload.get("target_id"):
            if payload.get("rating") is not None:
                operational_intelligence.record_metric(
                    AgentMetric(
                        tenant_id=ctx.tenant_id,
                        agent_id=str(payload["target_id"]),
                        version=str(payload.get("version", "unknown")),
                        metric="user_rating",
                        value=float(payload["rating"]),
                        metadata={"feedback_id": record.feedback_id},
                    )
                )
            if payload.get("correction_notes"):
                operational_intelligence.record_metric(
                    AgentMetric(
                        tenant_id=ctx.tenant_id,
                        agent_id=str(payload["target_id"]),
                        version=str(payload.get("version", "unknown")),
                        metric="correction_frequency",
                        value=1.0,
                        metadata={"feedback_id": record.feedback_id},
                    )
                )
        return record.as_dict()

    @app.get("/feedback", tags=["feedback"])
    def feedback_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["feedback.read"])
        items = feedback_service.list(ctx)
        return {"items": [item.as_dict() for item in items], "total": len(items)}

    @app.post("/runtime/jobs", tags=["runtime"])
    def runtime_job_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        job = RuntimeJob(
            tenant_id=ctx.tenant_id,
            organization_id=ctx.organization_id,
            created_by=ctx.principal_id,
            job_type=payload["job_type"],
            payload=dict(payload.get("payload", {})),
            queue_name=payload.get("queue_name", "default"),
            max_attempts=int(payload.get("max_attempts", settings.queue_max_attempts)),
        )
        try:
            created = cloud_runtime.submit(job)
            if payload.get("dispatch_now"):
                dispatched = cloud_runtime.dispatcher.dispatch_one(
                    tenant_id=ctx.tenant_id,
                    queue_name=created.queue_name,
                    worker_id=str(payload.get("worker_id", "api-dispatcher")),
                )
                return (dispatched or created).as_dict()
        except (ValueError, AuthorizationError, ConflictError) as exc:
            raise HTTPException(status_code=400 if isinstance(exc, ValueError) else 403 if isinstance(exc, AuthorizationError) else 409, detail=str(exc))
        metering.record(ctx.tenant_id, "runtime_jobs", metadata={"job_id": created.job_id})
        category = {
            "agent_run": "agent_run",
            "workflow_step": "workflow_run",
            "tool_execution": "tool_execution",
            "connector_sync": "connector_sync",
            "evaluation_run": "evaluation_run",
            "audit_export": "audit_bundle_export",
        }.get(created.job_type, "queue_worker_runtime")
        cost = cost_tracker.record(ctx.tenant_id, category, source_id=created.job_id, metadata={"job_type": created.job_type})
        event_store.append("economics.cost.recorded", cost.event_id, cost.as_dict())
        return created.as_dict()

    @app.get("/runtime/jobs", tags=["runtime"])
    def runtime_jobs_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        jobs = cloud_runtime.list_jobs(None if ctx.is_global_admin else ctx.tenant_id)
        return {"items": [job.as_dict() for job in jobs], "total": len(jobs)}

    @app.get("/runtime/jobs/{job_id}", tags=["runtime"])
    def runtime_job_get(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return job.as_dict()

    @app.post("/runtime/jobs/{job_id}/cancel", tags=["runtime"])
    def runtime_job_cancel(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return cloud_runtime.cancel(job_id).as_dict()

    @app.post("/runtime/jobs/{job_id}/retry", tags=["runtime"])
    def runtime_job_retry(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return cloud_runtime.retry(job_id).as_dict()

    @app.get("/runtime/dead-letter", tags=["runtime"])
    def runtime_dead_letter(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        jobs = cloud_queue.dead_letters(tenant_id=None if ctx.is_global_admin else ctx.tenant_id)
        return {"items": [job.as_dict() for job in jobs], "total": len(jobs)}

    @app.post("/runtime/dead-letter/{job_id}/requeue", tags=["runtime"])
    def runtime_dead_letter_requeue(job_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.manage"])
        limit_enforcer.consume(ctx.tenant_id, _tenant_policy(ctx.tenant_id), "api_calls")
        job = cloud_runtime.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        _assert_governance_tenant(ctx, job.as_dict())
        return cloud_runtime.requeue_dead_letter(job_id).as_dict()

    @app.post("/runtime/workers/register", tags=["runtime"])
    def runtime_worker_register(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.workers.manage"])
        worker = Worker(
            worker_id=payload.get("worker_id") or f"worker-{uuid4().hex[:12]}",
            tenant_id=ctx.tenant_id,
            queue_names=tuple(payload.get("queue_names", ("default",))),
            capabilities=tuple(payload.get("capabilities", ())),
        )
        return cloud_runtime.register_worker(worker).as_dict()

    @app.post("/runtime/workers/{worker_id}/heartbeat", tags=["runtime"])
    def runtime_worker_heartbeat(worker_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.workers.manage"])
        worker = cloud_runtime.workers.get(worker_id)
        if worker is None:
            raise HTTPException(status_code=404, detail="worker not found")
        _assert_governance_tenant(ctx, worker.as_dict())
        return cloud_runtime.heartbeat(worker_id).as_dict()

    @app.get("/runtime/workers", tags=["runtime"])
    def runtime_workers_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        workers = cloud_runtime.workers.list(None if ctx.is_global_admin else ctx.tenant_id)
        return {"items": [worker.as_dict() for worker in workers], "total": len(workers)}

    @app.post("/runtime/schedules", tags=["runtime"])
    def runtime_schedule_create(payload: dict, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.schedules.manage"])
        run_at = datetime.fromisoformat(payload["run_at"]) if payload.get("run_at") else None
        schedule = scheduler.create(
            ScheduledJob(
                tenant_id=ctx.tenant_id,
                organization_id=ctx.organization_id,
                created_by=ctx.principal_id,
                job_type=payload["job_type"],
                payload=dict(payload.get("payload", {})),
                schedule_type=payload.get("schedule_type", "one_time"),
                cron=payload.get("cron"),
                run_at=run_at,
            )
        )
        return schedule.as_dict()

    @app.get("/runtime/schedules", tags=["runtime"])
    def runtime_schedules_list(request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.jobs.read"])
        schedules = scheduler.list(ctx.tenant_id)
        return {"items": [schedule.as_dict() for schedule in schedules], "total": len(schedules)}

    @app.post("/runtime/schedules/{schedule_id}/disable", tags=["runtime"])
    def runtime_schedule_disable(schedule_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.schedules.manage"])
        schedule = scheduler.get(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        _assert_governance_tenant(ctx, schedule.as_dict())
        return scheduler.set_enabled(schedule_id, False).as_dict()

    @app.post("/runtime/schedules/{schedule_id}/enable", tags=["runtime"])
    def runtime_schedule_enable(schedule_id: str, request: Request):
        ctx = _tenant_context(request)
        require_scopes(request, ["runtime.schedules.manage"])
        schedule = scheduler.get(schedule_id)
        if schedule is None:
            raise HTTPException(status_code=404, detail="schedule not found")
        _assert_governance_tenant(ctx, schedule.as_dict())
        return scheduler.set_enabled(schedule_id, True).as_dict()

    @app.get("/metrics", tags=["system"])
    @app.get("/metrics/prometheus", tags=["system"])
    def metrics(request: Request):
        if not settings.metrics_public:
            require_scopes(request, ["metrics.read"])
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/metrics/tenants/{tenant_id}", tags=["system"])
    def tenant_metrics(tenant_id: str, request: Request):
        _assert_tenant_access(request, tenant_id, ["usage.read"])
        runtime_metrics = TenantUsageMetrics(cloud_runtime).snapshot(tenant_id)
        runtime_metrics["runtime"] = metrics_registry.runtime_snapshot(cloud_runtime)
        runtime_metrics["usage"] = metering.aggregate(tenant_id)
        return runtime_metrics

    @app.get("/runtime/agents", tags=["runtime"])
    def runtime_agents(request: Request):
        require_scopes(request, ["runtime.read"])
        return {"items": control_plane.runtime_agents()}

    @app.post("/runtime/install", tags=["runtime"])
    def runtime_install(payload: dict, request: Request):
        require_scopes(request, ["runtime.install"])
        agent_id = control_plane.install_runtime_agent(
            manifest=payload["manifest"],
            payload=payload["payload"].encode("utf-8"),
            signer_id=payload["signer_id"],
            signer_key=payload["signer_key"],
            signature=payload["signature"],
        )
        return {"agent_id": agent_id}

    @app.post("/runtime/load", tags=["runtime"])
    def runtime_load(payload: dict, request: Request):
        require_scopes(request, ["runtime.run"])
        control_plane.runtime_load(payload["agent_id"])
        return {"status": "loaded"}

    @app.post("/runtime/run", tags=["runtime"])
    def runtime_run(payload: dict, request: Request):
        require_scopes(request, ["runtime.run"])
        return control_plane.runtime_run(
            agent_id=payload["agent_id"],
            request=payload["request"],
            user_id=payload["user_id"],
            session_id=payload["session_id"],
        )

    @app.post("/runtime/suspend", tags=["runtime"])
    def runtime_suspend(payload: dict, request: Request):
        require_scopes(request, ["runtime.run"])
        control_plane.runtime_suspend(payload["agent_id"])
        return {"status": "suspended"}

    @app.post("/runtime/uninstall", tags=["runtime"])
    def runtime_uninstall(payload: dict, request: Request):
        require_scopes(request, ["runtime.install"])
        control_plane.runtime_uninstall(payload["agent_id"])
        return {"status": "uninstalled"}

    @app.post("/enterprise/rbac/assign", tags=["enterprise"])
    def enterprise_rbac_assign(payload: dict, request: Request):
        require_scopes(request, ["enterprise.rbac.write"])
        control_plane.assign_role(payload["principal_id"], payload["role"])
        return {"status": "ok"}

    @app.post("/enterprise/rbac/check", tags=["enterprise"])
    def enterprise_rbac_check(payload: dict, request: Request):
        require_scopes(request, ["enterprise.rbac.read"])
        control_plane.check_permission(payload["principal_id"], payload["permission"])
        return {"allowed": True}

    @app.post("/enterprise/namespace/create", tags=["enterprise"])
    def enterprise_namespace_create(payload: dict, request: Request):
        require_scopes(request, ["enterprise.namespace.write"], tenant_id=payload["owner_tenant_id"])
        control_plane.create_namespace(payload["owner_tenant_id"], payload["namespace"])
        return {"status": "created"}

    @app.post("/enterprise/namespace/grant", tags=["enterprise"])
    def enterprise_namespace_grant(payload: dict, request: Request):
        require_scopes(request, ["enterprise.namespace.write"], tenant_id=payload["owner_tenant_id"])
        control_plane.grant_namespace_access(
            payload["owner_tenant_id"],
            payload["namespace"],
            payload["target_tenant_id"],
        )
        return {"status": "granted"}

    @app.post("/enterprise/namespace/check", tags=["enterprise"])
    def enterprise_namespace_check(payload: dict, request: Request):
        require_scopes(request, ["enterprise.namespace.read"], tenant_id=payload["tenant_id"])
        control_plane.check_namespace_access(payload["tenant_id"], payload["namespace"])
        return {"allowed": True}

    @app.post("/enterprise/audit/append", tags=["enterprise"])
    def enterprise_audit_append(payload: dict, request: Request):
        require_scopes(request, ["enterprise.audit.write"])
        return control_plane.append_audit(
            actor_id=payload["actor_id"],
            action=payload["action"],
            target=payload["target"],
            metadata=payload.get("metadata", {}),
        )

    @app.post("/enterprise/audit/export", tags=["enterprise"])
    def enterprise_audit_export(payload: dict, request: Request):
        require_scopes(request, ["enterprise.audit.read"])
        path = control_plane.export_siem_audit(payload["output_file"])
        return {"path": path}

    @app.post("/reviews/submit", tags=["reviews"])
    def reviews_submit(payload: dict, request: Request):
        require_scopes(request, ["reviews.write"], tenant_id=payload["tenant_id"])
        review_id = control_plane.submit_review(
            Rating(
                tenant_id=payload["tenant_id"],
                package_fqid=payload["package_fqid"],
                user_id=payload["user_id"],
                stars=int(payload["stars"]),
                review=payload["review"],
            )
        )
        return {"review_id": review_id}

    @app.post("/reviews/moderation/pending", tags=["reviews"])
    def reviews_pending(request: Request):
        require_scopes(request, ["reviews.moderate"])
        return {"items": control_plane.pending_reviews()}

    @app.post("/reviews/moderation/resolve", tags=["reviews"])
    def reviews_resolve(payload: dict, request: Request):
        require_scopes(request, ["reviews.moderate"])
        control_plane.moderate_review(int(payload["review_id"]), approved=bool(payload["approved"]))
        return {"status": "ok"}

    @app.post("/compliance/gdpr/request", tags=["compliance"])
    def gdpr_request(payload: dict, request: Request):
        require_scopes(request, ["compliance.gdpr.write"], tenant_id=payload["tenant_id"])
        request_id = control_plane.request_gdpr_deletion(
            tenant_id=payload["tenant_id"],
            user_id=payload.get("user_id"),
            reason=payload["reason"],
        )
        return {"request_id": request_id}

    @app.post("/compliance/gdpr/process", tags=["compliance"])
    def gdpr_process(request: Request):
        require_scopes(request, ["compliance.gdpr.write"])
        return {"processed": control_plane.process_gdpr_deletions()}

    @app.post("/compliance/legal/publish", tags=["compliance"])
    def legal_publish(payload: dict, request: Request):
        require_scopes(request, ["compliance.legal.write"])
        control_plane.publish_legal_document(
            payload["doc_type"],
            payload["version"],
            payload["content"],
        )
        return {"status": "ok"}

    @app.post("/compliance/legal/accept", tags=["compliance"])
    def legal_accept(payload: dict, request: Request):
        require_scopes(request, ["compliance.legal.read"])
        return control_plane.accept_legal_document(payload["doc_type"], payload["principal_id"])

    @app.post("/ops/backup", tags=["ops"])
    def ops_backup(request: Request):
        require_scopes(request, ["ops.backup.write"])
        backup = control_plane.create_backup()
        return {"backup_file": backup}

    @app.get("/ops/backups", tags=["ops"])
    def ops_list_backups(request: Request):
        require_scopes(request, ["ops.backup.read"])
        items = control_plane.list_backups()
        return {"items": items}

    @app.post("/ops/restore", tags=["ops"])
    def ops_restore(payload: dict, request: Request):
        require_scopes(request, ["ops.backup.write"])
        backup_file = payload.get("backup_file")
        if not backup_file:
            raise HTTPException(status_code=400, detail="backup_file required")
        try:
            control_plane.restore_backup(backup_file)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"status": "restored", "backup_file": backup_file}

    @app.post("/audit/append", tags=["audit"])
    def append_audit(actor_id: str, action: str, target: str, metadata: dict | None, request: Request, db: Session = Depends(get_db)):
        require_scopes(request, ["audit.write"])
        service = AuditService(db)
        return service.append(actor_id=actor_id, action=action, target=target, metadata=metadata)

    return app
