import uuid
from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72

bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decode + validate an access token.

    Loop 15: explicitly enforce the `exp` claim. python-jose's
    `options={'require': ['exp']}` is documented to reject tokens
    missing the claim but in practice (jose 3.x) it's a no-op for
    decode — so we check by hand after a successful decode. Without
    this, a token minted without `exp` would be valid forever, opening
    a permanent backdoor if leaked.
    """
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
        )
    except JWTError:
        return None
    if "exp" not in payload:
        return None
    return payload


async def get_current_child(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
):
    """FastAPI dependency that extracts and validates the JWT from Authorization header."""
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")

    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    child_id = payload.get("sub")
    if not child_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    from app.models.family import Child
    result = await db.execute(select(Child).where(Child.id == uuid.UUID(child_id)))
    child = result.scalar_one_or_none()
    if not child:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    jwt_family_id = payload.get("family_id")
    # Loop 11: require family_id on all access tokens. The previous "if
    # present, check it" pattern let any token issued without the claim
    # bypass family isolation — including any future code path that
    # forgets to add the claim. Strictness is the right default.
    if not jwt_family_id:
        # Allow `pending:` tokens (issued during phone-verify/reset flows)
        # to pass without a family claim — they sub-string is `pending:<phone>`,
        # not a real child UUID, and they're scoped to a narrow set of
        # routes that do their own auth.
        if not (isinstance(child_id, str) and child_id.startswith("pending:")):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing family_id claim — please re-authenticate",
            )
    elif str(child.family_id) != jwt_family_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token family mismatch — please re-authenticate",
        )

    return child


def require_family_access(child, family_id: uuid.UUID) -> None:
    """Verify the authenticated child belongs to the requested family. Raises 403 on mismatch."""
    if child.family_id != family_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this family's data",
        )


def require_family_scoped_access(family_id: uuid.UUID, child=Depends(get_current_child)):
    """Combined auth + family-scope dependency.

    Loop 16: 15 routers (voting, person_context, hcg, expenses,
    health_tracking, etc.) had NO auth at all on their family-scoped
    endpoints. Any user with any guessed/leaked `family_id` could
    read/write financial, medical, or preference data for ANY family.

    Use this dep in family-scoped routes:

        @router.get("/families/{family_id}/voting/results")
        async def get_results(
            family_id: uuid.UUID,
            child: Child = Depends(require_family_scoped_access),
            ...
        ):

    Returns the authenticated child (so callers don't need a second
    Depends(get_current_child)). Raises 401 if no token, 403 if the
    token's family_id doesn't match the path family_id.
    """
    require_family_access(child, family_id)
    return child


def require_entity_access(child, entity) -> None:
    """Verify an entity (cart, ride, location, etc.) belongs to the child's family."""
    entity_family_id = getattr(entity, "family_id", None)
    if entity_family_id is None:
        return
    if child.family_id != entity_family_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this resource",
        )
