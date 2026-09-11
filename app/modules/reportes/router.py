"""Endpoints especializados de consulta y exportación de reportes."""

from datetime import date
from io import BytesIO

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.modules.eventos.models import EventoEstado, EventoModalidad
from app.modules.reportes.dto import (
    AcreditacionReporteResponse,
    BeneficioReporteResponse,
    DashboardReporteResponse,
    DetalleReporteListResponse,
    DistribucionCategoriaResponse,
    DistribucionGrupoResponse,
    EmpresaReporteListResponse,
    EventoSelectorResponse,
    ParticipanteReporteListResponse,
    ProgramacionReporteResponse,
    ReporteAlcance,
    ReporteClasificacion,
    ReporteEventoFiltros,
    ReporteFiltrosResponse,
    ReporteKpisResponse,
    ReporteOrden,
    ReporteTipoParticipante,
    SerieMensualResponse,
)
from app.modules.reportes.service import (
    EventoReporteNotFoundError,
    ReporteExportLimitError,
    ReporteFiltroInconsistenteError,
    ReporteService,
    ReporteServiceError,
)
from app.modules.usuarios.dependencies import require_permission
from app.modules.usuarios.models import Usuario


MODULO_REPORTES = "REPORTES"
PERMISO_CONSULTAR = "CONSULTAR_REPORTE_EVENTO"
PERMISO_PII = "CONSULTAR_DATOS_PERSONALES_REPORTE"
PERMISO_EXPORTAR = "EXPORTAR_REPORTE_EVENTO"

router = APIRouter(prefix="/reportes", tags=["Reportes"])


def _raise_http_error(exc: ReporteServiceError) -> None:
    detail = {
        "mensaje": str(exc),
        "codigo": exc.codigo,
        "campo": exc.campo,
    }
    if isinstance(exc, EventoReporteNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if isinstance(exc, ReporteExportLimitError):
        raise HTTPException(status_code=status.HTTP_413_CONTENT_TOO_LARGE, detail=detail)
    if isinstance(exc, ReporteFiltroInconsistenteError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def reporte_filtros(
    id_programacion_evento: int | None = Query(default=None, gt=0),
    id_grupo: int | None = Query(default=None, gt=0),
    id_categoria: int | None = Query(default=None, gt=0),
    id_detalle_categoria: int | None = Query(default=None, gt=0),
    id_empresa: int | None = Query(default=None, gt=0),
    id_cargo: int | None = Query(default=None, gt=0),
    estado_afiliacion: bool | None = Query(default=None),
    estado_participacion: bool | None = Query(default=None),
    asistencia: bool | None = Query(default=None),
    id_beneficio: int | None = Query(default=None, gt=0),
    requiere_coordinacion: bool | None = Query(default=None),
    tipo_participante: ReporteTipoParticipante | None = Query(default=None),
    modalidad: EventoModalidad | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    alcance: ReporteAlcance = Query(default=ReporteAlcance.VIGENTE),
    clasificacion: ReporteClasificacion = Query(default=ReporteClasificacion.ACTUAL),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    sort: str | None = Query(default=None, max_length=50),
    order: ReporteOrden = Query(default=ReporteOrden.ASC),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> ReporteEventoFiltros:
    return ReporteEventoFiltros(
        id_programacion_evento=id_programacion_evento,
        id_grupo=id_grupo,
        id_categoria=id_categoria,
        id_detalle_categoria=id_detalle_categoria,
        id_empresa=id_empresa,
        id_cargo=id_cargo,
        estado_afiliacion=estado_afiliacion,
        estado_participacion=estado_participacion,
        asistencia=asistencia,
        id_beneficio=id_beneficio,
        requiere_coordinacion=requiere_coordinacion,
        tipo_participante=tipo_participante,
        modalidad=modalidad,
        search=search,
        alcance=alcance,
        clasificacion=clasificacion,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/eventos",
    response_model=EventoSelectorResponse,
    summary="Listar eventos disponibles para reportes",
    description="Selector paginado de eventos por ID, estado, área y vigencia de política.",
)
async def listar_eventos(
    search: str | None = Query(default=None, max_length=200),
    estado: EventoEstado | None = Query(default=None),
    fecha_desde: date | None = Query(default=None),
    fecha_hasta: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="nombre_evento"),
    order: ReporteOrden = Query(default=ReporteOrden.ASC),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> EventoSelectorResponse:
    try:
        return await ReporteService(db).listar_eventos(
            search=search, estado=estado, fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta, page=page, page_size=page_size,
            sort=sort, order=order,
        )
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/filtros",
    response_model=ReporteFiltrosResponse,
    summary="Obtener filtros contextualizados",
    description="Devuelve solo opciones presentes dentro del evento y filtros seleccionados.",
)
async def obtener_filtros(
    id_evento: int = Path(gt=0),
    filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> ReporteFiltrosResponse:
    try:
        return await ReporteService(db).obtener_filtros(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/kpis",
    response_model=ReporteKpisResponse,
    summary="Obtener indicadores del evento",
    description="Calcula KPIs agregados en PostgreSQL sin cargar el detalle completo.",
)
async def obtener_kpis(
    id_evento: int = Path(gt=0),
    filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> ReporteKpisResponse:
    try:
        return await ReporteService(db).obtener_kpis(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/grupos", response_model=DistribucionGrupoResponse,
    summary="Distribuir métricas por grupo",
    description="Conserva empresas afiliadas aunque aún no tengan participantes.",
)
async def obtener_grupos(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> DistribucionGrupoResponse:
    try:
        return await ReporteService(db).obtener_grupos(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/categorias", response_model=DistribucionCategoriaResponse,
    summary="Distribuir métricas por categoría y grupo",
    description="El grano es DetalleCategoria; una categoría compartida mantiene cada contexto de grupo.",
)
async def obtener_categorias(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> DistribucionCategoriaResponse:
    try:
        return await ReporteService(db).obtener_categorias(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/empresas", response_model=EmpresaReporteListResponse,
    summary="Listar empresas afiliadas del evento",
    description="Parte de EventoEmpresa y preserva afiliaciones sin participantes.",
)
async def obtener_empresas(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> EmpresaReporteListResponse:
    try:
        return await ReporteService(db).obtener_empresas(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/participantes", response_model=ParticipanteReporteListResponse,
    summary="Listar participantes con datos personales",
    description="Una fila por EventoContacto; requiere permiso explícito de PII.",
)
async def obtener_participantes(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_PII)),
    db: AsyncSession = Depends(get_db),
) -> ParticipanteReporteListResponse:
    try:
        return await ReporteService(db).obtener_participantes(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/programaciones", response_model=ProgramacionReporteResponse,
    summary="Obtener programaciones, agenda y responsables",
    description="Compone granos separados para evitar productos cartesianos.",
)
async def obtener_programaciones(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> ProgramacionReporteResponse:
    try:
        return await ReporteService(db).obtener_programaciones(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/detalle", response_model=DetalleReporteListResponse,
    summary="Obtener detalle operativo plano",
    description="Detalle paginado por participación para operación, Excel y BI futuro.",
)
async def obtener_detalle(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_PII)),
    db: AsyncSession = Depends(get_db),
) -> DetalleReporteListResponse:
    try:
        return await ReporteService(db).obtener_detalle(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/dashboard", response_model=DashboardReporteResponse,
    summary="Obtener dashboard compacto",
    description="Reutiliza las mismas métricas, series y distribuciones de los endpoints especializados.",
)
async def obtener_dashboard(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> DashboardReporteResponse:
    try:
        return await ReporteService(db).obtener_dashboard(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/series/mensual", response_model=SerieMensualResponse,
    summary="Obtener series mensuales",
    description="Agrupa dentro de un único evento y declara la fuente temporal de cada serie.",
)
async def obtener_series(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> SerieMensualResponse:
    try:
        return await ReporteService(db).obtener_series(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/beneficios", response_model=BeneficioReporteResponse,
    summary="Obtener consumo de beneficios",
    description="Respeta las reglas POR_EVENTO, POR_ANIO y SIN_BENEFICIO existentes.",
)
async def obtener_beneficios(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> BeneficioReporteResponse:
    try:
        return await ReporteService(db).obtener_beneficios(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/acreditacion", response_model=AcreditacionReporteResponse,
    summary="Obtener métricas de acreditación",
    description="Reporta estados de QR y credencial sin exponer códigos secretos.",
)
async def obtener_acreditacion(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_CONSULTAR)),
    db: AsyncSession = Depends(get_db),
) -> AcreditacionReporteResponse:
    try:
        return await ReporteService(db).obtener_acreditacion(id_evento, filtros)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise


@router.get(
    "/eventos/{id_evento}/exportar",
    summary="Exportar reporte integral a Excel",
    description="Genera seis hojas con los mismos filtros de la API y audita la descarga.",
    response_class=StreamingResponse,
)
async def exportar_reporte(
    id_evento: int = Path(gt=0), filtros: ReporteEventoFiltros = Depends(reporte_filtros),
    actor: Usuario = Depends(require_permission(MODULO_REPORTES, PERMISO_EXPORTAR)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    try:
        content = await ReporteService(db).exportar(id_evento, filtros, actor)
    except ReporteServiceError as exc:
        _raise_http_error(exc)
        raise
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="reporte-evento-{id_evento}.xlsx"'},
    )
