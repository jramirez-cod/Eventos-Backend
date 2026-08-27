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
    PoliticaEventoUpdate,
    ProgramacionDiaCreate,
    ProgramacionEventoCreate,
    ProgramacionEventoListResponse,
    ProgramacionEventoResponse,
    ProgramacionEventoTransversalListResponse,
    ProgramacionEventoUpdate,
    ResponsableEventoCreate,
    ResponsableEventoResponse,
)
from app.modules.eventos.models import EventoEstado, EventoModalidad
from app.modules.eventos.service import (
    AreaNotFoundError,
    BeneficioNotFoundError,
    CategoriaNotFoundError,
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
    LugarNoPermitidoError,
    LugarRequeridoError,
    ProgramacionNotEditableError,
    ProgramacionNotFoundError,
    ResponsableDuplicadoError,
    ResponsableNotFoundError,
    UltimoDiaNoEliminableError,
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
PERMISO_CAMBIAR_ESTADO_PROGRAMACION = "CAMBIAR_ESTADO_PROGRAMACION"
PERMISO_REABRIR_PROGRAMACION = "REABRIR_PROGRAMACION"

router = APIRouter(prefix="/eventos", tags=["Eventos"])


def _raise_http_error(exc: EventoServiceError) -> None:
    if isinstance(
        exc,
        (
            EventoNotFoundError,
            AreaNotFoundError,
            BeneficioNotFoundError,
            CategoriaNotFoundError,
            ProgramacionNotFoundError,
            DiaNotFoundError,
            ResponsableNotFoundError,
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
            ProgramacionNotEditableError,
            ResponsableDuplicadoError,
            UltimoDiaNoEliminableError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(
        exc,
        (
            InvalidDateRangeError,
            InvalidScheduleError,
            InvalidFlyerError,
            LugarRequeridoError,
            LugarNoPermitidoError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", response_model=EventoListResponse)
async def listar_eventos(
    search: str | None = Query(default=None, max_length=200),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    estado: EventoEstado | None = Query(default=None),
    id_area: int | None = Query(default=None, gt=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoListResponse:
    try:
        return await EventoService(db).listar_eventos(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            id_area=id_area,
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
    id_area: int | None = Query(default=None, gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_EXPORTAR)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    try:
        content = await EventoService(db).exportar_eventos(
            search=search,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            estado=estado,
            id_area=id_area,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise
    return StreamingResponse(
        BytesIO(content),
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        headers={"Content-Disposition": 'attachment; filename="eventos.xlsx"'},
    )


@router.get("/flyers/{filename}", include_in_schema=False)
async def descargar_flyer(
    filename: str,
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
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


@router.get(
    "/programaciones",
    response_model=ProgramacionEventoTransversalListResponse,
)
async def listar_programaciones_transversal(
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    id_empresa: int | None = Query(default=None, gt=0),
    estado: EventoEstado | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoTransversalListResponse:
    try:
        return await EventoService(db).listar_programaciones_transversal(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            id_empresa=id_empresa,
            estado=estado,
            page=page,
            page_size=page_size,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("/{id_evento}", response_model=EventoResponse)
async def obtener_evento(
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
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
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).actualizar_evento(
            id_evento=id_evento, data=data, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put("/{id_evento}/politica", response_model=EventoResponse)
async def actualizar_politica(
    data: PoliticaEventoUpdate,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoResponse:
    try:
        return await EventoService(db).actualizar_politica(
            id_evento=id_evento, data=data, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/{id_evento}/programaciones",
    response_model=ProgramacionEventoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_programacion(
    data: ProgramacionEventoCreate,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).crear_programacion(
            id_evento=id_evento, data=data, actor=actor
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/{id_evento}/programaciones", response_model=ProgramacionEventoListResponse
)
async def listar_programaciones(
    id_evento: int = Path(gt=0),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    modalidad: EventoModalidad | None = Query(default=None),
    estado: EventoEstado | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoListResponse:
    try:
        return await EventoService(db).listar_programaciones(
            id_evento=id_evento,
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            modalidad=modalidad,
            estado=estado,
            page=page,
            page_size=page_size,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/{id_evento}/programaciones/{id_programacion}",
    response_model=ProgramacionEventoResponse,
)
async def obtener_programacion(
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).obtener_programacion(
            id_evento=id_evento, id_programacion=id_programacion
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put(
    "/{id_evento}/programaciones/{id_programacion}",
    response_model=ProgramacionEventoResponse,
)
async def actualizar_programacion(
    data: ProgramacionEventoUpdate,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).actualizar_programacion(
            id_evento=id_evento,
            id_programacion=id_programacion,
            data=data,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/{id_evento}/programaciones/{id_programacion}/finalizar",
    response_model=ProgramacionEventoResponse,
)
async def finalizar_programacion(
    data: EventoFinalizarRequest,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CAMBIAR_ESTADO_PROGRAMACION)
    ),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).finalizar_programacion(
            id_evento=id_evento,
            id_programacion=id_programacion,
            motivo=data.motivo,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/{id_evento}/programaciones/{id_programacion}/reabrir",
    response_model=ProgramacionEventoResponse,
)
async def reabrir_programacion(
    data: EventoReabrirRequest,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_REABRIR_PROGRAMACION)
    ),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).reabrir_programacion(
            id_evento=id_evento,
            id_programacion=id_programacion,
            motivo=data.motivo,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/{id_evento}/programaciones/{id_programacion}/inactivar",
    response_model=ProgramacionEventoResponse,
)
async def inactivar_programacion(
    data: EventoInactivarRequest,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_EVENTOS, PERMISO_CAMBIAR_ESTADO_PROGRAMACION)
    ),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionEventoResponse:
    try:
        return await EventoService(db).inactivar_programacion(
            id_evento=id_evento,
            id_programacion=id_programacion,
            motivo=data.motivo,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/{id_evento}/programaciones/{id_programacion}/dias",
    response_model=list[DetalleProgramacionResponse],
)
async def listar_dias(
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> list[DetalleProgramacionResponse]:
    try:
        return await EventoService(db).listar_dias(
            id_evento=id_evento, id_programacion=id_programacion
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/{id_evento}/programaciones/{id_programacion}/dias",
    response_model=DetalleProgramacionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_dia(
    data: ProgramacionDiaCreate,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> DetalleProgramacionResponse:
    try:
        return await EventoService(db).crear_dia(
            id_evento=id_evento,
            id_programacion=id_programacion,
            data=data,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/{id_evento}/programaciones/{id_programacion}/dias/{id_dia}",
    response_model=DetalleProgramacionResponse,
)
async def actualizar_dia(
    data: DetalleProgramacionUpdate,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    id_dia: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> DetalleProgramacionResponse:
    try:
        return await EventoService(db).actualizar_dia(
            id_evento=id_evento,
            id_programacion=id_programacion,
            id_dia=id_dia,
            data=data,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.delete(
    "/{id_evento}/programaciones/{id_programacion}/dias/{id_dia}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def eliminar_dia(
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    id_dia: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await EventoService(db).eliminar_dia(
            id_evento=id_evento,
            id_programacion=id_programacion,
            id_dia=id_dia,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{id_evento}/programaciones/{id_programacion}/responsables",
    response_model=ResponsableEventoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_responsable(
    data: ResponsableEventoCreate,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> ResponsableEventoResponse:
    try:
        return await EventoService(db).crear_responsable(
            id_evento=id_evento,
            id_programacion=id_programacion,
            data=data,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/{id_evento}/programaciones/{id_programacion}/responsables",
    response_model=list[ResponsableEventoResponse],
)
async def listar_responsables(
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> list[ResponsableEventoResponse]:
    try:
        return await EventoService(db).listar_responsables(
            id_evento=id_evento, id_programacion=id_programacion
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/{id_evento}/programaciones/{id_programacion}/responsables/{id_responsable}/estado",
    response_model=ResponsableEventoResponse,
)
async def cambiar_estado_responsable(
    estado: bool,
    id_evento: int = Path(gt=0),
    id_programacion: int = Path(gt=0),
    id_responsable: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
    db: AsyncSession = Depends(get_db),
) -> ResponsableEventoResponse:
    try:
        return await EventoService(db).cambiar_estado_responsable(
            id_evento=id_evento,
            id_programacion=id_programacion,
            id_responsable=id_responsable,
            estado=estado,
            actor=actor,
        )
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put("/{id_evento}/flyer", response_model=EventoResponse)
async def subir_flyer(
    id_evento: int = Path(gt=0),
    flyer: UploadFile = File(...),
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ACTUALIZAR)),
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
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_REABRIR)),
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
    actor: Usuario = Depends(require_permission(MODULO_EVENTOS, PERMISO_ELIMINAR)),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await EventoService(db).eliminar_evento(id_evento=id_evento, actor=actor)
    except EventoServiceError as exc:
        _raise_http_error(exc)
        raise
    return Response(status_code=status.HTTP_204_NO_CONTENT)
