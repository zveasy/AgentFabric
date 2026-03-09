"""Core business services backed by SQLAlchemy + queue + integrations."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from agentfabric.errors import ConflictError, NotFoundError, ValidationError
from agentfabric.server.models import (
    AgentProject,
    AuditEvent,
    BillingEvent,
    Install,
    InvoiceLine,
    Package,
    PackageReview,
    PaymentRecord,
    ProjectBranch,
    ProjectContribution,
    ProjectMaintainer,
    ProjectRelease,
)
from agentfabric.server.payments import MockPaymentProcessor, PaymentProcessor
from agentfabric.server.queue import QueueBackend, QueueItem, SqlQueueStore
from agentfabric.server.signing import CosignVerifier, DigestFallbackVerifier


def utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


class PackageService:
    def __init__(self, db: Session, signing_verifier=None) -> None:
        self.db = db
        self.signing_verifier = signing_verifier or DigestFallbackVerifier()

    def publish(
        self,
        *,
        namespace: str,
        package_id: str,
        version: str,
        category: str,
        permissions: list[str],
        manifest: dict,
        payload: bytes,
        signature: str,
        signer_id: str,
    ) -> Package:
        existing = self.db.execute(
            select(Package).where(
                Package.namespace == namespace,
                Package.package_id == package_id,
                Package.version == version,
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("package version already exists")
        verification = self.signing_verifier.verify_blob(payload=payload, signature=signature)
        package = Package(
            namespace=namespace,
            package_id=package_id,
            version=version,
            category=category,
            permissions_csv=",".join(sorted(set(permissions))),
            manifest_json=json.dumps(manifest, sort_keys=True),
            payload_digest=verification.payload_digest,
            signature=signature,
            sbom_json=json.dumps(
                {
                    "component": package_id,
                    "version": version,
                    "artifact_sha256": verification.payload_digest,
                    "signer": signer_id,
                    "verified_by": verification.verifier,
                },
                sort_keys=True,
            ),
        )
        self.db.add(package)
        self.db.flush()
        return package

    def list_packages(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        required_permissions: set[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        namespace_filter: str | None = None,
    ) -> dict:
        subq = (
            select(
                Package.namespace,
                Package.package_id,
                func.max(Package.created_at).label("max_created"),
            )
            .group_by(Package.namespace, Package.package_id)
            .subquery()
        )
        stmt = (
            select(Package)
            .join(
                subq,
                (Package.namespace == subq.c.namespace)
                & (Package.package_id == subq.c.package_id)
                & (Package.created_at == subq.c.max_created),
            )
            .order_by(Package.created_at.desc())
        )
        rows = self.db.execute(stmt).scalars().all()
        filtered = []
        for item in rows:
            if namespace_filter and item.namespace != namespace_filter:
                continue
            if query and query.lower() not in item.package_id.lower():
                continue
            if category and item.category != category:
                continue
            perms = {p for p in item.permissions_csv.split(",") if p}
            if required_permissions and not required_permissions.issubset(perms):
                continue
            filtered.append(item)
        total = len(filtered)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        items = [
            {
                "namespace": item.namespace,
                "package_id": item.package_id,
                "version": item.version,
                "category": item.category,
                "permissions": [p for p in item.permissions_csv.split(",") if p],
                "payload_digest": item.payload_digest,
                "created_at": item.created_at.isoformat(),
            }
            for item in filtered[start:end]
        ]
        return {"items": items, "page": page, "page_size": page_size, "total": total, "total_pages": total_pages}

    def install(self, *, tenant_id: str, user_id: str, namespace: str, package_id: str, version: str | None = None) -> Install:
        stmt = select(Package).where(Package.namespace == namespace, Package.package_id == package_id)
        if version:
            stmt = stmt.where(Package.version == version)
        package = self.db.execute(stmt.order_by(Package.created_at.desc())).scalars().first()
        if not package:
            raise NotFoundError("package not found")
        install = Install(tenant_id=tenant_id, user_id=user_id, package_fqid=f"{package.namespace}/{package.package_id}:{package.version}")
        self.db.add(install)
        self.db.flush()
        return install


class BillingService:
    PRICING = {"install": 0.05, "run": 0.01, "subscription_month": 29.0}

    def __init__(self, db: Session, payment_processor: PaymentProcessor | None = None) -> None:
        self.db = db
        self.payment_processor = payment_processor or MockPaymentProcessor()

    def record_event(self, *, tenant_id: str, actor_id: str, event_type: str, package_fqid: str, idempotency_key: str) -> bool:
        row = self.db.get(BillingEvent, idempotency_key)
        if row:
            return False
        self.db.add(
            BillingEvent(
                idempotency_key=idempotency_key,
                tenant_id=tenant_id,
                actor_id=actor_id,
                event_type=event_type,
                package_fqid=package_fqid,
            )
        )
        self.db.flush()
        return True

    def build_invoice(self, tenant_id: str) -> dict:
        rows = self.db.execute(
            select(BillingEvent.event_type, func.count(BillingEvent.idempotency_key))
            .where(BillingEvent.tenant_id == tenant_id)
            .group_by(BillingEvent.event_type)
        ).all()
        lines = []
        total = 0.0
        for event_type, qty in rows:
            qty_int = int(qty)
            price = self.PRICING.get(event_type, 0.0)
            subtotal = round(qty_int * price, 4)
            total += subtotal
            lines.append({"event_type": event_type, "quantity": qty_int, "unit_price": price, "subtotal": subtotal})
        return {"tenant_id": tenant_id, "lines": lines, "total": round(total, 4)}

    def settle_invoice(self, tenant_id: str, *, currency: str, idempotency_key: str) -> dict:
        invoice = self.build_invoice(tenant_id)
        payment = self.payment_processor.charge(
            tenant_id=tenant_id,
            amount=invoice["total"],
            currency=currency,
            idempotency_key=idempotency_key,
        )
        self.db.add(
            PaymentRecord(
                tenant_id=tenant_id,
                provider=payment.provider,
                provider_txn_id=payment.provider_txn_id,
                amount=payment.amount,
                currency=payment.currency,
                idempotency_key=idempotency_key,
            )
        )
        self.db.add(
            InvoiceLine(
                tenant_id=tenant_id,
                event_type="settlement",
                quantity=1,
                unit_price=payment.amount,
                subtotal=payment.amount,
            )
        )
        self.db.flush()
        return {"invoice": invoice, "payment": asdict(payment)}


class QueueService:
    def __init__(self, db: Session, backend: QueueBackend) -> None:
        self.db = db
        self.backend = backend
        self.store = SqlQueueStore(db)

    def enqueue(self, queue_name: str, payload: dict) -> QueueItem:
        item = self.backend.enqueue(queue_name, payload)
        self.store.record_enqueue(queue_name, payload, item.message_id)
        return item

    def dequeue(self, queue_name: str) -> QueueItem | None:
        item = self.backend.dequeue(queue_name)
        if item is None:
            return None
        self.store.mark_processing(item.message_id)
        self.store.mark_done(item.message_id)
        return item


class AuditService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def append(self, *, actor_id: str, action: str, target: str, metadata: dict | None = None) -> dict:
        metadata = metadata or {}
        previous = self.db.execute(select(AuditEvent).order_by(AuditEvent.id.desc())).scalars().first()
        previous_hash = previous.event_hash if previous else "GENESIS"
        material = f"{actor_id}|{action}|{target}|{metadata}|{previous_hash}"
        event_hash = sha256(material.encode("utf-8")).hexdigest()
        event = AuditEvent(
            actor_id=actor_id,
            action=action,
            target=target,
            metadata_json=json.dumps(metadata, sort_keys=True),
            previous_hash=previous_hash,
            event_hash=event_hash,
        )
        self.db.add(event)
        self.db.flush()
        return {"previous_hash": previous_hash, "event_hash": event_hash}


class ReviewService:
    BANNED_TERMS = {"malware", "phishing", "scam"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def submit(self, *, tenant_id: str, user_id: str, package_fqid: str, stars: int, review_text: str) -> PackageReview:
        if stars < 1 or stars > 5:
            raise ValidationError("stars must be between 1 and 5")
        lowered = review_text.lower()
        if any(term in lowered for term in self.BANNED_TERMS):
            raise ValidationError("review rejected by moderation policy")
        row = PackageReview(
            tenant_id=tenant_id,
            user_id=user_id,
            package_fqid=package_fqid,
            stars=stars,
            review_text=review_text,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def list_reviews(self, package_fqid: str, page: int = 1, page_size: int = 20) -> dict:
        stmt = select(PackageReview).where(PackageReview.package_fqid == package_fqid).order_by(PackageReview.created_at.desc())
        total = self.db.execute(select(func.count()).select_from(PackageReview).where(PackageReview.package_fqid == package_fqid)).scalar() or 0
        items = self.db.execute(stmt.offset((page - 1) * page_size).limit(page_size)).scalars().all()
        return {
            "items": [
                {"id": r.id, "tenant_id": r.tenant_id, "user_id": r.user_id, "stars": r.stars, "review_text": r.review_text, "created_at": r.created_at.isoformat()}
                for r in items
            ],
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    def get_summary(self, package_fqid: str) -> dict:
        row = self.db.execute(
            select(func.count(PackageReview.id).label("count"), func.avg(PackageReview.stars).label("avg_stars")).where(PackageReview.package_fqid == package_fqid)
        ).one_or_none()
        if not row or row.count == 0:
            return {"count": 0, "avg_stars": 0.0}
        return {"count": row.count, "avg_stars": round(float(row.avg_stars), 2)}


class AgentProjectService:
    DEFAULT_ZONES = (
        "prompts",
        "tool_adapters",
        "reasoning_policies",
        "memory_modules",
        "evaluators",
        "domain_packs",
        "ui_blocks",
        "safety_constraints",
        "workflow_steps",
    )
    DEFAULT_MERGE_POLICY = {
        "min_improvements": 1,
        "allowed_latency_regression_pct": 5.0,
        "allowed_cost_regression_pct": 5.0,
        "must_pass_safety": True,
        "must_pass_regression_tests": True,
    }
    RELEASE_CHANNELS = {"stable", "beta", "nightly", "enterprise-certified"}
    MERGEABLE_STATUSES = {"evaluated", "approved"}

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_project(
        self,
        *,
        namespace: str,
        project_id: str,
        display_name: str,
        description: str,
        created_by: str,
        contribution_zones: list[str] | None = None,
        merge_policy: dict[str, Any] | None = None,
    ) -> AgentProject:
        existing = self.db.execute(
            select(AgentProject).where(
                AgentProject.namespace == namespace,
                AgentProject.project_id == project_id,
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("project already exists")
        zones = tuple(sorted(set(contribution_zones or self.DEFAULT_ZONES)))
        if not zones:
            raise ValidationError("at least one contribution zone is required")
        effective_policy = dict(self.DEFAULT_MERGE_POLICY)
        if merge_policy:
            effective_policy.update(merge_policy)
        project = AgentProject(
            namespace=namespace,
            project_id=project_id,
            display_name=display_name,
            description=description,
            default_branch="main",
            contribution_zones_csv=",".join(zones),
            merge_policy_json=json.dumps(effective_policy, sort_keys=True),
            created_by=created_by,
        )
        self.db.add(project)
        self.db.flush()
        self.db.add(ProjectMaintainer(project_ref_id=project.id, principal_id=created_by))
        self.db.add(ProjectBranch(project_ref_id=project.id, branch_name="main", base_ref="root", created_by=created_by))
        self.db.flush()
        return project

    def get_project(self, *, namespace: str, project_id: str) -> AgentProject:
        project = self.db.execute(
            select(AgentProject).where(
                AgentProject.namespace == namespace,
                AgentProject.project_id == project_id,
            )
        ).scalar_one_or_none()
        if not project:
            raise NotFoundError("project not found")
        return project

    def get_project_detail(self, *, namespace: str, project_id: str) -> dict[str, Any]:
        project = self.get_project(namespace=namespace, project_id=project_id)
        return self._serialize_project(project)

    def list_projects(self, *, namespace: str | None = None, query: str | None = None, page: int = 1, page_size: int = 20) -> dict:
        if page < 1 or page_size < 1:
            raise ValidationError("page and page_size must be positive")
        stmt = select(AgentProject).order_by(AgentProject.created_at.desc())
        rows = self.db.execute(stmt).scalars().all()
        filtered = []
        for item in rows:
            if namespace and item.namespace != namespace:
                continue
            if query and query.lower() not in item.project_id.lower() and query.lower() not in item.display_name.lower():
                continue
            filtered.append(item)
        total = len(filtered)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start = (page - 1) * page_size
        end = start + page_size
        items = [self._serialize_project(row) for row in filtered[start:end]]
        return {"items": items, "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}

    def add_maintainer(self, *, namespace: str, project_id: str, actor_id: str, principal_id: str) -> None:
        project = self.get_project(namespace=namespace, project_id=project_id)
        self._require_maintainer(project.id, actor_id)
        existing = self.db.execute(
            select(ProjectMaintainer).where(
                ProjectMaintainer.project_ref_id == project.id,
                ProjectMaintainer.principal_id == principal_id,
            )
        ).scalar_one_or_none()
        if existing:
            return
        self.db.add(ProjectMaintainer(project_ref_id=project.id, principal_id=principal_id))
        self.db.flush()

    def create_branch(
        self,
        *,
        namespace: str,
        project_id: str,
        actor_id: str,
        branch_name: str,
        base_ref: str,
    ) -> ProjectBranch:
        project = self.get_project(namespace=namespace, project_id=project_id)
        self._require_maintainer(project.id, actor_id)
        existing = self.db.execute(
            select(ProjectBranch).where(
                ProjectBranch.project_ref_id == project.id,
                ProjectBranch.branch_name == branch_name,
            )
        ).scalar_one_or_none()
        if existing:
            raise ConflictError("branch already exists")
        branch = ProjectBranch(
            project_ref_id=project.id,
            branch_name=branch_name,
            base_ref=base_ref,
            status="active",
            created_by=actor_id,
        )
        self.db.add(branch)
        self.db.flush()
        return branch

    def submit_contribution(
        self,
        *,
        namespace: str,
        project_id: str,
        submitter_id: str,
        branch_name: str,
        title: str,
        summary: str,
        contribution_zone: str,
        contribution_manifest: dict[str, Any],
        metrics: dict[str, Any],
        regressions: dict[str, Any],
    ) -> ProjectContribution:
        project = self.get_project(namespace=namespace, project_id=project_id)
        self._ensure_branch(project.id, branch_name)
        allowed_zones = self._project_zones(project)
        if contribution_zone not in allowed_zones:
            raise ValidationError(f"contribution zone '{contribution_zone}' is not enabled for this project")
        contribution = ProjectContribution(
            project_ref_id=project.id,
            branch_name=branch_name,
            title=title,
            summary=summary,
            contribution_zone=contribution_zone,
            manifest_json=json.dumps(contribution_manifest or {}, sort_keys=True),
            metrics_json=json.dumps(metrics or {}, sort_keys=True),
            regressions_json=json.dumps(regressions or {}, sort_keys=True),
            status="pending",
            submitter_id=submitter_id,
        )
        self.db.add(contribution)
        self.db.flush()
        return contribution

    def evaluate_contribution(
        self,
        *,
        namespace: str,
        project_id: str,
        contribution_id: int,
    ) -> dict[str, Any]:
        project = self.get_project(namespace=namespace, project_id=project_id)
        contribution = self._get_contribution(project.id, contribution_id)
        policy = self._merge_policy(project)
        metrics = json.loads(contribution.metrics_json or "{}")
        regressions = json.loads(contribution.regressions_json or "{}")

        improved_dimensions = [
            key
            for key, value in (metrics.get("improvements") or {}).items()
            if isinstance(value, (int, float)) and value > 0
        ]
        reasons = []
        if len(improved_dimensions) < int(policy.get("min_improvements", 1)):
            reasons.append("insufficient measurable depth improvements")

        latency_regression = float(regressions.get("latency_regression_pct", 0.0))
        if latency_regression > float(policy.get("allowed_latency_regression_pct", 5.0)):
            reasons.append("latency regression exceeds policy threshold")

        cost_regression = float(regressions.get("cost_regression_pct", 0.0))
        if cost_regression > float(policy.get("allowed_cost_regression_pct", 5.0)):
            reasons.append("cost regression exceeds policy threshold")

        if bool(policy.get("must_pass_safety", True)) and not bool(metrics.get("safety_passed", False)):
            reasons.append("safety checks failed")
        if bool(policy.get("must_pass_regression_tests", True)) and not bool(metrics.get("regression_tests_passed", False)):
            reasons.append("regression tests failed")

        gate_passed = not reasons
        evaluation = {
            "gate_passed": gate_passed,
            "improved_dimensions": improved_dimensions,
            "policy": policy,
            "reasons": reasons,
            "evaluation_score": float(metrics.get("evaluation_score", 0.0)),
        }
        contribution.evaluation_json = json.dumps(evaluation, sort_keys=True)
        contribution.status = "evaluated" if gate_passed else "rejected"
        if not gate_passed:
            contribution.decision_notes = "; ".join(reasons)
            contribution.decided_at = utc_now()
        self.db.add(contribution)
        self.db.flush()
        return evaluation

    def review_contribution(
        self,
        *,
        namespace: str,
        project_id: str,
        contribution_id: int,
        reviewer_id: str,
        decision: str,
        decision_notes: str,
        release_version: str | None = None,
        release_channel: str = "stable",
    ) -> dict[str, Any]:
        if decision not in {"merge", "reject"}:
            raise ValidationError("decision must be 'merge' or 'reject'")
        project = self.get_project(namespace=namespace, project_id=project_id)
        self._require_maintainer(project.id, reviewer_id)
        contribution = self._get_contribution(project.id, contribution_id)
        if decision == "reject":
            contribution.status = "rejected"
            contribution.reviewer_id = reviewer_id
            contribution.decision_notes = decision_notes
            contribution.decided_at = utc_now()
            self.db.add(contribution)
            self.db.flush()
            return {"status": contribution.status, "contribution_id": contribution.id}

        if contribution.status not in self.MERGEABLE_STATUSES:
            raise ValidationError("contribution must be evaluated before merge")
        evaluation = json.loads(contribution.evaluation_json or "{}")
        if not evaluation.get("gate_passed"):
            raise ValidationError("contribution did not pass automated evaluation gate")
        channel = release_channel.strip().lower()
        if channel not in self.RELEASE_CHANNELS:
            raise ValidationError(f"unsupported release channel: {release_channel}")
        if not release_version:
            raise ValidationError("release_version is required when merging")
        existing_release = self.db.execute(
            select(ProjectRelease).where(
                ProjectRelease.project_ref_id == project.id,
                ProjectRelease.version == release_version,
                ProjectRelease.channel == channel,
            )
        ).scalar_one_or_none()
        if existing_release:
            raise ConflictError("release already exists for this version/channel")
        release = ProjectRelease(
            project_ref_id=project.id,
            version=release_version,
            channel=channel,
            source_branch=contribution.branch_name,
            changelog=decision_notes,
            created_by=reviewer_id,
        )
        self.db.add(release)
        contribution.status = "merged"
        contribution.reviewer_id = reviewer_id
        contribution.decision_notes = decision_notes
        contribution.merged_release_version = release_version
        contribution.decided_at = utc_now()
        self.db.add(contribution)
        self.db.flush()
        return {"status": contribution.status, "contribution_id": contribution.id, "release": self._serialize_release(release)}

    def list_releases(self, *, namespace: str, project_id: str, channel: str | None = None) -> list[dict[str, Any]]:
        project = self.get_project(namespace=namespace, project_id=project_id)
        stmt = select(ProjectRelease).where(ProjectRelease.project_ref_id == project.id).order_by(ProjectRelease.created_at.desc())
        rows = self.db.execute(stmt).scalars().all()
        output = []
        normalized_channel = channel.strip().lower() if channel else None
        for row in rows:
            if normalized_channel and row.channel != normalized_channel:
                continue
            output.append(self._serialize_release(row))
        return output

    def list_contributions(
        self,
        *,
        namespace: str,
        project_id: str,
        status: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        if limit < 1 or limit > 200:
            raise ValidationError("limit must be between 1 and 200")
        project = self.get_project(namespace=namespace, project_id=project_id)
        stmt = (
            select(ProjectContribution)
            .where(ProjectContribution.project_ref_id == project.id)
            .order_by(ProjectContribution.created_at.desc())
            .limit(limit)
        )
        rows = self.db.execute(stmt).scalars().all()
        normalized_status = status.strip().lower() if status else None
        items = []
        for row in rows:
            if normalized_status and row.status != normalized_status:
                continue
            items.append(self._serialize_contribution(row))
        return {"items": items, "total": len(items)}

    def _require_maintainer(self, project_ref_id: int, principal_id: str) -> None:
        row = self.db.execute(
            select(ProjectMaintainer).where(
                ProjectMaintainer.project_ref_id == project_ref_id,
                ProjectMaintainer.principal_id == principal_id,
            )
        ).scalar_one_or_none()
        if not row:
            raise ValidationError("principal is not a project maintainer")

    def _ensure_branch(self, project_ref_id: int, branch_name: str) -> ProjectBranch:
        branch = self.db.execute(
            select(ProjectBranch).where(
                ProjectBranch.project_ref_id == project_ref_id,
                ProjectBranch.branch_name == branch_name,
            )
        ).scalar_one_or_none()
        if not branch:
            raise NotFoundError("branch not found")
        return branch

    def _get_contribution(self, project_ref_id: int, contribution_id: int) -> ProjectContribution:
        contribution = self.db.execute(
            select(ProjectContribution).where(
                ProjectContribution.project_ref_id == project_ref_id,
                ProjectContribution.id == contribution_id,
            )
        ).scalar_one_or_none()
        if not contribution:
            raise NotFoundError("contribution not found")
        return contribution

    def _project_zones(self, project: AgentProject) -> set[str]:
        return {z for z in project.contribution_zones_csv.split(",") if z}

    def _merge_policy(self, project: AgentProject) -> dict[str, Any]:
        policy = dict(self.DEFAULT_MERGE_POLICY)
        policy.update(json.loads(project.merge_policy_json or "{}"))
        return policy

    def _serialize_project(self, project: AgentProject) -> dict[str, Any]:
        maintainers = self.db.execute(
            select(ProjectMaintainer).where(ProjectMaintainer.project_ref_id == project.id)
        ).scalars().all()
        branches = self.db.execute(
            select(ProjectBranch).where(ProjectBranch.project_ref_id == project.id).order_by(ProjectBranch.created_at.asc())
        ).scalars().all()
        releases = self.db.execute(
            select(ProjectRelease).where(ProjectRelease.project_ref_id == project.id).order_by(ProjectRelease.created_at.desc())
        ).scalars().all()
        return {
            "namespace": project.namespace,
            "project_id": project.project_id,
            "display_name": project.display_name,
            "description": project.description,
            "default_branch": project.default_branch,
            "contribution_zones": sorted(self._project_zones(project)),
            "merge_policy": self._merge_policy(project),
            "maintainers": [m.principal_id for m in maintainers],
            "branches": [
                {"branch_name": b.branch_name, "base_ref": b.base_ref, "status": b.status, "created_by": b.created_by}
                for b in branches
            ],
            "releases": [self._serialize_release(r) for r in releases],
            "created_by": project.created_by,
            "created_at": project.created_at.isoformat(),
        }

    def _serialize_release(self, release: ProjectRelease) -> dict[str, Any]:
        return {
            "version": release.version,
            "channel": release.channel,
            "source_branch": release.source_branch,
            "changelog": release.changelog,
            "created_by": release.created_by,
            "created_at": release.created_at.isoformat(),
        }

    def _serialize_contribution(self, contribution: ProjectContribution) -> dict[str, Any]:
        evaluation = json.loads(contribution.evaluation_json or "{}")
        return {
            "contribution_id": contribution.id,
            "branch_name": contribution.branch_name,
            "title": contribution.title,
            "summary": contribution.summary,
            "contribution_zone": contribution.contribution_zone,
            "status": contribution.status,
            "submitter_id": contribution.submitter_id,
            "reviewer_id": contribution.reviewer_id,
            "decision_notes": contribution.decision_notes,
            "merged_release_version": contribution.merged_release_version,
            "evaluation_gate_passed": evaluation.get("gate_passed"),
            "evaluation_score": evaluation.get("evaluation_score"),
            "created_at": contribution.created_at.isoformat(),
            "decided_at": contribution.decided_at.isoformat() if contribution.decided_at else None,
        }
