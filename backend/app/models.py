from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    Float,
    String,
    DateTime,
    func,
    Boolean,
    Text,
    ForeignKey,
    PrimaryKeyConstraint,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
from .database import Base
from .credentials_crypto import encrypt_credential, decrypt_credential


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    role = Column(String(20), nullable=False, server_default="user")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Customer(Base):
    """A customer / tenant with its own Qlik Cloud credentials."""
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    _tenant_url_encrypted = Column("tenant_url", Text, nullable=False)
    _api_key_encrypted = Column("api_key", Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    @property
    def tenant_url(self) -> str:
        return decrypt_credential(
            self._tenant_url_encrypted,
            context="customers.tenant_url",
            allow_plaintext_fallback=True,
        )

    @tenant_url.setter
    def tenant_url(self, value: str) -> None:
        self._tenant_url_encrypted = encrypt_credential(value, context="customers.tenant_url")

    @property
    def api_key(self) -> str:
        return decrypt_credential(
            self._api_key_encrypted,
            context="customers.api_key",
            allow_plaintext_fallback=True,
        )

    @api_key.setter
    def api_key(self, value: str) -> None:
        self._api_key_encrypted = encrypt_credential(value, context="customers.api_key")


class Project(Base):
    """A project assigned to a customer. Lineage data is isolated per project."""
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserCustomerAccess(Base):
    """Customer assignments for non-admin users (admins effectively have full access)."""
    __tablename__ = "user_customer_access"
    __table_args__ = (PrimaryKeyConstraint("user_id", "customer_id"),)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_refresh_tokens_hash"),)
    token_id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    replaced_by_token_id = Column(BigInteger, ForeignKey("refresh_tokens.token_id", ondelete="SET NULL"), nullable=True)


class QlikApp(Base):
    """Qlik app metadata scoped to a project (composite PK)."""
    __tablename__ = "qlik_apps"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'app_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    app_id = Column(String(100), nullable=False)
    space_id = Column(String(100), index=True)
    name_value = Column("name", String(255), nullable=True)
    app_id_payload = Column("appId", String(100), nullable=True)
    item_id = Column("id", String(120), nullable=True)
    owner_id = Column("ownerId", String(120), nullable=True)
    description = Column(Text, nullable=True)
    resource_type = Column("resourceType", String(120), nullable=True)
    resource_id = Column("resourceId", String(120), nullable=True)
    thumbnail = Column(String(1024), nullable=True)
    resource_attributes_id = Column("resourceAttributes_id", String(120), nullable=True)
    resource_attributes_name = Column("resourceAttributes_name", String(255), nullable=True)
    resource_attributes_description = Column("resourceAttributes_description", Text, nullable=True)
    resource_attributes_created_date = Column("resourceAttributes_createdDate", Text, nullable=True)
    resource_attributes_modified_date = Column("resourceAttributes_modifiedDate", Text, nullable=True)
    resource_attributes_modified_by_user_name = Column("resourceAttributes_modifiedByUserName", String(255), nullable=True)
    resource_attributes_publish_time = Column("resourceAttributes_publishTime", Text, nullable=True)
    resource_attributes_last_reload_time = Column("resourceAttributes_lastReloadTime", Text, nullable=True)
    resource_attributes_trashed = Column("resourceAttributes_trashed", Boolean, nullable=True)
    resource_custom_attributes_json = Column("resourceCustomAttributes_json", JSONB, nullable=True)
    status = Column(Integer, nullable=True)
    app_name = Column("appName", String(255), nullable=True, index=True)
    space_id_payload = Column("spaceId", String(100), nullable=True)
    file_name = Column("fileName", String(512), nullable=True)
    item_type = Column("itemType", String(100), nullable=True)
    edges_count = Column("edgesCount", Integer, nullable=True)
    nodes_count = Column("nodesCount", Integer, nullable=True)
    root_node_id = Column("rootNodeId", Text, nullable=True)
    lineage_fetched = Column("lineageFetched", Boolean, nullable=True)
    lineage_success = Column("lineageSuccess", Boolean, nullable=True)
    source = Column(String(255), nullable=True)
    tenant = Column(String(255), nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikSpace(Base):
    """Qlik space metadata scoped to a project (composite PK)."""
    __tablename__ = "qlik_spaces"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'space_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    space_id = Column(String(100), nullable=False)
    space_type = Column("type", String(100), nullable=True)
    owner_id = Column("ownerId", String(255), nullable=True)
    space_id_payload = Column("spaceId", String(100), nullable=True, index=True)
    tenant_id = Column("tenantId", String(100), nullable=True)
    created_at_source = Column("createdAt", Text, nullable=True)
    space_name = Column("spaceName", String(255), nullable=True, index=True)
    updated_at_source = Column("updatedAt", Text, nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikDataConnection(Base):
    """Qlik data connections scoped to a project (composite PK)."""
    __tablename__ = "qlik_data_connections"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'connection_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    connection_id = Column(String(120), nullable=False)
    space_id = Column(String(100), nullable=True, index=True)
    id_payload = Column("id", String(120), nullable=True)
    q_id = Column("qID", String(120), nullable=True)
    qri = Column(Text, nullable=True)
    tags = Column(JSONB, nullable=True)
    user_name = Column("user", String(255), nullable=True)
    links = Column(JSONB, nullable=True)
    q_name = Column("qName", String(255), nullable=True, index=True)
    q_type = Column("qType", String(120), nullable=True)
    space_payload = Column("space", String(100), nullable=True, index=True)
    q_log_on = Column("qLogOn", Boolean, nullable=True)
    tenant = Column(String(100), nullable=True)
    created_source = Column("created", Text, nullable=True)
    updated_source = Column("updated", Text, nullable=True)
    version = Column(String(100), nullable=True)
    privileges = Column(JSONB, nullable=True)
    datasource_id = Column("datasourceID", String(255), nullable=True)
    q_architecture = Column("qArchitecture", JSONB, nullable=True)
    q_credentials_id = Column("qCredentialsID", String(255), nullable=True)
    q_engine_object_id = Column("qEngineObjectID", String(255), nullable=True)
    q_connect_statement = Column("qConnectStatement", Text, nullable=True)
    q_separate_credentials = Column("qSeparateCredentials", Boolean, nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikAppUsage(Base):
    """Latest app usage payload scoped to a project (composite PK)."""
    __tablename__ = "qlik_app_usage"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'app_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    app_id = Column(String(100), nullable=False)
    app_id_payload = Column("appId", String(100), nullable=True)
    app_name = Column("appName", String(255), nullable=True, index=True)
    window_days = Column("windowDays", Integer, nullable=True)
    usage_reloads = Column("usageReloads", Integer, nullable=True)
    usage_app_opens = Column("usageAppOpens", Integer, nullable=True)
    usage_sheet_views = Column("usageSheetViews", Integer, nullable=True)
    usage_unique_users = Column("usageUniqueUsers", Integer, nullable=True)
    usage_last_reload_at = Column("usageLastReloadAt", Text, nullable=True)
    usage_last_viewed_at = Column("usageLastViewedAt", Text, nullable=True)
    usage_classification = Column("usageClassification", String(100), nullable=True)
    connections = Column(JSONB, nullable=True)
    generated_at_payload = Column("generatedAt", Text, nullable=True)
    artifact_file_name = Column("_artifactFileName", String(255), nullable=True)
    data = Column(JSONB, nullable=False)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikAppScript(Base):
    """App load script payload scoped to a project (composite PK)."""
    __tablename__ = "qlik_app_scripts"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'app_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    app_id = Column(String(100), nullable=False)
    script = Column(Text, nullable=False)
    source = Column(String(40), nullable=True)
    file_name = Column(String(255), nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikReload(Base):
    """Qlik reload records scoped to a project (composite PK)."""
    __tablename__ = "qlik_reloads"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'reload_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    reload_id = Column(String(120), nullable=False)
    app_id = Column(String(100), nullable=True, index=True)
    log = Column(Text, nullable=True)
    reload_type = Column("type", String(120), nullable=True)
    status = Column(String(120), nullable=True)
    user_id = Column("userId", String(120), nullable=True)
    weight = Column(Integer, nullable=True)
    end_time = Column("endTime", Text, nullable=True)
    partial = Column(Boolean, nullable=True)
    tenant_id_payload = Column("tenantId", String(120), nullable=True)
    error_code = Column("errorCode", String(120), nullable=True)
    error_message = Column("errorMessage", Text, nullable=True)
    start_time = Column("startTime", Text, nullable=True)
    engine_time = Column("engineTime", Text, nullable=True)
    creation_time = Column("creationTime", Text, nullable=True)
    created_date = Column("createdDate", Text, nullable=True)
    created_date_ts = Column(DateTime(timezone=True), nullable=True, index=True)
    modified_date = Column("modifiedDate", Text, nullable=True)
    modified_by_user_name = Column("modifiedByUserName", String(255), nullable=True)
    owner_id = Column("ownerId", String(120), nullable=True)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    log_available = Column("logAvailable", Boolean, nullable=True)
    operational_id = Column("operational_id", String(120), nullable=True)
    operational_next_execution = Column("operational_nextExecution", Text, nullable=True)
    operational_times_executed = Column("operational_timesExecuted", Integer, nullable=True)
    operational_state = Column("operational_state", String(120), nullable=True)
    operational_hash = Column("operational_hash", String(255), nullable=True)
    links_self_href = Column("links_self_href", Text, nullable=True)
    source = Column(String(255), nullable=True)
    tenant = Column(String(255), nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikAudit(Base):
    """Qlik audit records scoped to a project (composite PK)."""
    __tablename__ = "qlik_audits"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'audit_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    audit_id = Column(String(200), nullable=False)
    user_id = Column("userId", String(120), nullable=True)
    event_id = Column("eventId", String(120), nullable=True)
    tenant_id_payload = Column("tenantId", String(120), nullable=True)
    event_time = Column("eventTime", Text, nullable=True)
    event_type = Column("eventType", String(255), nullable=True)
    links_self_href = Column("links_self_href", Text, nullable=True)
    extensions_actor_sub = Column("extensions_actor_sub", String(255), nullable=True)
    time = Column(Text, nullable=True)
    time_ts = Column(DateTime(timezone=True), nullable=True, index=True)
    sub_type = Column("subType", String(120), nullable=True)
    space_id = Column("spaceId", String(120), nullable=True)
    space_type = Column("spaceType", String(120), nullable=True)
    category = Column(String(120), nullable=True)
    audit_type = Column("type", String(120), nullable=True)
    actor_id = Column("actorId", String(255), nullable=True)
    actor_type = Column("actorType", String(120), nullable=True)
    origin = Column(String(255), nullable=True)
    context = Column(Text, nullable=True)
    ip_address = Column("ipAddress", String(120), nullable=True)
    user_agent = Column("userAgent", Text, nullable=True)
    properties_app_id = Column("properties_appId", String(120), nullable=True, index=True)
    data_message = Column("data_message", Text, nullable=True)
    source = Column(String(255), nullable=True)
    tenant = Column(String(255), nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikLicenseConsumption(Base):
    """Qlik license consumption records scoped to a project (composite PK)."""
    __tablename__ = "qlik_license_consumption"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'consumption_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    consumption_id = Column(String(120), nullable=False)
    app_id_payload = Column("appId", String(120), nullable=True, index=True)
    user_id = Column("userId", String(120), nullable=True, index=True)
    end_time = Column("endTime", Text, nullable=True)
    duration = Column(String(120), nullable=True)
    session_id = Column("sessionId", String(255), nullable=True, index=True)
    allotment_id = Column("allotmentId", String(255), nullable=True)
    minutes_used = Column("minutesUsed", Integer, nullable=True)
    capacity_used = Column("capacityUsed", Integer, nullable=True)
    license_usage = Column("licenseUsage", String(120), nullable=True)
    name = Column(String(255), nullable=True)
    display_name = Column("displayName", String(255), nullable=True)
    license_type = Column("type", String(120), nullable=True)
    excess = Column(Integer, nullable=True)
    allocated = Column(Integer, nullable=True)
    available = Column(Integer, nullable=True)
    used = Column(Integer, nullable=True)
    quarantined = Column(Integer, nullable=True)
    total = Column(Integer, nullable=True)
    source = Column(String(255), nullable=True)
    tenant = Column(String(255), nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class QlikLicenseStatus(Base):
    """Qlik license status records scoped to a project (composite PK)."""
    __tablename__ = "qlik_license_status"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'status_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    status_id = Column(String(120), nullable=False)
    license_type = Column("type", String(120), nullable=True)
    trial = Column(Boolean, nullable=True)
    valid = Column(Boolean, nullable=True)
    origin = Column(String(120), nullable=True)
    status = Column(String(120), nullable=True)
    product = Column(String(255), nullable=True)
    deactivated = Column(Boolean, nullable=True)
    source = Column(String(255), nullable=True)
    tenant = Column(String(255), nullable=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class AppDataMetadataSnapshot(Base):
    """Append-only snapshot for /api/v1/apps/{appId}/data/metadata."""
    __tablename__ = "app_data_metadata_snapshot"
    snapshot_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    app_id = Column(String(100), nullable=False, index=True)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    static_byte_size = Column(BigInteger, nullable=True)
    has_section_access = Column(Boolean, nullable=True)
    is_direct_query_mode = Column(Boolean, nullable=True)
    reload_meta_cpu_time_spent_ms = Column(BigInteger, nullable=True)
    reload_meta_peak_memory_bytes = Column(BigInteger, nullable=True)
    reload_meta_full_reload_peak_memory_bytes = Column(BigInteger, nullable=True)
    reload_meta_partial_reload_peak_memory_bytes = Column(BigInteger, nullable=True)
    reload_meta_hardware_total_memory = Column(BigInteger, nullable=True)
    reload_meta_hardware_logical_cores = Column(Integer, nullable=True)
    schema_hash = Column(String(64), nullable=False)
    extra_json = Column(JSONB, nullable=True)
    source = Column(String(255), nullable=True)
    tenant = Column(String(255), nullable=True)


class AppDataMetadataField(Base):
    __tablename__ = "app_data_metadata_fields"
    __table_args__ = (UniqueConstraint("snapshot_id", "field_hash"),)
    row_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(BigInteger, ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False, index=True)
    field_hash = Column(String(120), nullable=False)
    name = Column(String(255), nullable=True)
    comment = Column(Text, nullable=True)
    cardinal = Column(BigInteger, nullable=True)
    byte_size = Column(BigInteger, nullable=True)
    is_hidden = Column(Boolean, nullable=True)
    is_locked = Column(Boolean, nullable=True)
    is_system = Column(Boolean, nullable=True)
    is_numeric = Column(Boolean, nullable=True)
    is_semantic = Column(Boolean, nullable=True)
    total_count = Column(BigInteger, nullable=True)
    distinct_only = Column(Boolean, nullable=True)
    always_one_selected = Column(Boolean, nullable=True)
    tags = Column(ARRAY(Text), nullable=True)
    src_tables = Column(ARRAY(Text), nullable=True)
    extra_json = Column(JSONB, nullable=True)


class AppDataMetadataTable(Base):
    __tablename__ = "app_data_metadata_tables"
    __table_args__ = (UniqueConstraint("snapshot_id", "name"),)
    row_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(BigInteger, ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    comment = Column(Text, nullable=True)
    is_loose = Column(Boolean, nullable=True)
    byte_size = Column(BigInteger, nullable=True)
    is_system = Column(Boolean, nullable=True)
    is_semantic = Column(Boolean, nullable=True)
    no_of_rows = Column(BigInteger, nullable=True)
    no_of_fields = Column(Integer, nullable=True)
    no_of_key_fields = Column(Integer, nullable=True)
    extra_json = Column(JSONB, nullable=True)


class AppDataMetadataTableProfile(Base):
    __tablename__ = "table_profiles"
    __table_args__ = (UniqueConstraint("snapshot_id", "profile_index"),)
    table_profile_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(BigInteger, ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False, index=True)
    profile_index = Column(Integer, nullable=False)
    no_of_rows = Column(BigInteger, nullable=True)
    extra_json = Column(JSONB, nullable=True)


class AppDataMetadataFieldProfile(Base):
    __tablename__ = "field_profiles"
    __table_args__ = (UniqueConstraint("table_profile_id", "profile_index"),)
    field_profile_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(BigInteger, ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False, index=True)
    table_profile_id = Column(BigInteger, ForeignKey("table_profiles.table_profile_id", ondelete="CASCADE"), nullable=False, index=True)
    profile_index = Column(Integer, nullable=False)
    name = Column(String(255), nullable=True)
    max_value = Column(Float, nullable=True)
    min_value = Column(Float, nullable=True)
    std_value = Column(Float, nullable=True)
    sum_value = Column(Float, nullable=True)
    sum2_value = Column(Float, nullable=True)
    median_value = Column(Float, nullable=True)
    average_value = Column(Float, nullable=True)
    kurtosis = Column(Float, nullable=True)
    skewness = Column(Float, nullable=True)
    field_tags = Column(ARRAY(Text), nullable=True)
    fractiles = Column(JSONB, nullable=True)
    neg_values = Column(BigInteger, nullable=True)
    pos_values = Column(BigInteger, nullable=True)
    last_sorted = Column(Text, nullable=True)
    null_values = Column(BigInteger, nullable=True)
    text_values = Column(BigInteger, nullable=True)
    zero_values = Column(BigInteger, nullable=True)
    first_sorted = Column(Text, nullable=True)
    avg_string_len = Column(Float, nullable=True)
    data_evenness = Column(Float, nullable=True)
    empty_strings = Column(BigInteger, nullable=True)
    max_string_len = Column(BigInteger, nullable=True)
    min_string_len = Column(BigInteger, nullable=True)
    sum_string_len = Column(BigInteger, nullable=True)
    numeric_values = Column(BigInteger, nullable=True)
    distinct_values = Column(BigInteger, nullable=True)
    distinct_text_values = Column(BigInteger, nullable=True)
    distinct_numeric_values = Column(BigInteger, nullable=True)
    number_format_dec = Column(String(32), nullable=True)
    number_format_fmt = Column(String(120), nullable=True)
    number_format_thou = Column(String(32), nullable=True)
    number_format_ndec = Column(Integer, nullable=True)
    number_format_use_thou = Column(Integer, nullable=True)
    extra_json = Column(JSONB, nullable=True)


class AppDataMetadataFieldMostFrequent(Base):
    __tablename__ = "field_most_frequent"
    __table_args__ = (UniqueConstraint("field_profile_id", "rank"),)
    row_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(BigInteger, ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False, index=True)
    field_profile_id = Column(BigInteger, ForeignKey("field_profiles.field_profile_id", ondelete="CASCADE"), nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    symbol_text = Column(Text, nullable=True)
    symbol_number = Column(Float, nullable=True)
    frequency = Column(BigInteger, nullable=True)
    extra_json = Column(JSONB, nullable=True)


class AppDataMetadataFieldFrequencyDistribution(Base):
    __tablename__ = "field_frequency_distribution"
    __table_args__ = (UniqueConstraint("field_profile_id", "bin_index"),)
    row_id = Column(BigInteger, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    snapshot_id = Column(BigInteger, ForeignKey("app_data_metadata_snapshot.snapshot_id", ondelete="CASCADE"), nullable=False, index=True)
    field_profile_id = Column(BigInteger, ForeignKey("field_profiles.field_profile_id", ondelete="CASCADE"), nullable=False, index=True)
    bin_index = Column(Integer, nullable=False)
    bin_edge = Column(Float, nullable=True)
    frequency = Column(BigInteger, nullable=True)
    number_of_bins = Column(Integer, nullable=True)
    extra_json = Column(JSONB, nullable=True)


class LineageNode(Base):
    """Lineage graph node scoped to a project (composite PK)."""
    __tablename__ = "lineage_nodes"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'node_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    node_id = Column(Text, nullable=False)
    app_id = Column(String(100), index=True)
    node_type = Column(String(50), index=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())


class LineageEdge(Base):
    """Lineage graph edge scoped to a project (composite PK)."""
    __tablename__ = "lineage_edges"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'edge_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    edge_id = Column(Text, nullable=False)
    app_id = Column(String(100), index=True)
    source_node_id = Column(Text, index=True)
    target_node_id = Column(Text, index=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
