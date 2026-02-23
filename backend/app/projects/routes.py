from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from ..database import get_session
from ..models import Customer, Project
from ..auth.utils import get_current_user_id

router = APIRouter(prefix="/projects", tags=["projects"])


# ── Pydantic schemas ──

class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = None
    customer_id: int


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    customer_id: Optional[int] = None


class CustomerRef(BaseModel):
    id: int
    name: str
    tenant_url: str


class ProjectOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    customer_id: int
    customer: Optional[CustomerRef]
    created_at: str
    updated_at: str


def _to_out(p: Project, customer: Optional[Customer] = None) -> ProjectOut:
    cref = CustomerRef(id=customer.id, name=customer.name, tenant_url=customer.tenant_url) if customer else None
    return ProjectOut(
        id=p.id,
        name=p.name,
        description=p.description,
        customer_id=p.customer_id,
        customer=cref,
        created_at=p.created_at.isoformat() if p.created_at else "",
        updated_at=p.updated_at.isoformat() if p.updated_at else "",
    )


async def _get_project_with_customer(
    project_id: int, session: AsyncSession
) -> tuple[Project, Customer]:
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    cust_result = await session.execute(select(Customer).where(Customer.id == project.customer_id))
    customer = cust_result.scalar_one_or_none()
    return project, customer


# ── Routes ──

@router.get("", response_model=list[ProjectOut])
async def list_projects(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    projects_result = await session.execute(select(Project).order_by(Project.name))
    projects = list(projects_result.scalars())

    # Batch-load customers
    customer_ids = list({p.customer_id for p in projects})
    customers: dict[int, Customer] = {}
    if customer_ids:
        cust_result = await session.execute(select(Customer).where(Customer.id.in_(customer_ids)))
        for c in cust_result.scalars():
            customers[c.id] = c

    return [_to_out(p, customers.get(p.customer_id)) for p in projects]


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectIn,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")

    cust_result = await session.execute(select(Customer).where(Customer.id == payload.customer_id))
    customer = cust_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")

    project = Project(
        name=payload.name.strip(),
        description=payload.description,
        customer_id=payload.customer_id,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return _to_out(project, customer)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    project, customer = await _get_project_with_customer(project_id, session)
    return _to_out(project, customer)


@router.put("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    project, _ = await _get_project_with_customer(project_id, session)

    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="name must not be empty")
        project.name = payload.name.strip()
    if payload.description is not None:
        project.description = payload.description
    if payload.customer_id is not None:
        cust_result = await session.execute(select(Customer).where(Customer.id == payload.customer_id))
        if not cust_result.scalar_one_or_none():
            raise HTTPException(status_code=404, detail="customer not found")
        project.customer_id = payload.customer_id

    await session.commit()
    project, customer = await _get_project_with_customer(project_id, session)
    return _to_out(project, customer)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    result = await session.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="project not found")
    await session.delete(project)
    await session.commit()
