from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.maestros.dto import (
    AreaCreate,
    AreaEstadoUpdate,
    AreaListResponse,
    AreaResponse,
    AreaUpdate,
    CargoCreate,
    CargoEstadoUpdate,
    CargoListResponse,
    CargoResponse,
    CargoUpdate,
)
from app.modules.maestros.service import (
    AreaNotFoundError,
    CargoNotFoundError,
    DuplicateAreaNameError,
    DuplicateCargoNameError,
    InvalidMaestroNameError,
    MaestroService,
    MaestroServiceError,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_MAESTROS = "MAESTROS"
PERMISO_CONSULTAR = "CONSULTAR_MAESTROS"
PERMISO_GESTIONAR = "GESTIONAR_MAESTROS"

router = APIRouter(prefix="/maestros", tags=["Maestros"])


def _raise_http_error(exc: MaestroServiceError) -> None:
    if isinstance(exc, (CargoNotFoundError, AreaNotFoundError)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, (DuplicateCargoNameError, DuplicateAreaNameError)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, InvalidMaestroNameError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


@router.get("/cargos", response_model=CargoListResponse)
async def listar_cargos(
    search: str | None = Query(default=None, max_length=100),
    estado: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CargoListResponse:
    return await MaestroService(db).listar_cargos(
        search=search,
        estado=estado,
        page=page,
        page_size=page_size,
    )


@router.get("/cargos/{id_cargo}", response_model=CargoResponse)
async def obtener_cargo(
    id_cargo: int,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CargoResponse:
    try:
        return CargoResponse.model_validate(
            await MaestroService(db).obtener_cargo(id_cargo)
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/cargos", response_model=CargoResponse, status_code=status.HTTP_201_CREATED
)
async def crear_cargo(
    data: CargoCreate,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_GESTIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CargoResponse:
    try:
        return CargoResponse.model_validate(
            await MaestroService(db).crear_cargo(data=data, actor=actor)
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put("/cargos/{id_cargo}", response_model=CargoResponse)
async def actualizar_cargo(
    id_cargo: int,
    data: CargoUpdate,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_GESTIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CargoResponse:
    try:
        return CargoResponse.model_validate(
            await MaestroService(db).actualizar_cargo(
                id_cargo=id_cargo,
                data=data,
                actor=actor,
            )
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/cargos/{id_cargo}/estado", response_model=CargoResponse)
async def cambiar_estado_cargo(
    id_cargo: int,
    data: CargoEstadoUpdate,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_GESTIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CargoResponse:
    try:
        return CargoResponse.model_validate(
            await MaestroService(db).cambiar_estado_cargo(
                id_cargo=id_cargo,
                estado=data.estado,
                actor=actor,
            )
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("/areas", response_model=AreaListResponse)
async def listar_areas(
    search: str | None = Query(default=None, max_length=100),
    estado: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> AreaListResponse:
    return await MaestroService(db).listar_areas(
        search=search,
        estado=estado,
        page=page,
        page_size=page_size,
    )


@router.get("/areas/{id_area}", response_model=AreaResponse)
async def obtener_area(
    id_area: int,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> AreaResponse:
    try:
        return AreaResponse.model_validate(
            await MaestroService(db).obtener_area(id_area)
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/areas", response_model=AreaResponse, status_code=status.HTTP_201_CREATED
)
async def crear_area(
    data: AreaCreate,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_GESTIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> AreaResponse:
    try:
        return AreaResponse.model_validate(
            await MaestroService(db).crear_area(data=data, actor=actor)
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put("/areas/{id_area}", response_model=AreaResponse)
async def actualizar_area(
    id_area: int,
    data: AreaUpdate,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_GESTIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> AreaResponse:
    try:
        return AreaResponse.model_validate(
            await MaestroService(db).actualizar_area(
                id_area=id_area,
                data=data,
                actor=actor,
            )
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/areas/{id_area}/estado", response_model=AreaResponse)
async def cambiar_estado_area(
    id_area: int,
    data: AreaEstadoUpdate,
    actor: Usuario = Depends(
        require_permission(MODULO_MAESTROS, PERMISO_GESTIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> AreaResponse:
    try:
        return AreaResponse.model_validate(
            await MaestroService(db).cambiar_estado_area(
                id_area=id_area,
                estado=data.estado,
                actor=actor,
            )
        )
    except MaestroServiceError as exc:
        _raise_http_error(exc)
        raise
