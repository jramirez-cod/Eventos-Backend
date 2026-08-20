import csv
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.contactos.dto import (
    ContactoCambiarEmpresaRequest,
    ContactoCreate,
    ContactoEstadoUpdate,
    ContactoFusionRequest,
    ContactoPage,
    ContactoResponse,
    ContactoUpdate,
)
from app.modules.contactos.service import (
    CargoInactiveError,
    CargoNotFoundError,
    ContactoNotFoundError,
    ContactoPersistenceConflictError,
    ContactoService,
    ContactoServiceError,
    DuplicateDocumentError,
    EmpresaInactiveError,
    EmpresaNotFoundError,
    InvalidDocumentPairError,
    InvalidPhoneError,
    SameCompanyError,
    SameContactFusionError,
    TipoDocumentoInactiveError,
    TipoDocumentoNotFoundError,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_CONTACTOS = "CONTACTOS"
PERMISO_CREAR = "CREAR_CONTACTO"
PERMISO_CONSULTAR = "CONSULTAR_CONTACTO"
PERMISO_ACTUALIZAR = "ACTUALIZAR_CONTACTO"
PERMISO_CAMBIAR_EMPRESA = "CAMBIAR_EMPRESA_CONTACTO"
PERMISO_CAMBIAR_ESTADO = "CAMBIAR_ESTADO_CONTACTO"
PERMISO_FUSIONAR = "FUSIONAR_CONTACTO"
PERMISO_EXPORTAR = "EXPORTAR_CONTACTO"

router = APIRouter(prefix="/contactos", tags=["Contactos"])


def _raise_http_error(exc: ContactoServiceError) -> None:
    if isinstance(
        exc,
        (
            ContactoNotFoundError,
            EmpresaNotFoundError,
            CargoNotFoundError,
            TipoDocumentoNotFoundError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(
        exc,
        (
            EmpresaInactiveError,
            CargoInactiveError,
            TipoDocumentoInactiveError,
            InvalidDocumentPairError,
            InvalidPhoneError,
            SameContactFusionError,
        ),
    ):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if isinstance(
        exc,
        (DuplicateDocumentError, SameCompanyError, ContactoPersistenceConflictError),
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    raise exc


@router.post(
    "", response_model=ContactoResponse, status_code=status.HTTP_201_CREATED
)
async def crear_contacto(
    data: ContactoCreate,
    actor: Usuario = Depends(require_permission(MODULO_CONTACTOS, PERMISO_CREAR)),
    db: AsyncSession = Depends(get_db),
) -> ContactoResponse:
    try:
        return await ContactoService(db).crear_contacto(data=data, actor=actor)
    except ContactoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("", response_model=ContactoPage)
async def listar_contactos(
    search: str | None = Query(default=None, max_length=120),
    id_empresa: int | None = Query(default=None, gt=0),
    id_cargo: int | None = Query(default=None, gt=0),
    numero_documento: str | None = Query(default=None, max_length=30),
    estado: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    actor: Usuario = Depends(
        require_permission(MODULO_CONTACTOS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ContactoPage:
    return await ContactoService(db).listar_contactos(
        search=search,
        id_empresa=id_empresa,
        id_cargo=id_cargo,
        numero_documento=numero_documento,
        estado=estado,
        page=page,
        page_size=page_size,
    )


@router.get("/exportar")
async def exportar_contactos(
    search: str | None = Query(default=None, max_length=120),
    id_empresa: int | None = Query(default=None, gt=0),
    id_cargo: int | None = Query(default=None, gt=0),
    numero_documento: str | None = Query(default=None, max_length=30),
    estado: bool | None = Query(default=None),
    actor: Usuario = Depends(
        require_permission(MODULO_CONTACTOS, PERMISO_EXPORTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    contactos = await ContactoService(db).listar_para_exportar(
        search=search,
        id_empresa=id_empresa,
        id_cargo=id_cargo,
        numero_documento=numero_documento,
        estado=estado,
    )
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "id_contacto",
            "empresa",
            "cargo",
            "tipo_documento",
            "numero_documento",
            "apellidos",
            "nombres",
            "genero",
            "celular",
            "correo",
            "estado",
        ]
    )
    for contacto in contactos:
        writer.writerow(
            [
                contacto.id_contacto,
                contacto.nombre_empresa,
                contacto.nombre_cargo or "",
                contacto.nombre_tipo_documento or "",
                contacto.numero_documento or "",
                contacto.apellidos,
                contacto.nombres,
                contacto.genero,
                contacto.celular or "",
                str(contacto.correo or ""),
                contacto.estado,
            ]
        )
    content = "\ufeff" + output.getvalue()
    return StreamingResponse(
        iter([content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="contactos.csv"'
        },
    )


@router.post("/fusionar", response_model=ContactoResponse)
async def fusionar_contactos(
    data: ContactoFusionRequest,
    actor: Usuario = Depends(
        require_permission(MODULO_CONTACTOS, PERMISO_FUSIONAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ContactoResponse:
    try:
        return await ContactoService(db).fusionar_contactos(data=data, actor=actor)
    except ContactoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get("/{id_contacto}", response_model=ContactoResponse)
async def obtener_contacto(
    id_contacto: int,
    actor: Usuario = Depends(
        require_permission(MODULO_CONTACTOS, PERMISO_CONSULTAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ContactoResponse:
    try:
        return await ContactoService(db).obtener_contacto(id_contacto)
    except ContactoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/{id_contacto}", response_model=ContactoResponse)
async def actualizar_contacto(
    id_contacto: int,
    data: ContactoUpdate,
    actor: Usuario = Depends(
        require_permission(MODULO_CONTACTOS, PERMISO_ACTUALIZAR)
    ),
    db: AsyncSession = Depends(get_db),
) -> ContactoResponse:
    try:
        return await ContactoService(db).actualizar_contacto(
            id_contacto=id_contacto, data=data, actor=actor
        )
    except ContactoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/{id_contacto}/estado", response_model=ContactoResponse)
async def cambiar_estado_contacto(
    id_contacto: int,
    data: ContactoEstadoUpdate,
    actor: Usuario = Depends(
        require_permission(MODULO_CONTACTOS, PERMISO_CAMBIAR_ESTADO)
    ),
    db: AsyncSession = Depends(get_db),
) -> ContactoResponse:
    try:
        return await ContactoService(db).cambiar_estado(
            id_contacto=id_contacto,
            estado=data.estado,
            motivo=data.motivo,
            actor=actor,
        )
    except ContactoServiceError as exc:
        _raise_http_error(exc)
        raise


@router.patch("/{id_contacto}/empresa", response_model=ContactoResponse)
async def cambiar_empresa_contacto(
    id_contacto: int,
    data: ContactoCambiarEmpresaRequest,
    actor: Usuario = Depends(
        require_permission(MODULO_CONTACTOS, PERMISO_CAMBIAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> ContactoResponse:
    try:
        return await ContactoService(db).cambiar_empresa(
            id_contacto=id_contacto, data=data, actor=actor
        )
    except ContactoServiceError as exc:
        _raise_http_error(exc)
        raise
