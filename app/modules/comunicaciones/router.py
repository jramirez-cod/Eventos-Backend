from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.comunicaciones.dto import (
    CorreoConfiguracionGlobalResponse,
    CorreoConfiguracionGlobalUpdate,
    CorreoOperacionResponse,
    CorreoPlantillaHistorialResponse,
    CorreoPlantillaListItem,
    CorreoPlantillaPreviewRequest,
    CorreoPlantillaPreviewResponse,
    CorreoPlantillaResponse,
    CorreoPlantillaRestaurarRequest,
    CorreoPlantillaUpdate,
    CorreoPruebaRequest,
)
from app.modules.comunicaciones.email_service import (
    EmailConfigurationError,
    EmailDeliveryError,
)
from app.modules.comunicaciones.service import (
    ComunicacionService,
    ComunicacionServiceError,
    ConfiguracionCorreoNotFoundError,
    EmisorCorreoInvalidError,
    PlantillaInvalidError,
    PlantillaNotFoundError,
    PlantillaVersionConflictError,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_COMUNICACIONES = "COMUNICACIONES"
PERMISO_CONSULTAR = "CONSULTAR_PLANTILLA_CORREO"
PERMISO_GESTIONAR = "GESTIONAR_PLANTILLA_CORREO"
PERMISO_RESTAURAR = "RESTAURAR_PLANTILLA_CORREO"
PERMISO_ENVIAR_PRUEBA = "ENVIAR_CORREO_PRUEBA"
PERMISO_CONFIGURAR = "CONFIGURAR_CORREO_GLOBAL"

router = APIRouter(prefix="/comunicaciones", tags=["Comunicaciones"])


def _raise_http_error(exc: Exception) -> None:
    if isinstance(
        exc,
        (PlantillaNotFoundError, ConfiguracionCorreoNotFoundError),
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PlantillaVersionConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, (PlantillaInvalidError, EmisorCorreoInvalidError)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    # Falta de plantilla o remitente es configuración pendiente, no una caída
    # del SMTP: se responde 503 para que el panel lo distinga de un fallo real.
    if isinstance(exc, EmailConfigurationError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        )
    if isinstance(exc, EmailDeliveryError):
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    raise exc


@router.get(
    "/plantillas",
    response_model=list[CorreoPlantillaListItem],
)
async def listar_plantillas(
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[CorreoPlantillaListItem]:
    return await ComunicacionService(db).listar_plantillas()


@router.get(
    "/plantillas/{codigo}",
    response_model=CorreoPlantillaResponse,
)
async def obtener_plantilla(
    codigo: str = Path(min_length=1, max_length=50),
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CorreoPlantillaResponse:
    try:
        return await ComunicacionService(db).obtener_plantilla(codigo)
    except ComunicacionServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put(
    "/plantillas/{codigo}",
    response_model=CorreoPlantillaResponse,
)
async def actualizar_plantilla(
    data: CorreoPlantillaUpdate,
    codigo: str = Path(min_length=1, max_length=50),
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_GESTIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CorreoPlantillaResponse:
    try:
        return await ComunicacionService(db).actualizar_plantilla(
            codigo=codigo,
            data=data,
            actor=actor,
        )
    except ComunicacionServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/plantillas/{codigo}/previsualizar",
    response_model=CorreoPlantillaPreviewResponse,
)
async def previsualizar_plantilla(
    data: CorreoPlantillaPreviewRequest,
    codigo: str = Path(min_length=1, max_length=50),
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CorreoPlantillaPreviewResponse:
    try:
        return await ComunicacionService(db).previsualizar(codigo=codigo, data=data)
    except ComunicacionServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/plantillas/{codigo}/historial",
    response_model=list[CorreoPlantillaHistorialResponse],
)
async def listar_historial(
    codigo: str = Path(min_length=1, max_length=50),
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[CorreoPlantillaHistorialResponse]:
    try:
        return await ComunicacionService(db).listar_historial(codigo)
    except ComunicacionServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/plantillas/{codigo}/restaurar/{version}",
    response_model=CorreoPlantillaResponse,
)
async def restaurar_plantilla(
    data: CorreoPlantillaRestaurarRequest,
    codigo: str = Path(min_length=1, max_length=50),
    version: int = Path(ge=1),
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_RESTAURAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CorreoPlantillaResponse:
    try:
        return await ComunicacionService(db).restaurar_version(
            codigo=codigo,
            version=version,
            data=data,
            actor=actor,
        )
    except ComunicacionServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/configuracion-global",
    response_model=CorreoConfiguracionGlobalResponse,
)
async def obtener_configuracion_global(
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CorreoConfiguracionGlobalResponse:
    try:
        return await ComunicacionService(db).obtener_configuracion()
    except ComunicacionServiceError as exc:
        _raise_http_error(exc)
        raise


@router.put(
    "/configuracion-global",
    response_model=CorreoConfiguracionGlobalResponse,
)
async def actualizar_configuracion_global(
    data: CorreoConfiguracionGlobalUpdate,
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_CONFIGURAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> CorreoConfiguracionGlobalResponse:
    try:
        return await ComunicacionService(db).actualizar_configuracion(
            data=data,
            actor=actor,
        )
    except ComunicacionServiceError as exc:
        _raise_http_error(exc)
        raise


@router.post(
    "/plantillas/{codigo}/enviar-prueba",
    response_model=CorreoOperacionResponse,
)
async def enviar_correo_prueba(
    data: CorreoPruebaRequest,
    codigo: str = Path(min_length=1, max_length=50),
    actor: Usuario = Depends(
        require_permission(MODULO_COMUNICACIONES, PERMISO_ENVIAR_PRUEBA)
    ),
    db: AsyncSession = Depends(get_db),
) -> CorreoOperacionResponse:
    try:
        await ComunicacionService(db).enviar_prueba(codigo=codigo, data=data)
        return CorreoOperacionResponse(message="Correo de prueba enviado.")
    except (ComunicacionServiceError, EmailDeliveryError) as exc:
        _raise_http_error(exc)
        raise
