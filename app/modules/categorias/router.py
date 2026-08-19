from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.categorias.dto import (
    CategoriaCreateDTO,
    CategoriaResponseDTO,
    InactivarCategoriaDTO,
)
from app.modules.categorias.models import Categoria
from app.modules.categorias.repository import CategoriaRepository
from app.modules.categorias.service import (
    CategoriaEnUsoError,
    CategoriaNotFoundError,
    CategoriaService,
    DuplicateCategoriaNameError,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_CATEGORIAS = "CATEGORIAS"
PERMISO_CREAR_CATEGORIA = "CREAR_CATEGORIA"
PERMISO_INACTIVAR_CATEGORIA = "INACTIVAR_CATEGORIA"

router = APIRouter(prefix="/categorias", tags=["Categorías"])


@router.get("", response_model=list[CategoriaResponseDTO])
async def listar_categorias(
    actor: Usuario = Depends(
        require_permission(MODULO_CATEGORIAS, PERMISO_CREAR_CATEGORIA)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[Categoria]:
    return await CategoriaRepository(db).list_all()


@router.post(
    "", response_model=CategoriaResponseDTO, status_code=status.HTTP_201_CREATED
)
async def crear_categoria(
    data: CategoriaCreateDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_CATEGORIAS, PERMISO_CREAR_CATEGORIA)
    ),
    db: AsyncSession = Depends(get_db),
) -> Categoria:
    try:
        return await CategoriaService(db).crear_categoria(data=data, actor=actor)
    except DuplicateCategoriaNameError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nombre de la categoría ya existe.",
        )


@router.patch("/{id_categoria}/inactivar", response_model=CategoriaResponseDTO)
async def inactivar_categoria(
    id_categoria: int,
    data: InactivarCategoriaDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_CATEGORIAS, PERMISO_INACTIVAR_CATEGORIA)
    ),
    db: AsyncSession = Depends(get_db),
) -> Categoria:
    try:
        return await CategoriaService(db).inactivar_categoria(
            id_categoria=id_categoria, data=data, actor=actor
        )
    except CategoriaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada."
        )
    except CategoriaEnUsoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "La categoría está siendo usada por las siguientes empresas activas: "
                + ", ".join(exc.nombres_empresas)
                + ". Inactive esas empresas o cámbieles la clasificación"
                " antes de continuar."
            ),
        )


@router.patch("/{id_categoria}/reactivar", response_model=CategoriaResponseDTO)
async def reactivar_categoria(
    id_categoria: int,
    actor: Usuario = Depends(
        require_permission(MODULO_CATEGORIAS, PERMISO_INACTIVAR_CATEGORIA)
    ),
    db: AsyncSession = Depends(get_db),
) -> Categoria:
    try:
        return await CategoriaService(db).reactivar_categoria(
            id_categoria=id_categoria, actor=actor
        )
    except CategoriaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada."
        )
