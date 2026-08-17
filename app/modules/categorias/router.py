from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.categorias.dto import (
    CategoriaCreateDTO,
    CategoriaGrupoResponseDTO,
    CategoriaResponseDTO,
)
from app.modules.categorias.models import Categoria
from app.modules.categorias.service import (
    ActiveCompaniesInCategoryError,
    CategoriaGroupNotFoundError,
    CategoriaNotFoundError,
    CategoriaService,
    DuplicateCategoryRelationError,
    InactiveCategoryError,
    InactiveGroupError,
)
from app.modules.empresas.dto import EmpresaDependienteDTO
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_CATEGORIAS = "CATEGORIAS"
PERMISO_CREAR_CATEGORIA = "CREAR_CATEGORIA"
PERMISO_INACTIVAR_CATEGORIA = "INACTIVAR_CATEGORIA"
PERMISO_REACTIVAR_CATEGORIA = "REACTIVAR_CATEGORIA"

router = APIRouter(prefix="/categorias", tags=["Categorías"])


@router.post(
    "",
    response_model=CategoriaGrupoResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def crear_categoria(
    data: CategoriaCreateDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_CATEGORIAS, PERMISO_CREAR_CATEGORIA)
    ),
    db: AsyncSession = Depends(get_db),
) -> CategoriaGrupoResponseDTO:
    try:
        return await CategoriaService(db).crear_categoria(
            data=data,
            actor=actor,
        )
    except CategoriaGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grupo no encontrado.",
        )
    except InactiveGroupError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El grupo se encuentra inactivo.",
        )
    except InactiveCategoryError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La categoría existe pero se encuentra inactiva.",
        )
    except DuplicateCategoryRelationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La categoría ya está asociada al grupo.",
        )


@router.patch(
    "/{id_categoria}/inactivar",
    response_model=CategoriaResponseDTO,
)
async def inactivar_categoria(
    id_categoria: int,
    actor: Usuario = Depends(
        require_permission(
            MODULO_CATEGORIAS,
            PERMISO_INACTIVAR_CATEGORIA,
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> Categoria:
    try:
        return await CategoriaService(db).inactivar_categoria(
            id_categoria=id_categoria,
            actor=actor,
        )
    except CategoriaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada.",
        )
    except ActiveCompaniesInCategoryError as exc:
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
    "/{id_categoria}/reactivar",
    response_model=CategoriaResponseDTO,
)
async def reactivar_categoria(
    id_categoria: int,
    actor: Usuario = Depends(
        require_permission(
            MODULO_CATEGORIAS,
            PERMISO_REACTIVAR_CATEGORIA,
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> Categoria:
    try:
        return await CategoriaService(db).reactivar_categoria(
            id_categoria=id_categoria,
            actor=actor,
        )
    except CategoriaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Categoría no encontrada.",
        )
