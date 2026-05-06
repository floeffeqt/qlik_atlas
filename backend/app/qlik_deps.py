"""Shared helper: resolve Qlik credentials from a project."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import apply_rls_context
from .models import Customer, Project
from shared.qlik_client import QlikCredentials


class CredentialsError(ValueError):
    """Raised when project credentials cannot be resolved. Carries an HTTP status hint."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


async def resolve_project_creds(
    project_id: int,
    session: AsyncSession,
    actor_user_id: int,
    actor_role: str,
) -> QlikCredentials:
    """Load Project → Customer → QlikCredentials.

    Raises:
        CredentialsError(status=404): project or customer not found.
        CredentialsError(status=422): credentials present but incomplete.
    """
    await apply_rls_context(session, actor_user_id, actor_role)
    proj = (await session.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not proj:
        raise CredentialsError(f"Project {project_id} not found", status=404)
    cust = (await session.execute(select(Customer).where(Customer.id == proj.customer_id))).scalar_one_or_none()
    if not cust:
        raise CredentialsError("Customer for project not found", status=404)
    if not cust.tenant_url or not cust.api_key:
        raise CredentialsError("Customer credentials incomplete (tenant_url or api_key missing)", status=422)
    return QlikCredentials(tenant_url=cust.tenant_url, api_key=cust.api_key)
