from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Iterable

from sqlalchemy import or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    LineageEdge,
    LineageNode,
    QlikApp,
    QlikAppScript,
    QlikAppUsage,
    QlikDataConnection,
    QlikSpace,
)


def _normalize_project_scope(
    *,
    project_id: int | None = None,
    project_ids: Iterable[int] | None = None,
) -> list[int] | None:
    if project_id is None and project_ids is None:
        return None

    values: list[int] = []
    if project_ids is not None:
        for value in project_ids:
            values.append(int(value))
    if project_id is not None:
        values.append(int(project_id))
    return sorted(set(values))


def _apply_project_scope(stmt: Any, column: Any, project_ids: list[int] | None) -> Any:
    if project_ids is None:
        return stmt
    if not project_ids:
        return stmt.where(False)
    return stmt.where(column.in_(project_ids))


def _mapping_rows_to_namespaces(rows: Iterable[Any]) -> list[Any]:
    return [SimpleNamespace(**dict(row)) for row in rows]


async def _execute_namespaced_rows(session: AsyncSession, stmt: Any) -> list[Any]:
    rows = (await session.execute(stmt)).mappings().all()
    return _mapping_rows_to_namespaces(rows)


async def fetch_graph_rows(
    session: AsyncSession,
    *,
    project_id: int | None = None,
    project_ids: Iterable[int] | None = None,
) -> tuple[list[Any], list[Any], list[Any]]:
    scope_ids = _normalize_project_scope(project_id=project_id, project_ids=project_ids)

    node_stmt = _apply_project_scope(
        select(
            LineageNode.project_id.label("project_id"),
            LineageNode.node_id.label("node_id"),
            LineageNode.app_id.label("app_id"),
            LineageNode.node_type.label("node_type"),
            LineageNode.data.label("data"),
        ),
        LineageNode.project_id,
        scope_ids,
    )
    edge_stmt = _apply_project_scope(
        select(
            LineageEdge.project_id.label("project_id"),
            LineageEdge.edge_id.label("edge_id"),
            LineageEdge.app_id.label("app_id"),
            LineageEdge.source_node_id.label("source_node_id"),
            LineageEdge.target_node_id.label("target_node_id"),
            LineageEdge.data.label("data"),
        ),
        LineageEdge.project_id,
        scope_ids,
    )
    connection_stmt = _apply_project_scope(
        select(
            QlikDataConnection.project_id.label("project_id"),
            QlikDataConnection.connection_id.label("connection_id"),
            QlikDataConnection.space_id.label("space_id"),
            QlikDataConnection.qri.label("qri"),
            QlikDataConnection.q_connect_statement.label("q_connect_statement"),
            QlikDataConnection.data.label("data"),
        ),
        QlikDataConnection.project_id,
        scope_ids,
    )

    node_rows = await _execute_namespaced_rows(session, node_stmt)
    edge_rows = await _execute_namespaced_rows(session, edge_stmt)
    connection_rows = await _execute_namespaced_rows(session, connection_stmt)
    return node_rows, edge_rows, connection_rows


async def fetch_graph_context_rows(
    session: AsyncSession,
    *,
    project_ids: Iterable[int],
) -> tuple[list[Any], list[Any]]:
    scope_ids = _normalize_project_scope(project_ids=project_ids)
    if not scope_ids:
        return [], []

    app_stmt = _apply_project_scope(
        select(
            QlikApp.project_id.label("project_id"),
            QlikApp.app_id.label("app_id"),
            QlikApp.name_value.label("name_value"),
            QlikApp.app_name.label("app_name"),
            QlikApp.space_id.label("space_id"),
            QlikApp.space_id_payload.label("space_id_payload"),
            QlikApp.root_node_id.label("root_node_id"),
            QlikApp.data.label("data"),
        ),
        QlikApp.project_id,
        scope_ids,
    )
    space_stmt = _apply_project_scope(
        select(
            QlikSpace.project_id.label("project_id"),
            QlikSpace.space_id.label("space_id"),
            QlikSpace.space_id_payload.label("space_id_payload"),
            QlikSpace.space_name.label("space_name"),
            QlikSpace.data.label("data"),
        ),
        QlikSpace.project_id,
        scope_ids,
    )
    return (
        await _execute_namespaced_rows(session, app_stmt),
        await _execute_namespaced_rows(session, space_stmt),
    )


async def fetch_inventory_rows(session: AsyncSession) -> tuple[list[Any], list[Any]]:
    app_stmt = select(
        QlikApp.project_id.label("project_id"),
        QlikApp.app_id.label("app_id"),
        QlikApp.name_value.label("name_value"),
        QlikApp.app_name.label("app_name"),
        QlikApp.space_id.label("space_id"),
        QlikApp.space_id_payload.label("space_id_payload"),
        QlikApp.root_node_id.label("root_node_id"),
        QlikApp.nodes_count.label("nodes_count"),
        QlikApp.edges_count.label("edges_count"),
        QlikApp.status.label("status"),
        QlikApp.file_name.label("file_name"),
        QlikApp.fetched_at.label("fetched_at"),
        QlikApp.data.label("data"),
    )
    space_stmt = select(
        QlikSpace.project_id.label("project_id"),
        QlikSpace.space_id.label("space_id"),
        QlikSpace.space_id_payload.label("space_id_payload"),
        QlikSpace.space_name.label("space_name"),
        QlikSpace.data.label("data"),
    )
    return (
        await _execute_namespaced_rows(session, app_stmt),
        await _execute_namespaced_rows(session, space_stmt),
    )


async def fetch_space_rows(session: AsyncSession) -> list[Any]:
    stmt = select(
        QlikSpace.project_id.label("project_id"),
        QlikSpace.space_id.label("space_id"),
        QlikSpace.space_type.label("space_type"),
        QlikSpace.owner_id.label("owner_id"),
        QlikSpace.space_id_payload.label("space_id_payload"),
        QlikSpace.tenant_id.label("tenant_id"),
        QlikSpace.created_at_source.label("created_at_source"),
        QlikSpace.space_name.label("space_name"),
        QlikSpace.updated_at_source.label("updated_at_source"),
        QlikSpace.data.label("data"),
    )
    return await _execute_namespaced_rows(session, stmt)


async def fetch_data_connection_rows(session: AsyncSession) -> list[Any]:
    stmt = select(
        QlikDataConnection.project_id.label("project_id"),
        QlikDataConnection.connection_id.label("connection_id"),
        QlikDataConnection.space_id.label("space_id"),
        QlikDataConnection.q_id.label("q_id"),
        QlikDataConnection.qri.label("qri"),
        QlikDataConnection.tags.label("tags"),
        QlikDataConnection.user_name.label("user_name"),
        QlikDataConnection.links.label("links"),
        QlikDataConnection.q_name.label("q_name"),
        QlikDataConnection.q_type.label("q_type"),
        QlikDataConnection.space_payload.label("space_payload"),
        QlikDataConnection.q_log_on.label("q_log_on"),
        QlikDataConnection.tenant.label("tenant"),
        QlikDataConnection.created_source.label("created_source"),
        QlikDataConnection.updated_source.label("updated_source"),
        QlikDataConnection.version.label("version"),
        QlikDataConnection.privileges.label("privileges"),
        QlikDataConnection.datasource_id.label("datasource_id"),
        QlikDataConnection.q_architecture.label("q_architecture"),
        QlikDataConnection.q_credentials_id.label("q_credentials_id"),
        QlikDataConnection.q_engine_object_id.label("q_engine_object_id"),
        QlikDataConnection.q_separate_credentials.label("q_separate_credentials"),
        QlikDataConnection.data.label("data"),
    )
    return await _execute_namespaced_rows(session, stmt)


async def fetch_latest_app_row(session: AsyncSession, *, app_id: str) -> Any | None:
    stmt = (
        select(
            QlikApp.project_id.label("project_id"),
            QlikApp.app_id.label("app_id"),
            QlikApp.name_value.label("name_value"),
            QlikApp.app_name.label("app_name"),
            QlikApp.root_node_id.label("root_node_id"),
            QlikApp.data.label("data"),
            QlikApp.fetched_at.label("fetched_at"),
        )
        .where(QlikApp.app_id == app_id)
        .order_by(QlikApp.fetched_at.desc(), QlikApp.project_id.desc())
        .limit(1)
    )
    rows = await _execute_namespaced_rows(session, stmt)
    return rows[0] if rows else None


async def fetch_latest_app_usage_row(session: AsyncSession, *, app_id: str) -> Any | None:
    stmt = (
        select(
            QlikAppUsage.project_id.label("project_id"),
            QlikAppUsage.app_id.label("app_id"),
            QlikAppUsage.app_id_payload.label("app_id_payload"),
            QlikAppUsage.app_name.label("app_name"),
            QlikAppUsage.window_days.label("window_days"),
            QlikAppUsage.usage_reloads.label("usage_reloads"),
            QlikAppUsage.usage_app_opens.label("usage_app_opens"),
            QlikAppUsage.usage_sheet_views.label("usage_sheet_views"),
            QlikAppUsage.usage_unique_users.label("usage_unique_users"),
            QlikAppUsage.usage_last_reload_at.label("usage_last_reload_at"),
            QlikAppUsage.usage_last_viewed_at.label("usage_last_viewed_at"),
            QlikAppUsage.usage_classification.label("usage_classification"),
            QlikAppUsage.connections.label("connections"),
            QlikAppUsage.generated_at_payload.label("generated_at_payload"),
            QlikAppUsage.artifact_file_name.label("artifact_file_name"),
            QlikAppUsage.data.label("data"),
            QlikAppUsage.generated_at.label("generated_at"),
        )
        .where(QlikAppUsage.app_id == app_id)
        .order_by(QlikAppUsage.generated_at.desc(), QlikAppUsage.project_id.desc())
        .limit(1)
    )
    rows = await _execute_namespaced_rows(session, stmt)
    return rows[0] if rows else None


async def fetch_latest_app_script_row(session: AsyncSession, *, app_id: str) -> Any | None:
    stmt = (
        select(
            QlikAppScript.project_id.label("project_id"),
            QlikAppScript.app_id.label("app_id"),
            QlikAppScript.script.label("script"),
            QlikAppScript.source.label("source"),
            QlikAppScript.file_name.label("file_name"),
            QlikAppScript.data.label("data"),
            QlikAppScript.fetched_at.label("fetched_at"),
        )
        .where(QlikAppScript.app_id == app_id)
        .order_by(QlikAppScript.fetched_at.desc(), QlikAppScript.project_id.desc())
        .limit(1)
    )
    rows = await _execute_namespaced_rows(session, stmt)
    return rows[0] if rows else None


async def fetch_related_project_ids_for_node(session: AsyncSession, *, node_id: str) -> list[int]:
    node_stmt = select(LineageNode.project_id.label("project_id")).where(LineageNode.node_id == node_id)
    edge_stmt = select(LineageEdge.project_id.label("project_id")).where(
        or_(LineageEdge.source_node_id == node_id, LineageEdge.target_node_id == node_id)
    )
    stmt = union(node_stmt, edge_stmt)
    rows = (await session.execute(stmt)).all()
    return sorted({int(project_id) for (project_id,) in rows if project_id is not None})
