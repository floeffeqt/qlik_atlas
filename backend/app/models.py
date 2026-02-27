from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Text, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB
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


class QlikApp(Base):
    """Qlik app metadata scoped to a project (composite PK)."""
    __tablename__ = "qlik_apps"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'app_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    app_id = Column(String(100), nullable=False)
    space_id = Column(String(100), index=True)
    name_value = Column("name", String(255), nullable=True)
    app_id_payload = Column("appId", String(100), nullable=True)
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
