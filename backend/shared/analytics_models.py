from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class AnalyticsAreaItem(BaseModel):
    area_key: str
    area_name: str
    apps_count: int
    nodes_estimate: int
    total_static_byte_size_latest: int
    peak_memory_latest_max: int
    direct_query_apps_count: int
    section_access_missing_count: int
    schema_drift_apps_count: int


class AnalyticsAreaTotals(BaseModel):
    areas_count: int
    apps_count: int
    nodes_estimate: int
    total_static_byte_size_latest: int
    peak_memory_latest_max: int
    direct_query_apps_count: int
    section_access_missing_count: int
    schema_drift_apps_count: int


class AnalyticsAreasResponse(BaseModel):
    areas: list[AnalyticsAreaItem]
    totals: AnalyticsAreaTotals


class AnalyticsAppItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_id: str | None = None
    space_name: str | None = None
    latest_fetched_at: datetime | None = None
    static_byte_size_latest: int | None = None
    reload_meta_peak_memory_bytes_latest: int | None = None
    reload_meta_cpu_time_spent_ms_latest: int | None = None
    is_direct_query_mode_latest: bool | None = None
    has_section_access_latest: bool | None = None
    fields_count_latest: int = 0
    tables_count_latest: int = 0
    schema_hash_latest: str | None = None
    schema_drift_count_in_window: int = 0


class AnalyticsAreaAppsResponse(BaseModel):
    area_key: str
    area_name: str
    apps: list[AnalyticsAppItem]


class AnalyticsFieldItem(BaseModel):
    row_id: int
    field_hash: str
    name: str | None = None
    byte_size: int | None = None
    cardinal: int | None = None
    total_count: int | None = None
    is_numeric: bool | None = None
    is_semantic: bool | None = None
    is_system: bool | None = None
    is_hidden: bool | None = None
    is_locked: bool | None = None
    distinct_only: bool | None = None
    always_one_selected: bool | None = None
    tags: list[str] | None = None
    src_tables: list[str] | None = None


class AnalyticsPaging(BaseModel):
    limit: int
    offset: int
    total: int
    sort_by: str
    sort_dir: Literal["asc", "desc"]
    search: str | None = None


class AnalyticsAppFieldsResponse(BaseModel):
    app_id: str
    project_id: int
    snapshot_id: int | None = None
    fields: list[AnalyticsFieldItem]
    paging: AnalyticsPaging


class AnalyticsTrendPoint(BaseModel):
    fetched_at: datetime
    static_byte_size: int | None = None
    reload_meta_peak_memory_bytes: int | None = None
    reload_meta_cpu_time_spent_ms: int | None = None
    schema_hash: str | None = None


class AnalyticsAppTrendResponse(BaseModel):
    app_id: str
    project_id: int
    days: int
    points: list[AnalyticsTrendPoint]


class CostValueAppItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    latest_fetched_at: datetime | None = None
    static_byte_size_latest: int = 0
    reload_meta_peak_memory_bytes_latest: int = 0
    reload_meta_cpu_time_spent_ms_latest: int = 0
    has_section_access_latest: bool | None = None
    is_direct_query_mode_latest: bool | None = None
    fields_count_latest: int = 0
    tables_count_latest: int = 0
    usage_app_opens: int = 0
    usage_sheet_views: int = 0
    usage_unique_users: int = 0
    usage_reloads: int = 0
    complexity_raw: float = 0.0
    cost_raw: float = 0.0
    value_usage_raw: float = 0.0
    value_proxy_raw: float = 0.0
    complexity_score: float = 0.0
    cost_score: float = 0.0
    value_score: float = 0.0
    value_usage_score: float = 0.0
    value_proxy_score: float = 0.0
    value_signal_mode: str = "usage-primary"
    efficiency_score: float = 0.0
    quadrant: str


class CostValueSummary(BaseModel):
    apps_count: int
    high_cost_low_value_count: int
    avg_cost_score: float
    avg_value_score: float
    value_signal_mode: str = "usage-primary"
    value_usage_weight: float = 0.85
    value_proxy_weight: float = 0.15


class CostValueMapResponse(BaseModel):
    apps: list[CostValueAppItem]
    summary: CostValueSummary


class BloatAppItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    static_byte_size_latest: int = 0
    fields_count_latest: int = 0
    tables_count_latest: int = 0
    schema_drift_count_in_window: int = 0


class BloatTableItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    table_name: str
    byte_size: int = 0
    no_of_rows: int = 0
    no_of_fields: int = 0
    no_of_key_fields: int = 0
    is_system: bool | None = None
    is_semantic: bool | None = None


class BloatFieldItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    field_hash: str
    name: str | None = None
    byte_size: int = 0
    cardinal: int = 0
    total_count: int = 0
    is_system: bool | None = None
    is_hidden: bool | None = None
    is_semantic: bool | None = None
    src_tables: list[str] | None = None


class BloatExplorerSummary(BaseModel):
    apps_count: int
    top_tables_count: int
    top_fields_count: int
    schema_drift_apps_count: int


class BloatExplorerResponse(BaseModel):
    top_apps: list[BloatAppItem]
    top_tables: list[BloatTableItem]
    top_fields: list[BloatFieldItem]
    schema_drift_apps: list[BloatAppItem]
    summary: BloatExplorerSummary


class DataModelPackAppItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    static_byte_size_latest: int = 0
    fields_count_latest: int = 0
    tables_count_latest: int = 0
    complexity_latest: int = 0
    metric_value: float = 0.0


class DataModelPackAreaItem(BaseModel):
    area_key: str
    area_name: str
    metric_value: float = 0.0
    apps: list[DataModelPackAppItem]


class DataModelPackSummary(BaseModel):
    areas_count: int
    apps_count: int
    total_metric_value: float = 0.0


class DataModelPackResponse(BaseModel):
    metric: Literal["static_byte_size_latest", "complexity_latest"]
    metric_options: list[Literal["static_byte_size_latest", "complexity_latest"]]
    areas: list[DataModelPackAreaItem]
    summary: DataModelPackSummary


class LineageCriticalNodeItem(BaseModel):
    project_id: int
    node_id: str
    label: str
    node_type: str
    app_id: str | None = None
    app_name: str | None = None
    space_name: str | None = None
    degree: int
    in_degree: int
    out_degree: int
    blast_radius: int
    criticality_score: float


class LineageCriticalitySummary(BaseModel):
    nodes_count: int
    edges_count: int
    critical_nodes_count: int


class LineageCriticalityResponse(BaseModel):
    critical_nodes: list[LineageCriticalNodeItem]
    summary: LineageCriticalitySummary


class GovernanceOpsSummary(BaseModel):
    apps_total: int
    low_or_no_usage_apps_count: int
    no_usage_apps_count: int
    low_usage_apps_count: int
    low_signal_tables_count: int
    low_signal_fields_count: int
    low_signal_qvds_count: int
    low_usage_signal_threshold: float = 0.0


class GovernanceLowUsageAppItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    latest_fetched_at: datetime | None = None
    static_byte_size_latest: int = 0
    reload_meta_peak_memory_bytes_latest: int = 0
    reload_meta_cpu_time_spent_ms_latest: int = 0
    usage_app_opens: int = 0
    usage_sheet_views: int = 0
    usage_unique_users: int = 0
    usage_reloads: int = 0
    usage_signal_score: float = 0.0
    usage_classification: str
    reason: str


class GovernanceLowSignalTableItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    usage_classification: str
    usage_signal_score: float = 0.0
    usage_app_opens: int = 0
    usage_sheet_views: int = 0
    usage_unique_users: int = 0
    usage_reloads: int = 0
    table_name: str
    byte_size: int = 0
    no_of_rows: int = 0
    no_of_fields: int = 0
    no_of_key_fields: int = 0
    is_semantic: bool | None = None
    reason: str


class GovernanceLowSignalFieldItem(BaseModel):
    project_id: int
    app_id: str
    app_name: str
    space_name: str | None = None
    usage_classification: str
    usage_signal_score: float = 0.0
    usage_app_opens: int = 0
    usage_sheet_views: int = 0
    usage_unique_users: int = 0
    usage_reloads: int = 0
    field_hash: str
    name: str | None = None
    byte_size: int = 0
    cardinal: int = 0
    total_count: int = 0
    is_hidden: bool | None = None
    is_semantic: bool | None = None
    src_tables: list[str] | None = None
    reason: str


class GovernanceLowSignalQvdItem(BaseModel):
    project_id: int
    node_id: str
    label: str
    app_id: str | None = None
    app_name: str | None = None
    space_name: str | None = None
    usage_signal_score: float = 0.0
    usage_app_opens: int = 0
    usage_sheet_views: int = 0
    usage_unique_users: int = 0
    usage_reloads: int = 0
    linked_app_low_usage: bool = False
    degree: int = 0
    in_degree: int = 0
    out_degree: int = 0
    signal_classification: str
    reason: str


class GovernanceActionItem(BaseModel):
    action_id: str
    priority: str
    title: str
    scope: str
    candidate_count: int = 0
    target_metric: str
    rationale: str
    suggested_steps: list[str]


class GovernanceOperationsResponse(BaseModel):
    summary: GovernanceOpsSummary
    low_usage_apps: list[GovernanceLowUsageAppItem]
    low_signal_tables: list[GovernanceLowSignalTableItem]
    low_signal_fields: list[GovernanceLowSignalFieldItem]
    low_signal_qvds: list[GovernanceLowSignalQvdItem]
    action_plan: list[GovernanceActionItem]
