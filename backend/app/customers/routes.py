from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from ..database import get_session
from ..models import Customer
from ..auth.utils import get_current_user_id

router = APIRouter(prefix="/customers", tags=["customers"])


# ── Pydantic schemas ──

class CustomerIn(BaseModel):
    name: str
    tenant_url: str
    api_key: str
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    tenant_url: Optional[str] = None
    api_key: Optional[str] = None  # None = keep existing
    notes: Optional[str] = None


class CustomerOut(BaseModel):
    id: int
    name: str
    tenant_url: str
    api_key_preview: str
    notes: Optional[str]
    created_at: str
    updated_at: str


def _mask_key(api_key: str) -> str:
    return ("••••••••" + api_key[-4:]) if len(api_key) > 4 else "••••"


def _to_out(c: Customer) -> CustomerOut:
    return CustomerOut(
        id=c.id,
        name=c.name,
        tenant_url=c.tenant_url,
        api_key_preview=_mask_key(c.api_key),
        notes=c.notes,
        created_at=c.created_at.isoformat() if c.created_at else "",
        updated_at=c.updated_at.isoformat() if c.updated_at else "",
    )


# ── Routes ──

@router.get("", response_model=list[CustomerOut])
async def list_customers(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    result = await session.execute(select(Customer).order_by(Customer.name))
    return [_to_out(c) for c in result.scalars()]


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerIn,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="name must not be empty")
    if not payload.tenant_url.strip():
        raise HTTPException(status_code=400, detail="tenant_url must not be empty")
    if not payload.api_key.strip():
        raise HTTPException(status_code=400, detail="api_key must not be empty")

    customer = Customer(
        name=payload.name.strip(),
        tenant_url=payload.tenant_url.strip().rstrip("/"),
        api_key=payload.api_key.strip(),
        notes=payload.notes,
    )
    session.add(customer)
    await session.commit()
    await session.refresh(customer)
    return _to_out(customer)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    result = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")
    return _to_out(customer)


@router.put("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    result = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")

    if payload.name is not None:
        if not payload.name.strip():
            raise HTTPException(status_code=400, detail="name must not be empty")
        customer.name = payload.name.strip()
    if payload.tenant_url is not None:
        if not payload.tenant_url.strip():
            raise HTTPException(status_code=400, detail="tenant_url must not be empty")
        customer.tenant_url = payload.tenant_url.strip().rstrip("/")
    if payload.api_key is not None:
        if not payload.api_key.strip():
            raise HTTPException(status_code=400, detail="api_key must not be empty")
        customer.api_key = payload.api_key.strip()
    if payload.notes is not None:
        customer.notes = payload.notes

    await session.commit()
    await session.refresh(customer)
    return _to_out(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_user_id),
):
    result = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")
    await session.delete(customer)
    await session.commit()
