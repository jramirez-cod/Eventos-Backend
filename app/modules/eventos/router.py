from datetime import date
from io import BytesIO

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Path,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.eventos.dto import (
    DetalleProgramacionResponse,
    DetalleProgramacionUpdate,
    EventoCreate,
    EventoFinalizarRequest,
    EventoInactivarRequest,
    EventoListResponse,
    EventoReabrirRequest,
    EventoResponse,
    EventoUpdate,
    ProgramacionEventoResponse,
    ProgramacionEventoUpdate,
)
from app.modules.eventos.models import EventoEstado, EventoModalidad
from app.modules.eventos.service import (
    DiaNotFoundError,
    EventoDependencyError,
    EventoNotEditableError,
    EventoNotFoundError,
    EventoPersistenceConflictError,
    EventoService,
    EventoServiceError,
    FlyerNotFoundError,
    FlyerTooLargeError,
    InvalidDateRangeError,
    InvalidFlyerError,
    InvalidScheduleError,
    InvalidStateTransitionError,
    ProgramacionNotFoundError,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_EVENTOS = "EVENTOS"
PERMISO_CONSULTAR = "CONSULTAR_EVENTO"
PERMISO_CREAR = "CREAR_EVENTO"
PERMISO_ACTUALIZAR = "ACTUALIZAR_EVENTO"
PERMISO_CAMBIAR_ESTADO = "CAMBIAR_ESTADO_EVENTO"
PERMISO_REABRIR = "REABRIR_EVENTO"
PERMISO_ELIMINAR = "ELIMINAR_EVENTO"
PERMISO_EXPORTAR = "EXPORTAR_EVENTO"

router = APIRouter(prefix="/eventos", tags=["Eventos"])


def _raise_http_error(exc: EventoServiceError) -> None:
    if isinstance(
        exc,
        (
            EventoNotFoundError,
            ProgramacionNotFoundError,
            DiaNotFoundError,
            FlyerNotFoundError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, FlyerTooLargeError):
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=str(exc)
        )
    if isinstance(
        exc,
        (
            EventoDependencyError,
            EventoNotEditableError,
            EventoPersistenceConflictError,
            InvalidStateTransitionError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(
        exc,
        (InvalidDateRangeError, InvalidScheduleError, InvalidFlyerError),
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=EventoListResponse)
async def listar_eventos(
    search: str | None = Query(default=None, max_length=200),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    estado: EventoEstado | None = Query(default=None),
    modalidad: EventoModalidad | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoListResponse:
    try:
        return await EventoService(db).listar_eventos(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            modalidad=modalidad,
            page=page,
            page_size=page_size,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("/exportar")
async def exportar_eventos(
    search: str | None = Query(default=None, max_length=200),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    estado: EventoEstado | None = Query(default=None),
    modalidad: EventoModalidad | None = Query(default=None),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_EXPORTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    try:
        content = await EventoService(db).exportar_eventos(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            modalidad=modalidad,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise
    return StreamingResponse(
        BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={
            "Content-Disposition": 'attachment; filename="eventos.xlsx"'
        },
    )


@router.get("/flyers/{filename}", include_in_schema=False)
async def descargar_flyer(
    filename: str,
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    try:
        path = EventoService(db).obtener_ruta_flyer(filename)
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise
    return FileResponse(path)


@router.post("", response_model=EventoResponse, status_code=status.HTTP_201_CREATED)
async def crear_evento(
    data: EventoCreate,
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).crear_evento(data=data, actor=actor)
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("/{id_evento}", response_model=EventoResponse)
async def obtener_evento(
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).obtener_evento(id_evento)
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put("/{id_evento}", response_model=EventoResponse)
async def actualizar_evento(
    data: EventoUpdate,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).actualizar_evento(
            id_evento=id_evento, data=data, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/{id_evento}/programacion", response_model=ProgramacionEventoResponse
)
async def obtener_programacion(
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).obtener_programacion(id_evento)
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put(
    "/{id_evento}/programacion", response_model=ProgramacionEventoResponse
)
async def actualizar_programacion(
    data: ProgramacionEventoUpdate,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).actualizar_programacion(
            id_evento=id_evento, data=data, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/{id_evento}/dias", response_model=list[DetalleProgramacionResponse]
)
async def listar_dias(
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[DetalleProgramacionResponse]:
    try:
        return await EventoService(db).listar_dias(id_evento)
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/{id_evento}/dias/{id_dia}", response_model=DetalleProgramacionResponse
)
async def actualizar_dia(
    data: DetalleProgramacionUpdate,
    id_evento: int = Path(gt=0),
    id_dia: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> DetalleProgramacionResponse:
    try:
        return await EventoService(db).actualizar_dia(
            id_evento=id_evento, id_dia=id_dia, data=data, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put("/{id_evento}/flyer", response_model=EventoResponse)
async def subir_flyer(
    id_evento: int = Path(gt=0),
    flyer: UploadFile = File(...),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).subir_flyer(
            id_evento=id_evento, flyer=flyer, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/{id_evento}/finalizar", response_model=EventoResponse)
async def finalizar_evento(
    data: EventoFinalizarRequest,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CAMBIAR_ESTADO)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).finalizar_evento(
            id_evento=id_evento, motivo=data.motivo, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/{id_evento}/reabrir", response_model=EventoResponse)
async def reabrir_evento(
    data: EventoReabrirRequest,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_REABRIR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).reabrir_evento(
            id_evento=id_evento, motivo=data.motivo, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/{id_evento}/inactivar", response_model=EventoResponse)
async def inactivar_evento(
    data: EventoInactivarRequest,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CAMBIAR_ESTADO)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).inactivar_evento(
            id_evento=id_evento, motivo=data.motivo, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.delete("/{id_evento}", status_code=status.HTTP_204_NO_CONTENT)
async def eliminar_evento(
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_ELIMINAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await EventoService(db).eliminar_evento(id_evento=id_evento, actor=actor)
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
