from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.dto import (
    InactivarUsuarioDTO,
    UsuarioCreateDTO,
    UsuarioResponseDTO,
)
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.usuario_service import (
    DuplicateEmailError,
    DuplicateUsernameError,
    PasswordPolicyViolationError,
    RolNotFoundError,
    UsuarioNotFoundError,
    UsuarioService,
)


MODULO_USUARIOS = "USUARIOS"
PERMISO_CREAR_USUARIO = "CREAR_USUARIO"
PERMISO_INACTIVAR_USUARIO = "INACTIVAR_USUARIO"

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.post(
    "",
    response_model=UsuarioResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def crear_usuario(
    data: UsuarioCreateDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_USUARIOS, PERMISO_CREAR_USUARIO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    try:
        return await UsuarioService(db).crear_usuario(data=data, actor=actor)
    except RolNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rol no encontrado.",
        )
    except DuplicateUsernameError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nombre de usuario ya existe.",
        )
    except DuplicateEmailError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Correo ya existe.",
        )
    except PasswordPolicyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.errors,
        )


@router.patch("/{id_usuario}/inactivar", response_model=UsuarioResponseDTO)
async def inactivar_usuario(
    id_usuario: int,
    data: InactivarUsuarioDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_USUARIOS, PERMISO_INACTIVAR_USUARIO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Usuario:
    try:
        return await UsuarioService(db).inactivar_usuario(
            id_usuario=id_usuario,
            data=data,
            actor=actor,
        )
    except UsuarioNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuario no encontrado.",
        )
