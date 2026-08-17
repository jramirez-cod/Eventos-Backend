from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.empresas.dto import EmpresaDependienteDTO
from app.modules.grupos.dto import (
    GrupoConfiguracionCategoriaDTO,
    GrupoCreateDTO,
    GrupoResponseDTO,
)
from app.modules.grupos.models import Grupo
from app.modules.grupos.service import (
    ActiveCompaniesInGroupError,
    DuplicateGroupNameError,
    GrupoNotFoundError,
    GrupoService,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_GRUPOS = "GRUPOS"
PERMISO_CREAR_GRUPO = "CREAR_GRUPO"
PERMISO_INACTIVAR_GRUPO = "INACTIVAR_GRUPO"
PERMISO_REACTIVAR_GRUPO = "REACTIVAR_GRUPO"
PERMISO_CONFIGURAR_GRUPO = "CONFIGURAR_GRUPO"

router = APIRouter(prefix="/grupos", tags=["Grupos"])


@router.post(
    "",
    response_model=GrupoResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def crear_grupo(
    data: GrupoCreateDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_GRUPOS, PERMISO_CREAR_GRUPO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Grupo:
    try:
        return await GrupoService(db).crear_grupo(data=data, actor=actor)
    except DuplicateGroupNameError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nombre del grupo ya existe.",
        )


@router.patch(
    "/{id_grupo}/inactivar",
    response_model=GrupoResponseDTO,
)
async def inactivar_grupo(
    id_grupo: int,
    actor: Usuario = Depends(
        require_permission(MODULO_GRUPOS, PERMISO_INACTIVAR_GRUPO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Grupo:
    try:
        return await GrupoService(db).inactivar_grupo(
            id_grupo=id_grupo,
            actor=actor,
        )
    except GrupoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grupo no encontrado.",
        )
    except ActiveCompaniesInGroupError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(exc),
                "empresas_dependientes": [
                    EmpresaDependienteDTO.model_validate(empresa).model_dump()
                    for empresa in exc.empresas
                ],
            },
        )


@router.patch(
    "/{id_grupo}/reactivar",
    response_model=GrupoResponseDTO,
)
async def reactivar_grupo(
    id_grupo: int,
    actor: Usuario = Depends(
        require_permission(MODULO_GRUPOS, PERMISO_REACTIVAR_GRUPO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Grupo:
    try:
        return await GrupoService(db).reactivar_grupo(
            id_grupo=id_grupo,
            actor=actor,
        )
    except GrupoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grupo no encontrado.",
        )


@router.patch(
    "/{id_grupo}/configuracion-categoria",
    response_model=GrupoResponseDTO,
)
async def configurar_categoria_grupo(
    id_grupo: int,
    data: GrupoConfiguracionCategoriaDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_GRUPOS, PERMISO_CONFIGURAR_GRUPO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Grupo:
    try:
        return await GrupoService(db).configurar_categoria(
            id_grupo=id_grupo,
            data=data,
            actor=actor,
        )
    except GrupoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grupo no encontrado.",
        )
