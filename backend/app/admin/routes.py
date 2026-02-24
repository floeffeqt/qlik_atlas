from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func as sa_func, delete
from ..database import get_session, apply_rls_context
from ..models import User, Customer, UserCustomerAccess
from ..auth.utils import require_admin
from ..auth.schemas import UserOut, UserUpdate

router = APIRouter(prefix="/admin/users", tags=["admin"])


class CustomerAccessRef(BaseModel):
    customer_id: int
    customer_name: str


class UserCustomerAccessOut(BaseModel):
    user_id: int
    customers: list[CustomerAccessRef]


class UserCustomerAccessUpdate(BaseModel):
    customer_ids: list[int]


async def _admin_scoped_session(
    session: AsyncSession = Depends(get_session),
    admin_user: dict = Depends(require_admin),
) -> AsyncSession:
    await apply_rls_context(session, admin_user["user_id"], admin_user.get("role", "admin"))
    return session


@router.get("", response_model=list[UserOut])
async def list_users(
    session: AsyncSession = Depends(_admin_scoped_session),
):
    result = await session.execute(select(User).order_by(User.email))
    users = result.scalars().all()
    return [
        UserOut(
            id=u.id,
            email=u.email,
            role=u.role,
            is_active=u.is_active,
            created_at=u.created_at.isoformat() if u.created_at else "",
        )
        for u in users
    ]


@router.put("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    session: AsyncSession = Depends(_admin_scoped_session),
):
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent demoting the last admin
    if payload.role is not None and payload.role != "admin" and user.role == "admin":
        count_result = await session.execute(
            select(sa_func.count()).select_from(User).where(User.role == "admin", User.is_active == True)
        )
        admin_count = count_result.scalar() or 0
        if admin_count <= 1:
            raise HTTPException(status_code=400, detail="Cannot demote the last active admin")

    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    await session.commit()
    await session.refresh(user)
    return UserOut(
        id=user.id,
        email=user.email,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at.isoformat() if user.created_at else "",
    )


@router.get("/{user_id}/customer-access", response_model=UserCustomerAccessOut)
async def get_user_customer_access(
    user_id: int,
    session: AsyncSession = Depends(_admin_scoped_session),
):
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    rows_result = await session.execute(
        select(UserCustomerAccess.customer_id, Customer.name)
        .join(Customer, Customer.id == UserCustomerAccess.customer_id)
        .where(UserCustomerAccess.user_id == user_id)
        .order_by(Customer.name)
    )
    customers = [
        CustomerAccessRef(customer_id=row.customer_id, customer_name=row.name)
        for row in rows_result
    ]
    return UserCustomerAccessOut(user_id=user_id, customers=customers)


@router.put("/{user_id}/customer-access", response_model=UserCustomerAccessOut)
async def replace_user_customer_access(
    user_id: int,
    payload: UserCustomerAccessUpdate,
    session: AsyncSession = Depends(_admin_scoped_session),
):
    user_result = await session.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Admin users do not require customer assignments")

    target_ids = sorted(set(int(cid) for cid in payload.customer_ids))
    if target_ids:
        cust_rows = await session.execute(
            select(Customer.id, Customer.name).where(Customer.id.in_(target_ids))
        )
        found = {int(row.id): str(row.name) for row in cust_rows}
        missing = [cid for cid in target_ids if cid not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"Customers not found: {missing}")
    else:
        found = {}

    await session.execute(delete(UserCustomerAccess).where(UserCustomerAccess.user_id == user_id))
    for customer_id in target_ids:
        session.add(UserCustomerAccess(user_id=user_id, customer_id=customer_id))

    await session.commit()

    return UserCustomerAccessOut(
        user_id=user_id,
        customers=[
            CustomerAccessRef(customer_id=customer_id, customer_name=found[customer_id])
            for customer_id in target_ids
        ],
    )
