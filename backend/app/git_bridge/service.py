"""Script sync business logic: drift detection, hash comparison, provider factory."""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Customer, Project, ScriptGitMapping, ScriptDeployment
from .provider import GitFileContent, GitProvider
from .github_provider import GitHubProvider
from .gitlab_provider import GitLabProvider

logger = logging.getLogger("atlas.git.service")

SyncStatus = Literal["in_sync", "git_ahead", "qlik_ahead", "diverged", "unmapped", "error"]


def normalize_script(raw: str) -> str:
    """Normalize a Qlik load script for consistent hashing.

    Strips BOM, normalises line endings, removes trailing whitespace per line.
    """
    text = raw.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    # Remove trailing empty lines
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def script_hash(script: str) -> str:
    """SHA-256 hex digest of a normalised script."""
    return hashlib.sha256(normalize_script(script).encode("utf-8")).hexdigest()


def build_provider(customer: Customer) -> GitProvider:
    """Create the appropriate GitProvider from customer settings."""
    provider_type = (customer.git_provider or "").lower().strip()
    token = customer.git_token
    if not token:
        raise ValueError(f"Customer '{customer.name}' has no Git token configured")

    base_url = customer.git_base_url or None

    if provider_type == "github":
        return GitHubProvider(token=token, base_url=base_url)
    elif provider_type == "gitlab":
        return GitLabProvider(token=token, base_url=base_url)
    else:
        raise ValueError(
            f"Unsupported git_provider '{provider_type}' for customer '{customer.name}'. "
            "Expected 'github' or 'gitlab'."
        )


async def get_customer_for_project(
    session: AsyncSession, project_id: int
) -> Customer:
    """Resolve the customer that owns a project."""
    result = await session.execute(
        select(Customer)
        .join(Project, Project.customer_id == Customer.id)
        .where(Project.id == project_id)
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise ValueError(f"No customer found for project_id={project_id}")
    return customer


async def get_mapping(
    session: AsyncSession, project_id: int, app_id: str
) -> ScriptGitMapping | None:
    result = await session.execute(
        select(ScriptGitMapping).where(
            ScriptGitMapping.project_id == project_id,
            ScriptGitMapping.app_id == app_id,
        )
    )
    return result.scalar_one_or_none()


async def check_drift(
    session: AsyncSession,
    project_id: int,
    app_id: str,
    qlik_script: str | None = None,
) -> dict:
    """Compare Git and Qlik script hashes and return sync status.

    If qlik_script is None, only the stored hash is used.
    Returns a dict with status info suitable for API response.
    """
    mapping = await get_mapping(session, project_id, app_id)
    if not mapping:
        return {"status": "unmapped", "app_id": app_id}

    customer = await get_customer_for_project(session, project_id)
    provider = build_provider(customer)

    try:
        git_file: GitFileContent = await provider.read_file(
            repo=mapping.repo_identifier,
            branch=mapping.branch,
            file_path=mapping.file_path,
        )
    except Exception as exc:
        logger.warning("Failed to read git file for app %s: %s", app_id, exc)
        return {"status": "error", "app_id": app_id, "detail": str(exc)}
    finally:
        await provider.close()

    git_h = script_hash(git_file.content)

    qlik_h = script_hash(qlik_script) if qlik_script else mapping.last_qlik_script_hash
    old_git_h = mapping.last_git_script_hash

    # Determine status
    if qlik_h and git_h == qlik_h:
        status: SyncStatus = "in_sync"
    elif old_git_h and qlik_h:
        if git_h != old_git_h and qlik_h == old_git_h:
            status = "git_ahead"
        elif git_h == old_git_h and qlik_h != old_git_h:
            status = "qlik_ahead"
        else:
            status = "diverged"
    elif qlik_h is None:
        status = "git_ahead"
    else:
        status = "git_ahead" if git_h != qlik_h else "in_sync"

    # Persist latest check
    mapping.last_git_commit_sha = git_file.commit_sha
    mapping.last_git_script_hash = git_h
    if qlik_script is not None:
        mapping.last_qlik_script_hash = script_hash(qlik_script)
    mapping.last_checked_at = datetime.now(timezone.utc)

    return {
        "status": status,
        "app_id": app_id,
        "git_commit_sha": git_file.commit_sha,
        "git_script_hash": git_h,
        "qlik_script_hash": qlik_h,
        "last_checked_at": mapping.last_checked_at.isoformat(),
    }


async def log_deployment(
    session: AsyncSession,
    *,
    project_id: int,
    app_id: str,
    direction: str,
    status: str,
    triggered_by: int | None = None,
    git_commit_sha: str | None = None,
    git_script_hash: str | None = None,
    qlik_script_hash: str | None = None,
    version_message: str | None = None,
    error_detail: str | None = None,
) -> ScriptDeployment:
    entry = ScriptDeployment(
        project_id=project_id,
        app_id=app_id,
        direction=direction,
        status=status,
        triggered_by=triggered_by,
        git_commit_sha=git_commit_sha,
        git_script_hash=git_script_hash,
        qlik_script_hash=qlik_script_hash,
        version_message=version_message,
        error_detail=error_detail,
    )
    session.add(entry)
    return entry