"""Routes for project-collaboration features (tasks, tags, docs, readmes,
node-comments, templates, dashboard metrics)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, delete, distinct, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database import get_session, apply_rls_context
from ..models import (
    AppReadme,
    Customer,
    DocEntry,
    DocTemplate,
    NodeComment,
    Project,
    QlikApp,
    Tag,
    Task,
    TaskTag,
    User,
)
from ..auth.utils import get_current_user
from ..serialization import iso_or_empty
from .schemas import (
    AppHealthItem,
    AppWithoutReadme,
    DashboardMetrics,
    LogEntryIn,
    LogEntryOut,
    NodeCommentCountOut,
    NodeCommentIn,
    NodeCommentOut,
    ReadmeIn,
    ReadmeOut,
    ReadmeUpdate,
    TagIn,
    TagOut,
    TagUpdate,
    TaskIn,
    TaskOut,
    TaskTagIn,
    TaskUpdate,
    TemplateOut,
    UserRef,
)

router = APIRouter(tags=["collaboration"])


# ── Dependency: RLS-scoped session ───────────────────────────────────

async def _scoped(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> AsyncSession:
    await apply_rls_context(session, current_user["user_id"], current_user.get("role", "user"))
    return session


def _user_id(current_user: dict) -> int:
    return int(current_user["user_id"])


# ── Helpers ──────────────────────────────────────────────────────────

def _user_ref(user: User | None) -> UserRef | None:
    if not user:
        return None
    return UserRef(id=user.id, email=user.email, display_name=user.email.split("@")[0])


async def _load_user(session: AsyncSession, uid: int | None) -> User | None:
    if uid is None:
        return None
    r = await session.execute(select(User).where(User.id == uid))
    return r.scalar_one_or_none()


def _tag_out(t: Tag) -> TagOut:
    return TagOut(id=t.id, customer_id=t.customer_id, name=t.name, color=t.color, created_at=iso_or_empty(t.created_at))


async def _project_context(session: AsyncSession, project_id: int) -> tuple[str | None, str | None]:
    """Return (project_name, customer_name) for a given project_id."""
    r = await session.execute(
        select(Project.name, Customer.name)
        .join(Customer, Customer.id == Project.customer_id)
        .where(Project.id == project_id)
    )
    row = r.one_or_none()
    if row:
        return row[0], row[1]
    return None, None


async def _task_out(t: Task, session: AsyncSession, *, include_context: bool = False) -> TaskOut:
    assignee = await _load_user(session, t.assignee_id)
    tags = []
    tag_q = await session.execute(
        select(Tag).join(TaskTag, TaskTag.tag_id == Tag.id).where(TaskTag.task_id == t.id)
    )
    for tag in tag_q.scalars():
        tags.append(_tag_out(tag))

    subtasks = []
    sub_q = await session.execute(select(Task).where(Task.parent_task_id == t.id).order_by(Task.created_at))
    for s in sub_q.scalars():
        subtasks.append(TaskOut(
            id=s.id, project_id=s.project_id, qlik_app_id=s.qlik_app_id,
            parent_task_id=s.parent_task_id, title=s.title, description=s.description,
            status=s.status, priority=s.priority, assignee_id=s.assignee_id,
            start_date=iso_or_empty(s.start_date), start_time=s.start_time.strftime('%H:%M') if s.start_time else None,
            due_date=iso_or_empty(s.due_date),   end_time=s.end_time.strftime('%H:%M')   if s.end_time   else None,
            estimated_minutes=s.estimated_minutes,
            app_link=s.app_link, created_at=iso_or_empty(s.created_at),
            updated_at=iso_or_empty(s.updated_at),
        ))

    pname, cname = (None, None)
    if include_context:
        pname, cname = await _project_context(session, t.project_id)

    return TaskOut(
        id=t.id, project_id=t.project_id, project_name=pname, customer_name=cname,
        qlik_app_id=t.qlik_app_id,
        parent_task_id=t.parent_task_id, title=t.title, description=t.description,
        status=t.status, priority=t.priority, assignee_id=t.assignee_id,
        assignee=_user_ref(assignee),
        start_date=iso_or_empty(t.start_date), start_time=t.start_time.strftime('%H:%M') if t.start_time else None,
        due_date=iso_or_empty(t.due_date),     end_time=t.end_time.strftime('%H:%M')   if t.end_time   else None,
        estimated_minutes=t.estimated_minutes,
        app_link=t.app_link, tags=tags, subtasks=subtasks,
        created_at=iso_or_empty(t.created_at), updated_at=iso_or_empty(t.updated_at),
    )


# =====================================================================
#  TAGS
# =====================================================================

@router.get("/tags", response_model=list[TagOut])
async def list_tags(
    customer_id: int = Query(...),
    session: AsyncSession = Depends(_scoped),
):
    q = await session.execute(select(Tag).where(Tag.customer_id == customer_id).order_by(Tag.name))
    return [_tag_out(t) for t in q.scalars()]


@router.post("/tags", response_model=TagOut, status_code=status.HTTP_201_CREATED)
async def create_tag(
    payload: TagIn,
    session: AsyncSession = Depends(_scoped),
    current_user: dict = Depends(get_current_user),
):
    tag = Tag(customer_id=payload.customer_id, name=payload.name.strip(),
              color=payload.color, created_by=_user_id(current_user))
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return _tag_out(tag)


@router.put("/tags/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: int,
    payload: TagUpdate,
    session: AsyncSession = Depends(_scoped),
):
    r = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = r.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="tag not found")
    if payload.name is not None:
        tag.name = payload.name.strip()
    if payload.color is not None:
        tag.color = payload.color
    await session.commit()
    await session.refresh(tag)
    return _tag_out(tag)


@router.delete("/tags/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tag(tag_id: int, session: AsyncSession = Depends(_scoped)):
    r = await session.execute(select(Tag).where(Tag.id == tag_id))
    tag = r.scalar_one_or_none()
    if not tag:
        raise HTTPException(status_code=404, detail="tag not found")
    await session.delete(tag)
    await session.commit()


# =====================================================================
#  TASKS
# =====================================================================

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    project_id: int | None = Query(default=None),
    customer_id: int | None = Query(default=None),
    qlik_app_id: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    tag: int | None = Query(default=None),
    session: AsyncSession = Depends(_scoped),
    current_user: dict = Depends(get_current_user),
):
    q = select(Task)
    if project_id is not None:
        q = q.where(Task.project_id == project_id)
    if customer_id is not None:
        q = q.join(Project, Task.project_id == Project.id).where(Project.customer_id == customer_id)
    if qlik_app_id:
        q = q.where(Task.qlik_app_id == qlik_app_id)
    if assignee == "me":
        q = q.where(Task.assignee_id == _user_id(current_user))
    if status_filter:
        q = q.where(Task.status == status_filter)
    if priority:
        q = q.where(Task.priority == priority)
    if tag:
        q = q.join(TaskTag, TaskTag.task_id == Task.id).where(TaskTag.tag_id == tag)
    q = q.order_by(
        case(PRIORITY_ORDER, value=Task.priority, else_=9),
        Task.due_date.asc().nulls_last(),
        Task.created_at.desc(),
    )
    result = await session.execute(q)
    tasks = list(result.scalars())
    include_ctx = project_id is None
    return [await _task_out(t, session, include_context=include_ctx) for t in tasks]


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: int, session: AsyncSession = Depends(_scoped)):
    r = await session.execute(select(Task).where(Task.id == task_id))
    task = r.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    return await _task_out(task, session)


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskIn,
    session: AsyncSession = Depends(_scoped),
):
    task = Task(
        project_id=payload.project_id, title=payload.title.strip(),
        description=payload.description, status=payload.status,
        priority=payload.priority, assignee_id=payload.assignee_id,
        start_date=payload.start_date, start_time=payload.start_time,
        due_date=payload.due_date,     end_time=payload.end_time,
        estimated_minutes=payload.estimated_minutes,
        qlik_app_id=payload.qlik_app_id, app_link=payload.app_link,
        parent_task_id=payload.parent_task_id,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return await _task_out(task, session)


@router.put("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    session: AsyncSession = Depends(_scoped),
):
    r = await session.execute(select(Task).where(Task.id == task_id))
    task = r.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="task not found")
    for field in ("title", "description", "status", "priority", "assignee_id",
                  "start_date", "start_time", "due_date", "end_time",
                  "estimated_minutes", "qlik_app_id", "app_link", "parent_task_id"):
        val = getattr(payload, field)
        if val is not None:
            setattr(task, field, val.strip() if isinstance(val, str) else val)
    await session.commit()
    await session.refresh(task)
    return await _task_out(task, session)


# ── Task-Tags ────────────────────────────────────────────────────────

@router.post("/task-tags", status_code=status.HTTP_201_CREATED)
async def link_task_tag(payload: TaskTagIn, session: AsyncSession = Depends(_scoped)):
    tt = TaskTag(task_id=payload.task_id, tag_id=payload.tag_id)
    session.add(tt)
    await session.commit()
    return {"ok": True}


@router.delete("/task-tags/{task_id}/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_task_tag(task_id: int, tag_id: int, session: AsyncSession = Depends(_scoped)):
    await session.execute(delete(TaskTag).where(TaskTag.task_id == task_id, TaskTag.tag_id == tag_id))
    await session.commit()


# =====================================================================
#  LOG ENTRIES
# =====================================================================

def _log_entry_out(d: DocEntry, author: User | None, *, project_name: str | None = None, customer_name: str | None = None) -> LogEntryOut:
    return LogEntryOut(
        id=d.id, project_id=d.project_id, project_name=project_name, customer_name=customer_name,
        qlik_app_id=d.qlik_app_id,
        author_id=d.author_id, author=_user_ref(author),
        entry_type=d.entry_type, content=d.content,
        warum=d.warum, betrifft=d.betrifft,
        entry_date=iso_or_empty(d.entry_date), created_at=iso_or_empty(d.created_at),
    )


@router.get("/log-entries", response_model=list[LogEntryOut])
async def list_log_entries(
    project_id: int | None = Query(default=None),
    qlik_app_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(_scoped),
):
    q = select(DocEntry)
    if project_id is not None:
        q = q.where(DocEntry.project_id == project_id)
    if qlik_app_id:
        q = q.where(DocEntry.qlik_app_id == qlik_app_id)
    q = q.order_by(DocEntry.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(q)
    include_ctx = project_id is None
    out = []
    for d in result.scalars():
        author = await _load_user(session, d.author_id)
        pname, cname = (None, None)
        if include_ctx:
            pname, cname = await _project_context(session, d.project_id)
        out.append(_log_entry_out(d, author, project_name=pname, customer_name=cname))
    return out


@router.get("/log-entries/{entry_id}", response_model=LogEntryOut)
async def get_log_entry(entry_id: int, session: AsyncSession = Depends(_scoped)):
    r = await session.execute(select(DocEntry).where(DocEntry.id == entry_id))
    d = r.scalar_one_or_none()
    if not d:
        raise HTTPException(status_code=404, detail="log entry not found")
    author = await _load_user(session, d.author_id)
    return _log_entry_out(d, author)


@router.post("/log-entries", response_model=LogEntryOut, status_code=status.HTTP_201_CREATED)
async def create_log_entry(
    payload: LogEntryIn,
    session: AsyncSession = Depends(_scoped),
    current_user: dict = Depends(get_current_user),
):
    entry = DocEntry(
        project_id=payload.project_id, entry_type=payload.entry_type,
        content=payload.content, warum=payload.warum, betrifft=payload.betrifft,
        qlik_app_id=payload.qlik_app_id,
        entry_date=payload.entry_date or date.today(),
        author_id=_user_id(current_user),
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    author = await _load_user(session, entry.author_id)
    return _log_entry_out(entry, author)


# =====================================================================
#  NODE COMMENTS
# =====================================================================

@router.get("/node-comments", response_model=list[NodeCommentOut])
async def list_node_comments(
    lineage_node_id: str = Query(...),
    comment_type: str | None = Query(default=None),
    session: AsyncSession = Depends(_scoped),
):
    q = select(NodeComment).where(NodeComment.lineage_node_id == lineage_node_id)
    if comment_type:
        q = q.where(NodeComment.comment_type == comment_type)
    q = q.order_by(NodeComment.created_at.desc())
    result = await session.execute(q)
    out = []
    for c in result.scalars():
        author = await _load_user(session, c.author_id)
        assignee = await _load_user(session, c.assignee_id)
        out.append(NodeCommentOut(
            id=c.id, project_id=c.project_id, lineage_node_id=c.lineage_node_id,
            author_id=c.author_id, author=_user_ref(author),
            assignee_id=c.assignee_id, assignee=_user_ref(assignee),
            comment_type=c.comment_type, content=c.content,
            created_at=iso_or_empty(c.created_at),
        ))
    return out


@router.get("/node-comments/counts", response_model=list[NodeCommentCountOut])
async def node_comment_counts(
    project_id: int = Query(...),
    session: AsyncSession = Depends(_scoped),
):
    q = (
        select(
            NodeComment.lineage_node_id,
            func.count().label("total"),
            func.count().filter(NodeComment.comment_type == "technical").label("technical"),
            func.count().filter(NodeComment.comment_type == "business").label("business"),
            func.count().filter(NodeComment.comment_type == "issue").label("issue"),
        )
        .where(NodeComment.project_id == project_id)
        .where(NodeComment.lineage_node_id.is_not(None))
        .group_by(NodeComment.lineage_node_id)
    )
    result = await session.execute(q)
    return [
        NodeCommentCountOut(lineage_node_id=row.lineage_node_id, total=row.total,
                            technical=row.technical, business=row.business, issue=row.issue)
        for row in result
    ]


@router.post("/node-comments", response_model=NodeCommentOut, status_code=status.HTTP_201_CREATED)
async def create_node_comment(
    payload: NodeCommentIn,
    session: AsyncSession = Depends(_scoped),
    current_user: dict = Depends(get_current_user),
):
    comment = NodeComment(
        project_id=payload.project_id, lineage_node_id=payload.lineage_node_id,
        comment_type=payload.comment_type, content=payload.content,
        assignee_id=payload.assignee_id, author_id=_user_id(current_user),
    )
    session.add(comment)
    await session.commit()
    await session.refresh(comment)
    author = await _load_user(session, comment.author_id)
    assignee = await _load_user(session, comment.assignee_id)
    return NodeCommentOut(
        id=comment.id, project_id=comment.project_id, lineage_node_id=comment.lineage_node_id,
        author_id=comment.author_id, author=_user_ref(author),
        assignee_id=comment.assignee_id, assignee=_user_ref(assignee),
        comment_type=comment.comment_type, content=comment.content,
        created_at=iso_or_empty(comment.created_at),
    )


# =====================================================================
#  READMES
# =====================================================================

@router.get("/readmes", response_model=list[ReadmeOut])
async def list_readmes(
    project_id: int = Query(...),
    qlik_app_id: str | None = Query(default=None),
    readme_type: str | None = Query(default=None),
    session: AsyncSession = Depends(_scoped),
):
    q = select(AppReadme).where(AppReadme.project_id == project_id)
    if qlik_app_id:
        q = q.where(AppReadme.qlik_app_id == qlik_app_id)
    if readme_type:
        q = q.where(AppReadme.readme_type == readme_type)
    result = await session.execute(q)
    return [
        ReadmeOut(id=r.id, project_id=r.project_id, qlik_app_id=r.qlik_app_id,
                  readme_type=r.readme_type, content=r.content_md or "",
                  updated_at=iso_or_empty(r.updated_at))
        for r in result.scalars()
    ]


@router.post("/readmes", response_model=ReadmeOut, status_code=status.HTTP_201_CREATED)
async def create_readme(
    payload: ReadmeIn,
    session: AsyncSession = Depends(_scoped),
    current_user: dict = Depends(get_current_user),
):
    readme = AppReadme(
        project_id=payload.project_id, qlik_app_id=payload.qlik_app_id,
        readme_type=payload.readme_type, content_md=payload.content,
        last_edited_by=_user_id(current_user),
    )
    session.add(readme)
    await session.commit()
    await session.refresh(readme)
    return ReadmeOut(id=readme.id, project_id=readme.project_id, qlik_app_id=readme.qlik_app_id,
                     readme_type=readme.readme_type, content=readme.content_md or "",
                     updated_at=iso_or_empty(readme.updated_at))


@router.put("/readmes/{readme_id}", response_model=ReadmeOut)
async def update_readme(
    readme_id: int,
    payload: ReadmeUpdate,
    session: AsyncSession = Depends(_scoped),
    current_user: dict = Depends(get_current_user),
):
    r = await session.execute(select(AppReadme).where(AppReadme.id == readme_id))
    readme = r.scalar_one_or_none()
    if not readme:
        raise HTTPException(status_code=404, detail="readme not found")
    readme.content_md = payload.content
    readme.last_edited_by = _user_id(current_user)
    await session.commit()
    await session.refresh(readme)
    return ReadmeOut(id=readme.id, project_id=readme.project_id, qlik_app_id=readme.qlik_app_id,
                     readme_type=readme.readme_type, content=readme.content_md or "",
                     updated_at=iso_or_empty(readme.updated_at))


# =====================================================================
#  TEMPLATES
# =====================================================================

@router.get("/templates", response_model=TemplateOut | None)
async def get_template(
    type: str = Query(...),
    project_id: int | None = Query(default=None),
    session: AsyncSession = Depends(_scoped),
):
    """Return the best-matching template for the given type.

    Priority: project-specific override > global default.
    """
    q = select(DocTemplate).where(DocTemplate.template_type == type)
    result = await session.execute(q.order_by(DocTemplate.project_id.desc().nulls_last()))
    templates = list(result.scalars())
    # Prefer project-specific
    if project_id:
        for t in templates:
            if t.project_id == project_id:
                return TemplateOut(id=t.id, template_type=t.template_type, name=t.name,
                                   body=t.content_md, required_fields=t.required_fields or [],
                                   is_default=t.is_default)
    # Fall back to global default
    for t in templates:
        if t.project_id is None:
            return TemplateOut(id=t.id, template_type=t.template_type, name=t.name,
                               body=t.content_md, required_fields=t.required_fields or [],
                               is_default=t.is_default)
    return None


# =====================================================================
#  DASHBOARD METRICS
# =====================================================================

@router.get("/dashboard/metrics", response_model=DashboardMetrics)
async def dashboard_metrics(
    project_id: int | None = Query(default=None),
    session: AsyncSession = Depends(_scoped),
):
    now = datetime.now(timezone.utc)
    week_end = now + timedelta(days=(6 - now.weekday()))
    week_start = now - timedelta(days=now.weekday())

    pf_task = (Task.project_id == project_id) if project_id else True
    pf_doc = (DocEntry.project_id == project_id) if project_id else True
    pf_app = (QlikApp.project_id == project_id) if project_id else True
    pf_readme = (AppReadme.project_id == project_id) if project_id else True

    open_q = await session.execute(
        select(func.count()).select_from(Task).where(
            pf_task, Task.status.in_(["open", "in_progress", "review"])
        )
    )
    open_tasks = open_q.scalar() or 0

    due_q = await session.execute(
        select(func.count()).select_from(Task).where(
            pf_task,
            Task.status.in_(["open", "in_progress", "review"]),
            Task.due_date <= week_end.date(),
        )
    )
    due_this_week = due_q.scalar() or 0

    ip_q = await session.execute(
        select(func.count()).select_from(Task).where(
            pf_task, Task.status == "in_progress"
        )
    )
    in_progress = ip_q.scalar() or 0

    ip_a_q = await session.execute(
        select(func.count(distinct(Task.assignee_id))).select_from(Task).where(
            pf_task, Task.status == "in_progress",
            Task.assignee_id.is_not(None),
        )
    )
    in_progress_assignees = ip_a_q.scalar() or 0

    de_q = await session.execute(
        select(func.count()).select_from(DocEntry).where(pf_doc)
    )
    log_entries = de_q.scalar() or 0

    dew_q = await session.execute(
        select(func.count()).select_from(DocEntry).where(
            pf_doc,
            DocEntry.created_at >= week_start,
        )
    )
    log_entries_this_week = dew_q.scalar() or 0

    apps_q = await session.execute(
        select(func.count()).select_from(QlikApp).where(pf_app)
    )
    total_apps = apps_q.scalar() or 0

    readme_apps_q = await session.execute(
        select(func.count(distinct(AppReadme.qlik_app_id))).select_from(AppReadme).where(
            pf_readme,
            AppReadme.readme_type == "app_readme",
            AppReadme.qlik_app_id.is_not(None),
        )
    )
    apps_with_readme = readme_apps_q.scalar() or 0
    apps_without = max(0, total_apps - apps_with_readme)

    return DashboardMetrics(
        open_tasks=open_tasks, due_this_week=due_this_week,
        in_progress=in_progress, in_progress_assignees=in_progress_assignees,
        log_entries=log_entries, log_entries_this_week=log_entries_this_week,
        apps_without_readme=apps_without, total_apps=total_apps,
    )


# =====================================================================
#  APPS WITHOUT README
# =====================================================================

@router.get("/apps/without-readme", response_model=list[AppWithoutReadme])
async def apps_without_readme(
    project_id: int | None = Query(default=None),
    session: AsyncSession = Depends(_scoped),
):
    apps_sel = select(QlikApp.app_id, QlikApp.name_value, QlikApp.app_name, QlikApp.fetched_at, QlikApp.project_id)
    readme_sel = select(AppReadme.qlik_app_id, AppReadme.project_id).where(
        AppReadme.readme_type == "app_readme",
        AppReadme.qlik_app_id.is_not(None),
    )
    if project_id is not None:
        apps_sel = apps_sel.where(QlikApp.project_id == project_id)
        readme_sel = readme_sel.where(AppReadme.project_id == project_id)

    apps_q = await session.execute(apps_sel)
    all_apps = list(apps_q)

    readme_q = await session.execute(readme_sel)
    has_readme = {(r[0], r[1]) for r in readme_q}

    include_ctx = project_id is None
    out = []
    _ctx_cache: dict[int, tuple] = {}
    for a in all_apps:
        if (a.app_id, a.project_id) in has_readme:
            continue
        pname, cname = None, None
        if include_ctx:
            if a.project_id not in _ctx_cache:
                _ctx_cache[a.project_id] = await _project_context(session, a.project_id)
            pname, cname = _ctx_cache[a.project_id]
        out.append(AppWithoutReadme(
            app_id=a.app_id,
            name=a.name_value or a.app_name or a.app_id,
            project_id=a.project_id, project_name=pname, customer_name=cname,
            created_at=iso_or_empty(a.fetched_at),
        ))
    return out


# =====================================================================
#  APP HEALTH (aggregated per app)
# =====================================================================

@router.get("/apps/health", response_model=list[AppHealthItem])
async def apps_health(
    project_id: int | None = Query(default=None),
    session: AsyncSession = Depends(_scoped),
):
    """Per-app health overview: README status, open/done tasks, last log entry."""
    apps_sel = select(
        QlikApp.app_id, QlikApp.name_value, QlikApp.app_name, QlikApp.project_id
    )
    if project_id is not None:
        apps_sel = apps_sel.where(QlikApp.project_id == project_id)
    apps_q = await session.execute(apps_sel.order_by(QlikApp.name_value))
    all_apps = list(apps_q)
    if not all_apps:
        return []

    app_keys = [(a.app_id, a.project_id) for a in all_apps]

    # READMEs
    readme_q = await session.execute(
        select(AppReadme.qlik_app_id, AppReadme.project_id).where(
            AppReadme.readme_type == "app_readme",
            AppReadme.qlik_app_id.is_not(None),
        )
    )
    has_readme = {(r[0], r[1]) for r in readme_q}

    # Task counts per app (open vs done)
    open_q = await session.execute(
        select(Task.qlik_app_id, Task.project_id, func.count()).select_from(Task)
        .where(Task.qlik_app_id.is_not(None), Task.status.in_(["open", "in_progress", "review"]))
        .group_by(Task.qlik_app_id, Task.project_id)
    )
    open_tasks = {(r[0], r[1]): r[2] for r in open_q}

    done_q = await session.execute(
        select(Task.qlik_app_id, Task.project_id, func.count()).select_from(Task)
        .where(Task.qlik_app_id.is_not(None), Task.status == "done")
        .group_by(Task.qlik_app_id, Task.project_id)
    )
    done_tasks = {(r[0], r[1]): r[2] for r in done_q}

    # Latest log entry per app
    from sqlalchemy import literal_column
    log_sub = (
        select(
            DocEntry.qlik_app_id,
            DocEntry.project_id,
            DocEntry.created_at,
            DocEntry.entry_type,
            func.row_number().over(
                partition_by=[DocEntry.qlik_app_id, DocEntry.project_id],
                order_by=DocEntry.created_at.desc(),
            ).label("rn"),
        )
        .where(DocEntry.qlik_app_id.is_not(None))
        .subquery()
    )
    log_q = await session.execute(
        select(log_sub.c.qlik_app_id, log_sub.c.project_id, log_sub.c.created_at, log_sub.c.entry_type)
        .where(log_sub.c.rn == 1)
    )
    last_logs: dict[tuple, tuple] = {}
    for r in log_q:
        last_logs[(r[0], r[1])] = (iso_or_empty(r[2]), r[3])

    include_ctx = project_id is None
    _ctx_cache: dict[int, tuple] = {}
    out = []
    for a in all_apps:
        key = (a.app_id, a.project_id)
        pname, cname = None, None
        if include_ctx:
            if a.project_id not in _ctx_cache:
                _ctx_cache[a.project_id] = await _project_context(session, a.project_id)
            pname, cname = _ctx_cache[a.project_id]
        ll = last_logs.get(key)
        out.append(AppHealthItem(
            app_id=a.app_id,
            name=a.name_value or a.app_name or a.app_id,
            project_id=a.project_id,
            project_name=pname,
            customer_name=cname,
            has_readme=key in has_readme,
            open_tasks=open_tasks.get(key, 0),
            done_tasks=done_tasks.get(key, 0),
            last_log=ll[0] if ll else None,
            last_log_type=ll[1] if ll else None,
        ))
    return out


# =====================================================================
#  QLIK APPS LOOKUP (for dropdowns)
# =====================================================================

@router.get("/qlik-apps")
async def list_qlik_apps(
    project_id: int = Query(...),
    limit: int = Query(default=500, ge=1, le=2000),
    session: AsyncSession = Depends(_scoped),
):
    q = await session.execute(
        select(QlikApp).where(QlikApp.project_id == project_id).order_by(QlikApp.name_value).limit(limit)
    )
    return [
        {"app_id": a.app_id, "name": a.name_value or a.app_name or a.app_id, "project_id": a.project_id}
        for a in q.scalars()
    ]


@router.get("/qlik-apps/{app_id}")
async def get_qlik_app(
    app_id: str,
    project_id: int = Query(...),
    session: AsyncSession = Depends(_scoped),
):
    q = await session.execute(
        select(QlikApp).where(QlikApp.project_id == project_id, QlikApp.app_id == app_id)
    )
    app = q.scalar_one_or_none()
    if not app:
        raise HTTPException(status_code=404, detail="app not found")
    return {"app_id": app.app_id, "name": app.name_value or app.app_name or app.app_id, "project_id": app.project_id}


# =====================================================================
#  PROJECT MEMBERS (for assignee dropdowns)
# =====================================================================

@router.get("/projects/{project_id}/members")
async def project_members(
    project_id: int,
    session: AsyncSession = Depends(_scoped),
):
    """Return all active users visible to this project's customer scope."""
    r = await session.execute(select(User).where(User.is_active.is_(True)).order_by(User.email))
    return [
        {"id": u.id, "email": u.email, "display_name": u.email.split("@")[0]}
        for u in r.scalars()
    ]
