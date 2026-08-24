from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.contactos.service import (
    CargoInactiveError,
    CargoNotFoundError,
    ContactoPersistenceConflictError,
    ContactoServiceError,
    DuplicateDocumentError,
    EmpresaInactiveError as ContactoEmpresaInactiveError,
    EmpresaNotFoundError as ContactoEmpresaNotFoundError,
    InvalidDocumentPairError,
    InvalidPhoneError,
    TipoDocumentoInactiveError,
    TipoDocumentoNotFoundError,
)
from app.modules.participantes.dto import (
    ContactoDesdeEventoCreate,
    EventoEmpresaCreate,
    EventoEmpresaResponse,
    ParticipanteCreateMultiple,
    ParticipanteCreateResponse,
    ParticipanteListResponse,
    ParticipanteResponse,
)
from app.modules.participantes.models import ConfirmacionParticipante
from app.modules.participantes.service import (
    ContactoEmpresaMismatchError,
    ContactoInactiveError,
    ContactoNotFoundError,
    DuplicateEventoEmpresaError,
    DuplicateParticipanteError,
    EmpresaInactiveError,
    EmpresaNotFoundError,
    EventoEmpresaNotFoundError,
    EventoNotFoundError,
    EventoNotOpenError,
    ParticipanteNotFoundError,
    ParticipantePersistenceConflictError,
    ParticipanteService,
    ParticipanteServiceError,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_PARTICIPANTES = "PARTICIPANTES"
PERMISO_CONSULTAR = "CONSULTAR_PARTICIPANTE"
PERMISO_CREAR = "CREAR_PARTICIPANTE"
PERMISO_AFILIAR_EMPRESA = "AFILIAR_EMPRESA_EVENTO"

router = APIRouter(prefix="/participantes", tags=["Participantes"])


def _raise_http_error(exc: ParticipanteServiceError | ContactoServiceError) -> None:
    if isinstance(
        exc,
        (
            EventoNotFoundError,
            EmpresaNotFoundError,
            EventoEmpresaNotFoundError,
            ContactoNotFoundError,
            ParticipanteNotFoundError,
            ContactoEmpresaNotFoundError,
            CargoNotFoundError,
            TipoDocumentoNotFoundError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(
        exc,
        (
            EventoNotOpenError,
            EmpresaInactiveError,
            ContactoInactiveError,
            ContactoEmpresaMismatchError,
            DuplicateEventoEmpresaError,
            DuplicateParticipanteError,
            ParticipantePersistenceConflictError,
            ContactoPersistenceConflictError,
            DuplicateDocumentError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(
        exc,
        (
            ContactoEmpresaInactiveError,
            CargoInactiveError,
            TipoDocumentoInactiveError,
            InvalidDocumentPairError,
            InvalidPhoneError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/eventos/{id_evento}/empresas",
    response_model=EventoEmpresaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def afiliar_empresa_evento(
    data: EventoEmpresaCreate,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_AFILIAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoEmpresaResponse:
    try:
        return await ParticipanteService(db).afiliar_empresa_evento(
            id_evento=id_evento,
            id_empresa=data.id_empresa,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/empresas",
    response_model=list[EventoEmpresaResponse],
)
async def listar_empresas_evento(
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[EventoEmpresaResponse]:
    try:
        return await ParticipanteService(db).listar_empresas_evento(id_evento)
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/eventos/{id_evento}",
    response_model=ParticipanteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def agregar_participantes(
    data: ParticipanteCreateMultiple,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteCreateResponse:
    try:
        return await ParticipanteService(db).agregar_participantes(
            id_evento=id_evento,
            data=data,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/eventos/{id_evento}/crear-contacto",
    response_model=ParticipanteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_contacto_desde_evento(
    data: ContactoDesdeEventoCreate,
    id_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteResponse:
    try:
        return await ParticipanteService(db).crear_contacto_y_participante(
            id_evento=id_evento,
            data=data,
            actor=actor,
        )
    except (ParticipanteServiceError, ContactoServiceError) as exc:
        _raise_http_error(exc)
        raise


@router.get("", response_model=ParticipanteListResponse)
async def listar_participantes(
    id_evento: int | None = Query(default=None, gt=0),
    id_empresa: int | None = Query(default=None, gt=0),
    id_contacto: int | None = Query(default=None, gt=0),
    confirmacion: ConfirmacionParticipante | None = Query(default=None),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteListResponse:
    return await ParticipanteService(db).listar_participantes(
        id_evento=id_evento,
        id_empresa=id_empresa,
        id_contacto=id_contacto,
        confirmacion=confirmacion,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/{id_participante}", response_model=ParticipanteResponse)
async def obtener_participante(
    id_participante: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteResponse:
    try:
        return await ParticipanteService(db).obtener_participante(id_participante)
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise
