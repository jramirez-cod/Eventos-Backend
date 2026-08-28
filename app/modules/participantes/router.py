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
    AsignarBeneficioRequest,
    BeneficioDisponibleResponse,
    ContactoDesdeEventoCreate,
    ContactoPrincipalUpdate,
    EnviarCodigoAccesoMasivoResponse,
    EnviarQrMasivoResponse,
    EscaneoQrResponse,
    EstadoEventoContactoUpdate,
    EventoContactoCreateMultiple,
    EventoContactoCreateResponse,
    EventoContactoListResponse,
    EventoContactoResponse,
    EventoEmpresaCreate,
    EventoEmpresaResponse,
    InvitadoCreate,
    ReenviarCodigoAccesoRequest,
    ReimprimirCredencialRequest,
)
from app.modules.participantes.service import (
    AsignacionBeneficioCantidadInvalidaError,
    AsignacionBeneficioExistenteError,
    AsignacionBeneficioGrupoInvalidoError,
    AsignacionBeneficioNotFoundError,
    BeneficioNoAplicableError,
    ContactoInactiveError,
    ContactoNotFoundError,
    ContactoPrincipalInvalidoError,
    ContactoSinEmpresaAfiliadaError,
    CredencialYaImpresaError,
    CupoBeneficioAgotadoError,
    DuplicateEventoContactoError,
    DuplicateEventoEmpresaError,
    EmailRemitenteNoConfiguradoError,
    EmpresaInactiveError,
    EmpresaNotFoundError,
    EventoContactoNotFoundError,
    EventoEmpresaNotFoundError,
    EventoNotOpenError,
    InvitadoInvalidoError,
    LimiteInvitadosSuperadoError,
    ParticipanteBeneficioNotFoundError,
    ParticipantePersistenceConflictError,
    ParticipanteQrNotFoundError,
    ParticipanteService,
    ParticipanteServiceError,
    PasswordIncorrectoError,
    ProgramacionNotFoundError,
    ProgramacionSinDiasError,
    ResponsableInvalidoError,
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
            ProgramacionNotFoundError,
            EmpresaNotFoundError,
            EventoEmpresaNotFoundError,
            ContactoNotFoundError,
            EventoContactoNotFoundError,
            ContactoEmpresaNotFoundError,
            CargoNotFoundError,
            TipoDocumentoNotFoundError,
            ParticipanteBeneficioNotFoundError,
            AsignacionBeneficioNotFoundError,
            ParticipanteQrNotFoundError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PasswordIncorrectoError):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(
        exc,
        (
            EventoNotOpenError,
            EmpresaInactiveError,
            ContactoInactiveError,
            ContactoSinEmpresaAfiliadaError,
            DuplicateEventoEmpresaError,
            DuplicateEventoContactoError,
            ParticipantePersistenceConflictError,
            ContactoPersistenceConflictError,
            DuplicateDocumentError,
            AsignacionBeneficioExistenteError,
            CredencialYaImpresaError,
            CupoBeneficioAgotadoError,
            LimiteInvitadosSuperadoError,
            ProgramacionSinDiasError,
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
            AsignacionBeneficioCantidadInvalidaError,
            AsignacionBeneficioGrupoInvalidoError,
            BeneficioNoAplicableError,
            ResponsableInvalidoError,
            EmailRemitenteNoConfiguradoError,
            ContactoPrincipalInvalidoError,
            InvitadoInvalidoError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post(
    "/programaciones/{id_programacion_evento}/empresas",
    response_model=EventoEmpresaResponse,
    status_code=status.HTTP_201_CREATED,
)
async def afiliar_empresa_evento(
    data: EventoEmpresaCreate,
    id_programacion_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_AFILIAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoEmpresaResponse:
    try:
        return await ParticipanteService(db).afiliar_empresa_evento(
            id_programacion_evento=id_programacion_evento,
            id_empresa=data.id_empresa,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/programaciones/{id_programacion_evento}/empresas",
    response_model=list[EventoEmpresaResponse],
)
async def listar_empresas_programacion(
    id_programacion_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[EventoEmpresaResponse]:
    try:
        return await ParticipanteService(db).listar_empresas_programacion(
            id_programacion_evento
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.delete(
    "/empresas/{id_evento_empresa}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def desafiliar_empresa(
    id_evento_empresa: int = Path(gt=0),
    motivo: str | None = Query(default=None, max_length=500),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_AFILIAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await ParticipanteService(db).desafiliar_empresa(
            id_evento_empresa=id_evento_empresa,
            motivo=motivo,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/empresas/{id_evento_empresa}/contacto-principal",
    response_model=EventoEmpresaResponse,
)
async def asignar_contacto_principal(
    data: ContactoPrincipalUpdate,
    id_evento_empresa: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_AFILIAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoEmpresaResponse:
    try:
        return await ParticipanteService(db).asignar_contacto_principal(
            id_evento_empresa=id_evento_empresa,
            id_contacto=data.id_contacto,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/programaciones/{id_programacion_evento}/empresas/enviar-codigo-masivo",
    response_model=EnviarCodigoAccesoMasivoResponse,
)
async def enviar_codigo_acceso_masivo(
    id_programacion_evento: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_AFILIAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EnviarCodigoAccesoMasivoResponse:
    try:
        return await ParticipanteService(db).enviar_codigo_acceso_masivo(
            id_programacion_evento=id_programacion_evento, actor=actor
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/empresas/{id_evento_empresa}/reenviar-codigo",
    response_model=EventoEmpresaResponse,
)
async def reenviar_codigo_acceso(
    data: ReenviarCodigoAccesoRequest,
    id_evento_empresa: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_AFILIAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoEmpresaResponse:
    try:
        return await ParticipanteService(db).enviar_codigo_acceso(
            id_evento_empresa=id_evento_empresa, actor=actor, motivo=data.motivo
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/programaciones/{id_programacion_evento}/empresas/{id_empresa}/invitados",
    response_model=EventoContactoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def agregar_invitado_sin_registrar(
    data: InvitadoCreate,
    id_programacion_evento: int = Path(gt=0),
    id_empresa: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await ParticipanteService(db).agregar_invitado_sin_registrar(
            id_programacion_evento=id_programacion_evento,
            id_empresa=id_empresa,
            data=data,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/evento-contactos/{id_evento_contacto}/estado",
    response_model=EventoContactoResponse,
)
async def actualizar_estado_evento_contacto(
    data: EstadoEventoContactoUpdate,
    id_evento_contacto: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await ParticipanteService(db).actualizar_estado_evento_contacto(
            id_evento_contacto=id_evento_contacto,
            estado=data.estado,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.delete(
    "/evento-contactos/{id_evento_contacto}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def eliminar_invitado(
    id_evento_contacto: int = Path(gt=0),
    motivo: str | None = Query(default=None, max_length=500),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        await ParticipanteService(db).eliminar_invitado(
            id_evento_contacto=id_evento_contacto,
            motivo=motivo,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/programaciones/{id_programacion_evento}/evento-contactos",
    response_model=EventoContactoCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def agregar_evento_contactos(
    data: EventoContactoCreateMultiple,
    id_programacion_evento: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoCreateResponse:
    try:
        return await ParticipanteService(db).agregar_evento_contactos(
            id_programacion_evento=id_programacion_evento,
            data=data,
            actor=actor,
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/programaciones/{id_programacion_evento}/evento-contactos/crear-contacto",
    response_model=EventoContactoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def crear_contacto_desde_evento(
    data: ContactoDesdeEventoCreate,
    id_programacion_evento: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await ParticipanteService(db).crear_contacto_y_evento_contacto(
            id_programacion_evento=id_programacion_evento,
            data=data,
            actor=actor,
        )
    except (ParticipanteServiceError, ContactoServiceError) as exc:
        _raise_http_error(exc)
        raise


@router.get("/evento-contactos", response_model=EventoContactoListResponse)
async def listar_evento_contactos(
    id_programacion_evento: int | None = Query(default=None, gt=0),
    id_empresa: int | None = Query(default=None, gt=0),
    id_contacto: int | None = Query(default=None, gt=0),
    search: str | None = Query(default=None, max_length=120),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoListResponse:
    return await ParticipanteService(db).listar_evento_contactos(
        id_programacion_evento=id_programacion_evento,
        id_empresa=id_empresa,
        id_contacto=id_contacto,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/evento-contactos/{id_evento_contacto}", response_model=EventoContactoResponse
)
async def obtener_evento_contacto(
    id_evento_contacto: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await ParticipanteService(db).obtener_evento_contacto(
            id_evento_contacto
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch(
    "/evento-contactos/{id_evento_contacto}/asistencia",
    response_model=EventoContactoResponse,
)
async def marcar_asistencia(
    id_evento_contacto: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await ParticipanteService(db).marcar_asistencia(
            id_evento_contacto=id_evento_contacto, actor=actor
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/beneficios/asignar",
    response_model=list[EventoContactoResponse],
    status_code=status.HTTP_201_CREATED,
)
async def asignar_beneficio(
    data: AsignarBeneficioRequest,
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> list[EventoContactoResponse]:
    try:
        return await ParticipanteService(db).asignar_beneficio(
            data=data, actor=actor
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.delete(
    "/evento-contactos/{id_evento_contacto}/beneficio",
    response_model=EventoContactoResponse,
)
async def remover_asignacion_beneficio(
    id_evento_contacto: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await ParticipanteService(db).remover_asignacion_beneficio(
            id_evento_contacto=id_evento_contacto, actor=actor
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/evento-contactos/{id_evento_contacto}/beneficios-disponibles",
    response_model=list[BeneficioDisponibleResponse],
)
async def listar_beneficios_disponibles(
    id_evento_contacto: int = Path(gt=0),
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[BeneficioDisponibleResponse]:
    try:
        return await ParticipanteService(db).listar_beneficios_disponibles(
            id_evento_contacto
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/evento-contactos/{id_evento_contacto}/qr/enviar",
    response_model=EventoContactoResponse,
)
async def enviar_qr(
    id_evento_contacto: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await ParticipanteService(db).enviar_qr(
            id_evento_contacto=id_evento_contacto, actor=actor
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/programaciones/{id_programacion_evento}/qr/enviar-masivo",
    response_model=EnviarQrMasivoResponse,
)
async def enviar_qr_masivo(
    id_programacion_evento: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EnviarQrMasivoResponse:
    try:
        return await ParticipanteService(db).enviar_qr_masivo(
            id_programacion_evento=id_programacion_evento, actor=actor
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("/qr/{codigo_seguro}", response_model=EscaneoQrResponse)
async def escanear_qr(
    codigo_seguro: str,
    actor: Usuario = Depends(
        require_permission(MODULO_PARTICIPANTES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> EscaneoQrResponse:
    try:
        return await ParticipanteService(db).escanear_qr(codigo_seguro)
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post("/qr/{codigo_seguro}/imprimir", response_model=EscaneoQrResponse)
async def imprimir_credencial(
    codigo_seguro: str,
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EscaneoQrResponse:
    try:
        return await ParticipanteService(db).imprimir_credencial(
            codigo_seguro=codigo_seguro, actor=actor
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/evento-contactos/{id_evento_contacto}/reimprimir",
    response_model=EscaneoQrResponse,
)
async def reimprimir_credencial(
    data: ReimprimirCredencialRequest,
    id_evento_contacto: int = Path(gt=0),
    actor: Usuario = Depends(require_permission(MODULO_PARTICIPANTES, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> EscaneoQrResponse:
    try:
        return await ParticipanteService(db).reimprimir_credencial(
            id_evento_contacto=id_evento_contacto, data=data
        )
    except ParticipanteServiceError as exc:
        _raise_http_error(exc)
        raise
