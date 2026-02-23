from sqlalchemy import Column, Integer, String, DateTime, func, Boolean, Text, ForeignKey, PrimaryKeyConstraint
from sqlalchemy.dialects.postgresql import JSONB
from .database import Base


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
    tenant_url = Column(String(500), nullable=False)
    api_key = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Project(Base):
    """A project assigned to a customer. Lineage data is isolated per project."""
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class QlikApp(Base):
    """Qlik app metadata scoped to a project (composite PK)."""
    __tablename__ = "qlik_apps"
    __table_args__ = (PrimaryKeyConstraint('project_id', 'app_id'),)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    app_id = Column(String(100), nullable=False)
    space_id = Column(String(100), index=True)
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
    source_node_id = Column(Text, index=True)
    target_node_id = Column(Text, index=True)
    data = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
