from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.db.session import get_db
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")
password_change_bearer = HTTPBearer(
    scheme_name="PasswordChangeBearer",
    description="JWT limitado devuelto por el primer login.",
    auto_error=False,
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    try:
        payload = security.decode_access_token(token)
        id_usuario = int(payload["sub"])
    except (ValueError, security.InvalidTokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    usuario = await UsuarioRepository(db).get_by_id(id_usuario)
    if usuario is None or not usuario.estado:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticación inválida.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return usuario


def require_permission(modulo: str, permiso: str) -> Callable[..., object]:
    async def dependency(
        current_user: Usuario = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> Usuario:
        repository = UsuarioRepository(db)
        allowed = await repository.has_permission(
            id_rol=current_user.id_rol,
            modulo=modulo,
            permiso=permiso,
        )
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No cuenta con permiso para ejecutar esta operación.",
            )
        return current_user

    return dependency
