from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.categorias.repository import CategoriaRepository
from app.modules.grupos.dto import (
    AsignarCategoriaDTO,
    CategoriaAsignadaResponseDTO,
    GrupoCreateDTO,
    GrupoResponseDTO,
    InactivarGrupoDTO,
)
from app.modules.grupos.models import Grupo
from app.modules.grupos.repository import GrupoRepository
from app.modules.grupos.service import (
    AsignacionNotFoundError,
    CategoriaNotFoundError,
    CategoriaYaAsignadaError,
    DuplicateGrupoIdError,
    DuplicateGrupoNameError,
    GrupoEnUsoError,
    GrupoNotFoundError,
    GrupoService,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_GRUPOS = "GRUPOS"
PERMISO_CREAR_GRUPO = "CREAR_GRUPO"
PERMISO_INACTIVAR_GRUPO = "INACTIVAR_GRUPO"

router = APIRouter(prefix="/grupos", tags=["Grupos"])


@router.get("", response_model=list[GrupoResponseDTO])
async def listar_grupos(
    actor: Usuario = Depends(require_permission(MODULO_GRUPOS, PERMISO_CREAR_GRUPO)),
    db: AsyncSession = Depends(get_db),
) -> list[Grupo]:
    return await GrupoRepository(db).list_all()


@router.post("", response_model=GrupoResponseDTO, status_code=status.HTTP_201_CREATED)
async def crear_grupo(
    data: GrupoCreateDTO,
    actor: Usuario = Depends(require_permission(MODULO_GRUPOS, PERMISO_CREAR_GRUPO)),
    db: AsyncSession = Depends(get_db),
) -> Grupo:
    try:
        return await GrupoService(db).crear_grupo(data=data, actor=actor)
    except DuplicateGrupoIdError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El id de grupo ya existe."
        )
    except DuplicateGrupoNameError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="El nombre del grupo ya existe.",
        )


@router.patch("/{id_grupo}/inactivar", response_model=GrupoResponseDTO)
async def inactivar_grupo(
    id_grupo: int,
    data: InactivarGrupoDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_GRUPOS, PERMISO_INACTIVAR_GRUPO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Grupo:
    try:
        return await GrupoService(db).inactivar_grupo(
            id_grupo=id_grupo, data=data, actor=actor
        )
    except GrupoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado."
        )
    except GrupoEnUsoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "El grupo está siendo usado por las siguientes empresas activas: "
                + ", ".join(exc.nombres_empresas)
                + ". Inactive esas empresas o cámbieles la clasificación"
                " antes de continuar."
            ),
        )


@router.patch("/{id_grupo}/reactivar", response_model=GrupoResponseDTO)
async def reactivar_grupo(
    id_grupo: int,
    actor: Usuario = Depends(
        require_permission(MODULO_GRUPOS, PERMISO_INACTIVAR_GRUPO)
    ),
    db: AsyncSession = Depends(get_db),
) -> Grupo:
    try:
        return await GrupoService(db).reactivar_grupo(id_grupo=id_grupo, actor=actor)
    except GrupoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado."
        )


@router.get(
    "/{id_grupo}/categorias", response_model=list[CategoriaAsignadaResponseDTO]
)
async def listar_categorias_del_grupo(
    id_grupo: int,
    actor: Usuario = Depends(require_permission(MODULO_GRUPOS, PERMISO_CREAR_GRUPO)),
    db: AsyncSession = Depends(get_db),
) -> list[CategoriaAsignadaResponseDTO]:
    detalles = await CategoriaRepository(db).list_detalles_by_grupo(id_grupo=id_grupo)
    return [
        CategoriaAsignadaResponseDTO(
            id_detalle_categoria=detalle.id_detalle_categoria,
            id_grupo=detalle.id_grupo,
            id_categoria=detalle.id_categoria,
            nombre_categoria=categoria.nombre_categoria,
            estado=detalle.estado,
        )
        for detalle, categoria in detalles
    ]


@router.post(
    "/{id_grupo}/categorias",
    response_model=CategoriaAsignadaResponseDTO,
    status_code=status.HTTP_201_CREATED,
)
async def asignar_categoria(
    id_grupo: int,
    data: AsignarCategoriaDTO,
    actor: Usuario = Depends(require_permission(MODULO_GRUPOS, PERMISO_CREAR_GRUPO)),
    db: AsyncSession = Depends(get_db),
) -> CategoriaAsignadaResponseDTO:
    try:
        detalle = await GrupoService(db).asignar_categoria(
            id_grupo=id_grupo, data=data, actor=actor
        )
    except GrupoNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grupo no encontrado."
        )
    except CategoriaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Categoría no encontrada."
        )
    except CategoriaYaAsignadaError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="La categoría ya está asignada a este grupo.",
        )

    categoria = await CategoriaRepository(db).get_by_id(data.id_categoria)
    return CategoriaAsignadaResponseDTO(
        id_detalle_categoria=detalle.id_detalle_categoria,
        id_grupo=detalle.id_grupo,
        id_categoria=detalle.id_categoria,
        nombre_categoria=categoria.nombre_categoria if categoria else "",
        estado=detalle.estado,
    )


@router.patch(
    "/{id_grupo}/categorias/{id_categoria}/quitar",
    response_model=CategoriaAsignadaResponseDTO,
)
async def quitar_categoria(
    id_grupo: int,
    id_categoria: int,
    actor: Usuario = Depends(
        require_permission(MODULO_GRUPOS, PERMISO_INACTIVAR_GRUPO)
    ),
    db: AsyncSession = Depends(get_db),
) -> CategoriaAsignadaResponseDTO:
    try:
        detalle = await GrupoService(db).quitar_categoria(
            id_grupo=id_grupo, id_categoria=id_categoria, actor=actor
        )
    except AsignacionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="La categoría no está asignada a este grupo.",
        )

    categoria = await CategoriaRepository(db).get_by_id(id_categoria)
    return CategoriaAsignadaResponseDTO(
        id_detalle_categoria=detalle.id_detalle_categoria,
        id_grupo=detalle.id_grupo,
        id_categoria=detalle.id_categoria,
        nombre_categoria=categoria.nombre_categoria if categoria else "",
        estado=detalle.estado,
    )
