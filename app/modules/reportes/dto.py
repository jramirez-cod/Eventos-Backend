from datetime import date, datetime, time
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.modules.eventos.models import EventoEstado, EventoModalidad
from app.modules.maestros.models import TipoCalculoBeneficio


class ReporteAlcance(str, Enum):
    VIGENTE = "VIGENTE"
    HISTORICO = "HISTORICO"


class ReporteClasificacion(str, Enum):
    ACTUAL = "ACTUAL"
    FECHA_PROGRAMACION = "FECHA_PROGRAMACION"


class ReporteTipoParticipante(str, Enum):
    CONTACTO = "CONTACTO"
    INVITADO = "INVITADO"


class ReporteOrden(str, Enum):
    ASC = "asc"
    DESC = "desc"


class CalidadDato(str, Enum):
    DATO_ESTRUCTURADO = "DATO_ESTRUCTURADO"
    INFERIDO = "INFERIDO"
    NO_DISPONIBLE = "NO_DISPONIBLE"


class ReporteEventoFiltros(BaseModel):
    id_programacion_evento: int | None = Field(default=None, gt=0)
    id_grupo: int | None = Field(default=None, gt=0)
    id_categoria: int | None = Field(default=None, gt=0)
    id_detalle_categoria: int | None = Field(default=None, gt=0)
    id_empresa: int | None = Field(default=None, gt=0)
    id_cargo: int | None = Field(default=None, gt=0)
    estado_afiliacion: bool | None = None
    estado_participacion: bool | None = None
    asistencia: bool | None = None
    id_beneficio: int | None = Field(default=None, gt=0)
    requiere_coordinacion: bool | None = None
    tipo_participante: ReporteTipoParticipante | None = None
    modalidad: EventoModalidad | None = None
    search: str | None = Field(default=None, max_length=200)
    alcance: ReporteAlcance = ReporteAlcance.VIGENTE
    clasificacion: ReporteClasificacion = ReporteClasificacion.ACTUAL
    fecha_desde: date | None = None
    fecha_hasta: date | None = None
    sort: str | None = Field(default=None, max_length=50)
    order: ReporteOrden = ReporteOrden.ASC
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)

    @field_validator("search", mode="before")
    @classmethod
    def limpiar_search(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def validar_rango(self) -> "ReporteEventoFiltros":
        if (
            self.fecha_desde is not None
            and self.fecha_hasta is not None
            and self.fecha_hasta < self.fecha_desde
        ):
            raise ValueError("fecha_hasta no puede ser anterior a fecha_desde.")
        return self


class ReporteContexto(BaseModel):
    alcance: ReporteAlcance
    clasificacion: ReporteClasificacion
    fecha_referencia: date | None = None
    filtros_aplicados: dict[str, object]


class DisponibilidadCampo(BaseModel):
    disponible: bool
    motivo: str | None = None


class DisponibilidadDatos(BaseModel):
    confirmacion: DisponibilidadCampo
    asistencia_por_dia: DisponibilidadCampo
    canal_asistencia_hibrida: DisponibilidadCampo
    excedentes: DisponibilidadCampo


class MetricaValor(BaseModel):
    valor: int | float | None
    disponible: bool = True
    calidad: CalidadDato = CalidadDato.DATO_ESTRUCTURADO
    grano: str
    definicion: str


class CoberturaResponse(BaseModel):
    tipo_universo: str
    numerador: int
    denominador: int
    porcentaje: float | None


class AreaReporte(BaseModel):
    id_area: int
    nombre_area: str


class EventoSelectorItem(BaseModel):
    id_evento: int
    nombre_evento: str
    descripcion: str | None
    estado: EventoEstado
    area: AreaReporte
    fecha_inicio: date
    fecha_fin: date


class EventoSelectorResponse(BaseModel):
    items: list[EventoSelectorItem]
    total: int
    page: int
    page_size: int
    pages: int


class EventoReporteCabecera(BaseModel):
    id_evento: int
    nombre_evento: str
    descripcion: str | None
    estado: EventoEstado
    area: AreaReporte
    fecha_inicio: date
    fecha_fin: date
    flyer_url: str | None


class ReporteKpis(BaseModel):
    total_programaciones: MetricaValor
    total_dias: MetricaValor
    total_empresas_afiliadas: MetricaValor
    total_empresas_unicas: MetricaValor
    total_empresas_representadas: MetricaValor
    total_participaciones: MetricaValor
    total_contactos_maestros: MetricaValor
    total_invitados: MetricaValor
    contactos_unicos: MetricaValor
    total_asistencias: MetricaValor
    total_sin_asistencia: MetricaValor
    asignaciones_beneficio: MetricaValor
    requieren_coordinacion: MetricaValor
    qr_generados: MetricaValor
    qr_enviados: MetricaValor
    qr_pendientes: MetricaValor
    credenciales_impresas: MetricaValor
    credenciales_no_impresas: MetricaValor
    cobertura_afiliadas: CoberturaResponse
    cobertura_universo: CoberturaResponse


class ReporteKpisResponse(BaseModel):
    contexto: ReporteContexto
    kpis: ReporteKpis
    disponibilidad_datos: DisponibilidadDatos
    advertencias: list[str]


class FiltroOpcion(BaseModel):
    id: int
    label: str


class CategoriaFiltroOpcion(BaseModel):
    id_detalle_categoria: int
    id_grupo: int
    nombre_grupo: str
    id_categoria: int
    nombre_categoria: str


class ReporteFiltrosResponse(BaseModel):
    contexto: ReporteContexto
    programaciones: list[FiltroOpcion]
    grupos: list[FiltroOpcion]
    categorias: list[CategoriaFiltroOpcion]
    empresas: list[FiltroOpcion]
    cargos: list[FiltroOpcion]
    beneficios: list[FiltroOpcion]
    modalidades: list[EventoModalidad]
    has_more: dict[str, bool]


class DistribucionGrupoItem(BaseModel):
    id_grupo: int
    nombre_grupo: str
    afiliaciones: int
    empresas_unicas: int
    empresas_representadas: int
    participaciones: int
    asistencias: int
    sin_asistencia: int
    asignaciones_beneficio: int
    requieren_coordinacion: int
    cobertura_afiliadas: CoberturaResponse
    cobertura_universo: CoberturaResponse


class DistribucionCategoriaItem(BaseModel):
    id_detalle_categoria: int
    id_grupo: int
    nombre_grupo: str
    id_categoria: int
    nombre_categoria: str
    afiliaciones: int
    empresas_unicas: int
    empresas_representadas: int
    participaciones: int
    asistencias: int
    sin_asistencia: int
    asignaciones_beneficio: int
    requieren_coordinacion: int
    cobertura_afiliadas: CoberturaResponse
    cobertura_universo: CoberturaResponse


class DistribucionGrupoResponse(BaseModel):
    contexto: ReporteContexto
    items: list[DistribucionGrupoItem]
    advertencias: list[str]


class DistribucionCategoriaResponse(BaseModel):
    contexto: ReporteContexto
    items: list[DistribucionCategoriaItem]
    advertencias: list[str]


class ClasificacionReporte(BaseModel):
    id_detalle_categoria: int | None
    id_grupo: int | None
    nombre_grupo: str | None
    id_categoria: int | None
    nombre_categoria: str | None
    fuente: ReporteClasificacion
    fecha_referencia: date | None = None


class EmpresaReporteItem(BaseModel):
    id_empresa: int
    nombre_empresa: str
    ruc: str
    razon_social: str | None
    nombre_comercial: str | None
    estado_empresa: bool
    estado_afiliacion: bool
    clasificacion: ClasificacionReporte
    programaciones: list[int]
    afiliaciones: int
    participantes: int
    asistentes: int
    sin_asistencia: int
    beneficios: int
    requieren_coordinacion: int
    qr_generados: int
    qr_enviados: int
    credenciales_impresas: int


class EmpresaReporteListResponse(BaseModel):
    contexto: ReporteContexto
    items: list[EmpresaReporteItem]
    total: int
    page: int
    page_size: int
    pages: int
    advertencias: list[str]


class ParticipanteReporteItem(BaseModel):
    id_evento_contacto: int
    id_programacion_evento: int
    modalidad_programacion: EventoModalidad
    modalidad_asistencia: str
    tipo_participante: ReporteTipoParticipante
    id_contacto: int | None
    id_tipo_documento: int | None
    tipo_documento: str | None
    numero_documento: str | None
    nombres: str
    apellidos: str
    nombre_completo: str
    genero: str | None
    id_cargo: int | None
    nombre_cargo: str | None
    correo: str | None
    celular: str | None
    id_empresa: int
    nombre_empresa: str
    clasificacion: ClasificacionReporte
    estado_participacion: bool
    asistencia: bool
    hora_ingreso: datetime | None
    id_beneficio: int | None
    nombre_beneficio: str | None
    tipo_calculo_beneficio: TipoCalculoBeneficio | None
    requiere_coordinacion: bool
    qr_generado: bool
    qr_enviado: bool
    qr_estado: bool | None
    credencial_impresa: bool


class ParticipanteReporteListResponse(BaseModel):
    contexto: ReporteContexto
    items: list[ParticipanteReporteItem]
    total: int
    page: int
    page_size: int
    pages: int
    advertencias: list[str]


class DiaProgramacionReporte(BaseModel):
    id_detalle_programacion: int
    fecha: date
    hora_inicio: time
    hora_fin: time | None
    enlace: str | None
    estado: bool


class ResponsableProgramacionReporte(BaseModel):
    id_responsable_evento: int
    id_usuario: int
    nombre_usuario: str
    nombres: str
    apellidos: str
    estado: bool


class LugarReporte(BaseModel):
    id_lugar: int
    pais: str | None
    provincia: str | None
    distrito: str | None
    direccion: str | None
    estado: bool


class ProgramacionReporteItem(BaseModel):
    id_programacion_evento: int
    modalidad: EventoModalidad
    estado: EventoEstado
    enlace_general: str | None
    lugar: LugarReporte | None
    primera_fecha: date | None
    ultima_fecha: date | None
    cantidad_dias: int
    dias: list[DiaProgramacionReporte]
    responsables: list[ResponsableProgramacionReporte]
    empresas_afiliadas: int
    participaciones: int
    asistencias: int


class ProgramacionReporteResponse(BaseModel):
    contexto: ReporteContexto
    items: list[ProgramacionReporteItem]


class DetalleReporteItem(ParticipanteReporteItem):
    id_evento: int
    nombre_evento: str
    estado_evento: EventoEstado
    estado_programacion: EventoEstado
    primera_fecha_programacion: date | None


class DetalleReporteListResponse(BaseModel):
    contexto: ReporteContexto
    items: list[DetalleReporteItem]
    total: int
    page: int
    page_size: int
    pages: int
    advertencias: list[str]


class SerieDato(BaseModel):
    periodo: str
    valor: int


class SerieReporte(BaseModel):
    metrica: str
    fuente_temporal: str
    datos: list[SerieDato]


class SerieMensualResponse(BaseModel):
    contexto: ReporteContexto
    granularidad: str = "MES"
    series: list[SerieReporte]
    advertencias: list[str]


class BeneficioReporteItem(BaseModel):
    id_detalle_politica_evento: int
    id_beneficio: int
    nombre: str
    tipo_calculo: TipoCalculoBeneficio
    id_categoria: int
    nombre_categoria: str
    entradas_gratuitas: int
    personas_por_asignacion: int
    empresas_aplicables: int
    cupos_teoricos: int | None
    cupos_utilizados: int | None
    cupos_disponibles: int | None
    asignaciones: int
    requieren_coordinacion: int
    disponible: bool


class BeneficioReporteResponse(BaseModel):
    contexto: ReporteContexto
    items: list[BeneficioReporteItem]
    advertencias: list[str]


class AcreditacionReporteResponse(BaseModel):
    contexto: ReporteContexto
    qr_generados: MetricaValor
    qr_enviados: MetricaValor
    qr_pendientes: MetricaValor
    credenciales_impresas: MetricaValor
    credenciales_no_impresas: MetricaValor
    reimpresiones: MetricaValor


class DashboardReporteResponse(BaseModel):
    evento: EventoReporteCabecera
    contexto: ReporteContexto
    kpis: ReporteKpis
    serie_principal: SerieReporte
    distribuciones: dict[str, list[dict[str, object]]]
    disponibilidad_datos: DisponibilidadDatos
    advertencias: list[str]


class ReporteErrorResponse(BaseModel):
    detail: str
    codigo: str
    campo: str | None = None


class CupoAnioItem(BaseModel):
    id_evento: int
    nombre_evento: str
    estado_evento: str
    id_empresa: int
    nombre_empresa: str
    ruc: str
    id_categoria: int
    nombre_categoria: str
    id_beneficio: int
    nombre_beneficio: str
    entradas_gratuitas: int
    personas_por_asignacion: int
    cupos_totales: int
    cupos_utilizados: int
    cupos_disponibles: int


class CupoAnioResponse(BaseModel):
    items: list[CupoAnioItem]
