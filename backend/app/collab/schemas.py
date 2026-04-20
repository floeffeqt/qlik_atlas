"""Pydantic schemas for project-collaboration endpoints."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, Field


# ── Shared refs ──────────────────────────────────────────────────────

class UserRef(BaseModel):
    id: int
    email: str
    display_name: Optional[str] = None


# ── Tags ─────────────────────────────────────────────────────────────

class TagIn(BaseModel):
    customer_id: int
    name: str = Field(..., min_length=1, max_length=50)
    color: str = Field(default="#888780", max_length=7)


class TagUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=50)
    color: Optional[str] = Field(default=None, max_length=7)


class TagOut(BaseModel):
    id: int
    customer_id: int
    name: str
    color: str
    created_at: str


# ── Task-Tags ────────────────────────────────────────────────────────

class TaskTagIn(BaseModel):
    task_id: int
    tag_id: int


# ── Tasks ────────────────────────────────────────────────────────────

class TaskIn(BaseModel):
    project_id: int
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = "open"
    priority: str = "medium"
    assignee_id: Optional[int] = None
    start_date: Optional[date] = None
    start_time: Optional[time] = None
    due_date: Optional[date] = None
    end_time: Optional[time] = None
    estimated_minutes: Optional[int] = None
    qlik_app_id: Optional[str] = None
    app_link: Optional[str] = None
    parent_task_id: Optional[int] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[int] = None
    start_date: Optional[date] = None
    start_time: Optional[time] = None
    due_date: Optional[date] = None
    end_time: Optional[time] = None
    estimated_minutes: Optional[int] = None
    qlik_app_id: Optional[str] = None
    app_link: Optional[str] = None
    parent_task_id: Optional[int] = None


class TaskOut(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    customer_name: Optional[str] = None
    qlik_app_id: Optional[str]
    parent_task_id: Optional[int]
    title: str
    description: Optional[str]
    status: str
    priority: str
    assignee_id: Optional[int]
    assignee: Optional[UserRef] = None
    start_date: Optional[str]
    start_time: Optional[str]
    due_date: Optional[str]
    end_time: Optional[str]
    estimated_minutes: Optional[int]
    app_link: Optional[str]
    tags: list[TagOut] = []
    subtasks: list[TaskOut] = []
    created_at: str
    updated_at: str


# ── Log entries ──────────────────────────────────────────────────────

class LogEntryIn(BaseModel):
    project_id: int
    entry_type: str = Field(..., min_length=1, max_length=50)
    content: str = ""          # "was" — what happened / was decided
    warum: Optional[str] = None    # why / reasoning
    betrifft: Optional[str] = None # affected apps / areas (free text)
    qlik_app_id: Optional[str] = None
    entry_date: Optional[date] = None


class LogEntryOut(BaseModel):
    id: int
    project_id: int
    project_name: Optional[str] = None
    customer_name: Optional[str] = None
    qlik_app_id: Optional[str]
    author_id: Optional[int]
    author: Optional[UserRef] = None
    entry_type: str
    content: str               # "was"
    warum: Optional[str] = None
    betrifft: Optional[str] = None
    entry_date: Optional[str]
    created_at: str


# ── Node comments ────────────────────────────────────────────────────

class NodeCommentIn(BaseModel):
    project_id: int
    lineage_node_id: str
    comment_type: str = "technical"
    content: str = Field(..., min_length=1)
    assignee_id: Optional[int] = None


class NodeCommentOut(BaseModel):
    id: int
    project_id: int
    lineage_node_id: Optional[str]
    author_id: Optional[int]
    author: Optional[UserRef] = None
    assignee_id: Optional[int]
    assignee: Optional[UserRef] = None
    comment_type: str
    content: str
    created_at: str


class NodeCommentCountOut(BaseModel):
    lineage_node_id: str
    total: int = 0
    technical: int = 0
    business: int = 0
    issue: int = 0


# ── Readmes ──────────────────────────────────────────────────────────

class ReadmeIn(BaseModel):
    project_id: int
    readme_type: str = "app_readme"
    qlik_app_id: Optional[str] = None
    content: str = ""


class ReadmeUpdate(BaseModel):
    content: str


class ReadmeOut(BaseModel):
    id: int
    project_id: int
    qlik_app_id: Optional[str]
    readme_type: str
    content: str
    updated_at: str


# ── Templates ────────────────────────────────────────────────────────

class TemplateOut(BaseModel):
    id: int
    template_type: str
    name: str
    body: str
    required_fields: list = []
    is_default: bool


# ── Dashboard metrics ────────────────────────────────────────────────

class DashboardMetrics(BaseModel):
    open_tasks: int = 0
    due_this_week: int = 0
    in_progress: int = 0
    in_progress_assignees: int = 0
    log_entries: int = 0
    log_entries_this_week: int = 0
    apps_without_readme: int = 0
    total_apps: int = 0


# ── Apps without README ──────────────────────────────────────────────

class AppHealthItem(BaseModel):
    app_id: str
    name: str
    project_id: int
    project_name: Optional[str] = None
    customer_name: Optional[str] = None
    has_readme: bool = False
    open_tasks: int = 0
    done_tasks: int = 0
    last_log: Optional[str] = None
    last_log_type: Optional[str] = None


class AppWithoutReadme(BaseModel):
    app_id: str
    name: str
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    customer_name: Optional[str] = None
    created_at: Optional[str] = None
