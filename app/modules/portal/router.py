from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.participantes.dto import EventoContactoResponse, InvitadoCreate
from app.modules.participantes.router import (
    _raise_http_error as _raise_participante_http_error,
)
from app.modules.participantes.service import ParticipanteServiceError
from app.modules.portal.dto import (
    AgregarParticipantesPortalRequest,
    PortalContactoDisponible,
    ValidarCodigoRequest,
    ValidarCodigoResponse,
)
from app.modules.portal.service import (
    CodigoInvalidoError,
    ContactoNoPerteneceEmpresaError,
    PortalContext,
    PortalService,
    PortalServiceError,
    PortalTokenInvalidoError,
)


router = APIRouter(prefix="/portal", tags=["Portal"])


def _raise_http_error(exc: PortalServiceError) -> None:
    if isinstance(exc, (CodigoInvalidoError, PortalTokenInvalidoError)):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


async def get_portal_context(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> PortalContext:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Sesión inválida o expirada."
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        return await PortalService(db).get_context(token)
    except PortalServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post("/validar-codigo", response_model=ValidarCodigoResponse)
async def validar_codigo(
    data: ValidarCodigoRequest, db: AsyncSession = Depends(get_db)
) -> ValidarCodigoResponse:
    try:
        return await PortalService(db).validar_codigo(data.codigo)
    except PortalServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("/contactos", response_model=list[PortalContactoDisponible])
async def listar_contactos(
    context: PortalContext = Depends(get_portal_context),
    db: AsyncSession = Depends(get_db),
) -> list[PortalContactoDisponible]:
    return await PortalService(db).listar_contactos(context)


@router.post("/participantes", response_model=list[EventoContactoResponse])
async def agregar_participantes(
    data: AgregarParticipantesPortalRequest,
    context: PortalContext = Depends(get_portal_context),
    db: AsyncSession = Depends(get_db),
) -> list[EventoContactoResponse]:
    try:
        return await PortalService(db).agregar_participantes(context, data)
    except ContactoNoPerteneceEmpresaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except PortalServiceError as exc:
        _raise_http_error(exc)
        raise
    except ParticipanteServiceError as exc:
        _raise_participante_http_error(exc)
        raise


@router.post(
    "/invitados",
    response_model=EventoContactoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def agregar_invitado(
    data: InvitadoCreate,
    context: PortalContext = Depends(get_portal_context),
    db: AsyncSession = Depends(get_db),
) -> EventoContactoResponse:
    try:
        return await PortalService(db).agregar_invitado(context, data)
    except ParticipanteServiceError as exc:
        _raise_participante_http_error(exc)
        raise
