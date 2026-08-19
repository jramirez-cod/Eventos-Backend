from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.empresas.dto import (
    CambiarClasificacionDTO,
    ConsultaRucResponseDTO,
    EmpresaCreateDTO,
    EmpresaHistorialResponseDTO,
    EmpresaResponseDTO,
    InactivarEmpresaDTO,
)
from app.modules.empresas.repository import EmpresaRepository
from app.modules.empresas.ruc_client import RucConsultaError, RucNoEncontradoError
from app.modules.empresas.service import (
    DetalleCategoriaInvalidoError,
    DuplicateRucError,
    EmpresaNotFoundError,
    EmpresaService,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_EMPRESAS = "EMPRESAS"
PERMISO_CREAR_EMPRESA = "CREAR_EMPRESA"
PERMISO_INACTIVAR_EMPRESA = "INACTIVAR_EMPRESA"

router = APIRouter(prefix="/empresas", tags=["Empresas"])


def _to_response(empresa, grupo, categoria) -> EmpresaResponseDTO:
    return EmpresaResponseDTO(
        id_empresa=empresa.id_empresa,
        nombre_empresa=empresa.nombre_empresa,
        ruc=empresa.ruc,
        razon_social=empresa.razon_social,
        nombre_comercial=empresa.nombre_comercial,
        estado=empresa.estado,
        id_grupo=grupo.id_grupo,
        nombre_grupo=grupo.nombre_grupo,
        id_categoria=categoria.id_categoria,
        nombre_categoria=categoria.nombre_categoria,
    )


@router.get("", response_model=list[EmpresaResponseDTO])
async def listar_empresas(
    nombre: str | None = Query(default=None),
    ruc: str | None = Query(default=None),
    id_grupo: int | None = Query(default=None),
    id_categoria: int | None = Query(default=None),
    estado: bool | None = Query(default=None),
    actor: Usuario = Depends(
        require_permission(MODULO_EMPRESAS, PERMISO_CREAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[EmpresaResponseDTO]:
    filas = await EmpresaRepository(db).list_all_detallado(
        nombre=nombre,
        ruc=ruc,
        id_grupo=id_grupo,
        id_categoria=id_categoria,
        estado=estado,
    )
    return [_to_response(empresa, grupo, categoria) for empresa, grupo, categoria in filas]


@router.get("/consultar-ruc/{ruc}", response_model=ConsultaRucResponseDTO)
async def consultar_ruc(
    ruc: Annotated[str, Path(pattern=r"^\d{11}$")],
    actor: Usuario = Depends(
        require_permission(MODULO_EMPRESAS, PERMISO_CREAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> ConsultaRucResponseDTO:
    try:
        info = await EmpresaService(db).consultar_ruc(ruc)
    except RucNoEncontradoError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="RUC no encontrado."
        )
    except RucConsultaError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No se pudo consultar el RUC en este momento.",
        )

    return ConsultaRucResponseDTO(
        ruc=info.ruc,
        razon_social=info.razon_social,
        tipo_contribuyente=info.tipo_contribuyente,
        estado=info.estado,
        condicion=info.condicion,
        direccion=info.direccion,
    )


@router.post(
    "", response_model=EmpresaResponseDTO, status_code=status.HTTP_201_CREATED
)
async def crear_empresa(
    data: EmpresaCreateDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_EMPRESAS, PERMISO_CREAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EmpresaResponseDTO:
    try:
        empresa, grupo, categoria = await EmpresaService(db).crear_empresa(
            data=data, actor=actor
        )
    except DuplicateRucError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="El RUC ya está registrado."
        )
    except DetalleCategoriaInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )

    return _to_response(empresa, grupo, categoria)


@router.patch("/{id_empresa}/inactivar", response_model=EmpresaResponseDTO)
async def inactivar_empresa(
    id_empresa: int,
    data: InactivarEmpresaDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_EMPRESAS, PERMISO_INACTIVAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EmpresaResponseDTO:
    try:
        await EmpresaService(db).inactivar_empresa(
            id_empresa=id_empresa, motivo=data.motivo, actor=actor
        )
    except EmpresaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada."
        )

    detallado = await EmpresaRepository(db).get_detallado(id_empresa)
    assert detallado is not None
    return _to_response(*detallado)


@router.patch("/{id_empresa}/reactivar", response_model=EmpresaResponseDTO)
async def reactivar_empresa(
    id_empresa: int,
    actor: Usuario = Depends(
        require_permission(MODULO_EMPRESAS, PERMISO_INACTIVAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EmpresaResponseDTO:
    try:
        await EmpresaService(db).reactivar_empresa(id_empresa=id_empresa, actor=actor)
    except EmpresaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada."
        )

    detallado = await EmpresaRepository(db).get_detallado(id_empresa)
    assert detallado is not None
    return _to_response(*detallado)


@router.patch("/{id_empresa}/clasificacion", response_model=EmpresaResponseDTO)
async def cambiar_clasificacion(
    id_empresa: int,
    data: CambiarClasificacionDTO,
    actor: Usuario = Depends(
        require_permission(MODULO_EMPRESAS, PERMISO_CREAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> EmpresaResponseDTO:
    try:
        empresa, grupo, categoria = await EmpresaService(db).cambiar_clasificacion(
            id_empresa=id_empresa, data=data, actor=actor
        )
    except EmpresaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada."
        )
    except DetalleCategoriaInvalidoError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        )

    return _to_response(empresa, grupo, categoria)


@router.get(
    "/{id_empresa}/historial", response_model=list[EmpresaHistorialResponseDTO]
)
async def listar_historial(
    id_empresa: int,
    actor: Usuario = Depends(
        require_permission(MODULO_EMPRESAS, PERMISO_CREAR_EMPRESA)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[EmpresaHistorialResponseDTO]:
    try:
        filas = await EmpresaService(db).listar_historial(id_empresa)
    except EmpresaNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Empresa no encontrada."
        )

    return [
        EmpresaHistorialResponseDTO(
            id_historial=historial.id_historial,
            id_detalle_categoria=historial.id_detalle_categoria,
            nombre_grupo=grupo.nombre_grupo,
            nombre_categoria=categoria.nombre_categoria,
            fecha_inicio=historial.fecha_inicio,
            fecha_fin=historial.fecha_fin,
        )
        for historial, grupo, categoria in filas
    ]
