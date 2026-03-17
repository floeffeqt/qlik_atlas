from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from ..database import get_session, apply_rls_context
from ..models import Customer
from ..auth.utils import get_current_user, require_admin
from ..serialization import iso_or_empty

router = APIRouter(prefix="/customers", tags=["customers"])


async def _user_scoped_session(
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
) -> AsyncSession:
    await apply_rls_context(session, current_user["user_id"], current_user.get("role", "user"))
    return session


async def _admin_scoped_session(
    session: AsyncSession = Depends(get_session),
    admin_user: dict = Depends(require_admin),
) -> AsyncSession:
    await apply_rls_context(session, admin_user["user_id"], admin_user.get("role", "admin"))
    return session


# ── Pydantic schemas ──

class CustomerIn(BaseModel):
    name: str
    tenant_url: str
    api_key: str
    notes: Optional[str] = None
    git_provider: Optional[str] = None
    git_token: Optional[str] = None
    git_base_url: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    tenant_url: Optional[str] = None
    api_key: Optional[str] = None  # None = keep existing
    notes: Optional[str] = None
    git_provider: Optional[str] = None
    git_token: Optional[str] = None  # None = keep existing
    git_base_url: Optional[str] = None


class CustomerOut(BaseModel):
    id: int
    name: str
    tenant_url: str
    api_key_preview: str
    git_provider: Optional[str]
    git_token_preview: Optional[str]
    git_base_url: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str


class CustomerNameOut(BaseModel):
    id: int
    name: str

def _mask_key(api_key: str) -> str:
    return ("••••••••" + api_key[-4:]) if len(api_key) > 4 else "••••"


def _to_out(c: Customer) -> CustomerOut:
    git_tok = c.git_token
    return CustomerOut(
        id=c.id,
        name=c.name,
        tenant_url=c.tenant_url,
        api_key_preview=_mask_key(c.api_key),
        git_provider=c.git_provider,
        git_token_preview=_mask_key(git_tok) if git_tok else None,
        git_base_url=c.git_base_url,
        notes=c.notes,
        created_at=iso_or_empty(c.created_at),
        updated_at=iso_or_empty(c.updated_at),
    )


# ── Public route (all authenticated users) — must be before /{customer_id} ──

@router.get("/names", response_model=list[CustomerNameOut])
async def list_customer_names(
    session: AsyncSession = Depends(_user_scoped_session),
):
    """Minimal customer list for dropdowns — no credentials exposed."""
    result = await session.execute(select(Customer.id, Customer.name).order_by(Customer.name))
    return [CustomerNameOut(id=row.id, name=row.name) for row in result]


# ── Admin-only routes ──

@router.get("", response_model=list[CustomerOut])
async def list_customers(
    session: AsyncSession = Depends(_admin_scoped_session),
):
    result = await session.execute(select(Customer).order_by(Customer.name))
    return [_to_out(c) for c in result.scalars()]


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerIn,
    session: AsyncSession = Depends(_admin_scoped_session),
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
        git_provider=payload.git_provider.strip().lower() if payload.git_provider else None,
        git_base_url=payload.git_base_url.strip().rstrip("/") if payload.git_base_url else None,
    )
    if payload.git_token:
        customer.git_token = payload.git_token.strip()
    session.add(customer)
    await session.commit()
    await session.refresh(customer)
    return _to_out(customer)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: int,
    session: AsyncSession = Depends(_admin_scoped_session),
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
    session: AsyncSession = Depends(_admin_scoped_session),
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
    if payload.git_provider is not None:
        customer.git_provider = payload.git_provider.strip().lower() if payload.git_provider else None
    if payload.git_token is not None:
        if payload.git_token.strip():
            customer.git_token = payload.git_token.strip()
        else:
            customer._git_token_encrypted = None
    if payload.git_base_url is not None:
        customer.git_base_url = payload.git_base_url.strip().rstrip("/") if payload.git_base_url else None

    await session.commit()
    await session.refresh(customer)
    return _to_out(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    session: AsyncSession = Depends(_admin_scoped_session),
):
    result = await session.execute(select(Customer).where(Customer.id == customer_id))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=404, detail="customer not found")
    await session.delete(customer)
    await session.commit()
