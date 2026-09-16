"""Consultas de solo lectura para los reportes de eventos."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import (
    Select,
    String,
    and_,
    case,
    cast,
    func,
    literal,
    or_,
    select,
    true,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.contactos.models import Contacto
from app.modules.empresas.models import Empresa, EmpresaHistorialClasificacion
from app.modules.eventos.models import (
    DetallePoliticaEvento,
    DetalleProgramacionEvento,
    Evento,
    Lugar,
    PoliticaEvento,
    ProgramacionEvento,
    ResponsableEvento,
)
from app.modules.grupos.models import Grupo
from app.modules.maestros.models import Area, Beneficio, Cargo, TipoCalculoBeneficio
from app.modules.participantes.models import (
    AsignacionBeneficio,
    EventoContacto,
    EventoEmpresa,
    ParticipanteQr,
)
from app.modules.reportes.dto import (
    ReporteAlcance,
    ReporteClasificacion,
    ReporteEventoFiltros,
    ReporteOrden,
    ReporteTipoParticipante,
)
from app.modules.usuarios.models import TipoDocumento, Usuario


@dataclass(frozen=True, slots=True)
class EventoReporteDetalle:
    evento: Evento
    area: Area
    politica: PoliticaEvento


class ReporteRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_evento(self, id_evento: int) -> EventoReporteDetalle | None:
        stmt = (
            select(Evento, Area, PoliticaEvento)
            .join(Area, Area.id_area == Evento.id_area)
            .join(
                PoliticaEvento,
                PoliticaEvento.id_politica_evento == Evento.id_politica_evento,
            )
            .where(Evento.id_evento == id_evento)
        )
        row = (await self.db.execute(stmt)).first()
        return EventoReporteDetalle(row[0], row[1], row[2]) if row else None

    async def list_eventos(
        self,
        *,
        search: str | None,
        estado: Any,
        fecha_desde: date | None,
        fecha_hasta: date | None,
        page: int,
        page_size: int,
        sort: str,
        order: ReporteOrden,
    ) -> tuple[list[dict[str, Any]], int]:
        filters: list[Any] = []
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    Evento.nombre_evento.ilike(pattern),
                    Evento.descripcion.ilike(pattern),
                )
            )
        if estado is not None:
            filters.append(Evento.estado == estado)
        if fecha_desde is not None:
            filters.append(PoliticaEvento.fecha_fin >= fecha_desde)
        if fecha_hasta is not None:
            filters.append(PoliticaEvento.fecha_inicio <= fecha_hasta)

        base = (
            select(
                Evento.id_evento,
                Evento.nombre_evento,
                Evento.descripcion,
                Evento.estado,
                Area.id_area,
                Area.nombre_area,
                PoliticaEvento.fecha_inicio,
                PoliticaEvento.fecha_fin,
            )
            .join(Area, Area.id_area == Evento.id_area)
            .join(
                PoliticaEvento,
                PoliticaEvento.id_politica_evento == Evento.id_politica_evento,
            )
            .where(*filters)
        )
        total = int(
            await self.db.scalar(select(func.count()).select_from(base.subquery())) or 0
        )
        sort_columns = {
            "nombre_evento": Evento.nombre_evento,
            "estado": Evento.estado,
            "fecha_inicio": PoliticaEvento.fecha_inicio,
        }
        column = sort_columns[sort]
        direction = column.desc() if order == ReporteOrden.DESC else column.asc()
        stmt = (
            base.order_by(direction, Evento.id_evento.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return [dict(row) for row in (await self.db.execute(stmt)).mappings()], total

    async def programacion_pertenece(
        self, *, id_evento: int, id_programacion_evento: int
    ) -> bool:
        stmt = select(
            select(ProgramacionEvento.id_programacion_evento)
            .where(
                ProgramacionEvento.id_evento == id_evento,
                ProgramacionEvento.id_programacion_evento
                == id_programacion_evento,
            )
            .exists()
        )
        return bool(await self.db.scalar(stmt))

    async def detalle_categoria_valido(
        self,
        *,
        id_detalle_categoria: int,
        id_grupo: int | None,
        id_categoria: int | None,
    ) -> bool:
        filters: list[Any] = [
            DetalleCategoria.id_detalle_categoria == id_detalle_categoria
        ]
        if id_grupo is not None:
            filters.append(DetalleCategoria.id_grupo == id_grupo)
        if id_categoria is not None:
            filters.append(DetalleCategoria.id_categoria == id_categoria)
        return bool(
            await self.db.scalar(
                select(select(DetalleCategoria.id_detalle_categoria).where(*filters).exists())
            )
        )

    async def grupo_categoria_valido(
        self, *, id_grupo: int, id_categoria: int
    ) -> bool:
        return bool(
            await self.db.scalar(
                select(
                    select(DetalleCategoria.id_detalle_categoria)
                    .where(
                        DetalleCategoria.id_grupo == id_grupo,
                        DetalleCategoria.id_categoria == id_categoria,
                    )
                    .exists()
                )
            )
        )

    async def empresa_afiliada(
        self, *, id_evento: int, id_empresa: int, filtros: ReporteEventoFiltros
    ) -> bool:
        subq = self._affiliation_select(id_evento, filtros).subquery()
        return bool(
            await self.db.scalar(
                select(
                    select(subq.c.id_evento_empresa)
                    .where(subq.c.id_empresa == id_empresa)
                    .exists()
                )
            )
        )

    def _first_day(self, filtros: ReporteEventoFiltros) -> Any:
        conditions = [
            DetalleProgramacionEvento.id_programacion_evento
            == ProgramacionEvento.id_programacion_evento
        ]
        if filtros.alcance == ReporteAlcance.VIGENTE:
            conditions.append(DetalleProgramacionEvento.estado.is_(True))
        return (
            select(func.min(DetalleProgramacionEvento.fecha))
            .where(*conditions)
            .correlate(ProgramacionEvento)
            .scalar_subquery()
        )

    def _classification_expr(
        self, filtros: ReporteEventoFiltros, *, company_column: Any
    ) -> tuple[Any, Any]:
        first_day = self._first_day(filtros)
        if filtros.clasificacion == ReporteClasificacion.ACTUAL:
            return company_column, first_day
        historical = (
            select(EmpresaHistorialClasificacion.id_detalle_categoria)
            .where(
                EmpresaHistorialClasificacion.id_empresa == company_column,
                func.date(EmpresaHistorialClasificacion.fecha_inicio) <= first_day,
                or_(
                    EmpresaHistorialClasificacion.fecha_fin.is_(None),
                    func.date(EmpresaHistorialClasificacion.fecha_fin) > first_day,
                ),
            )
            .order_by(EmpresaHistorialClasificacion.fecha_inicio.desc())
            .limit(1)
            .correlate(Empresa, ProgramacionEvento)
            .scalar_subquery()
        )
        return historical, first_day

    def _program_conditions(
        self,
        id_evento: int,
        filtros: ReporteEventoFiltros,
        *,
        include_date_overlap: bool = True,
    ) -> list[Any]:
        conditions: list[Any] = [ProgramacionEvento.id_evento == id_evento]
        if filtros.id_programacion_evento is not None:
            conditions.append(
                ProgramacionEvento.id_programacion_evento
                == filtros.id_programacion_evento
            )
        if filtros.modalidad is not None:
            conditions.append(ProgramacionEvento.modalidad == filtros.modalidad)
        if include_date_overlap and (
            filtros.fecha_desde is not None or filtros.fecha_hasta is not None
        ):
            day_conditions: list[Any] = [
                DetalleProgramacionEvento.id_programacion_evento
                == ProgramacionEvento.id_programacion_evento
            ]
            if filtros.alcance == ReporteAlcance.VIGENTE:
                day_conditions.append(DetalleProgramacionEvento.estado.is_(True))
            if filtros.fecha_desde is not None:
                day_conditions.append(
                    DetalleProgramacionEvento.fecha >= filtros.fecha_desde
                )
            if filtros.fecha_hasta is not None:
                day_conditions.append(
                    DetalleProgramacionEvento.fecha <= filtros.fecha_hasta
                )
            conditions.append(
                select(DetalleProgramacionEvento.id_detalle_programacion)
                .where(*day_conditions)
                .exists()
            )
        return conditions

    @staticmethod
    def _classification_conditions(
        filtros: ReporteEventoFiltros,
    ) -> list[Any]:
        conditions: list[Any] = []
        if filtros.id_detalle_categoria is not None:
            conditions.append(
                DetalleCategoria.id_detalle_categoria
                == filtros.id_detalle_categoria
            )
        if filtros.id_grupo is not None:
            conditions.append(DetalleCategoria.id_grupo == filtros.id_grupo)
        if filtros.id_categoria is not None:
            conditions.append(DetalleCategoria.id_categoria == filtros.id_categoria)
        return conditions

    def _affiliation_select(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> Select[Any]:
        classification_id, first_day = self._classification_expr(
            filtros, company_column=Empresa.id_detalle_categoria
        )
        conditions = [
            *self._program_conditions(id_evento, filtros),
            ProgramacionEvento.id_evento == id_evento,
        ]
        if filtros.alcance == ReporteAlcance.VIGENTE:
            conditions.append(EventoEmpresa.estado.is_(True))
        if filtros.estado_afiliacion is not None:
            conditions.append(EventoEmpresa.estado.is_(filtros.estado_afiliacion))
        if filtros.id_empresa is not None:
            conditions.append(EventoEmpresa.id_empresa == filtros.id_empresa)
        conditions.extend(self._classification_conditions(filtros))
        if filtros.search:
            pattern = f"%{filtros.search}%"
            participant_match = (
                select(EventoContacto.id_evento_contacto)
                .outerjoin(
                    Contacto, Contacto.id_contacto == EventoContacto.id_contacto
                )
                .where(
                    EventoContacto.id_programacion_evento
                    == ProgramacionEvento.id_programacion_evento,
                    EventoContacto.id_empresa == EventoEmpresa.id_empresa,
                    or_(
                        Contacto.nombres.ilike(pattern),
                        Contacto.apellidos.ilike(pattern),
                        Contacto.numero_documento.ilike(pattern),
                        Contacto.correo.ilike(pattern),
                        Contacto.celular.ilike(pattern),
                        EventoContacto.invitado_nombres.ilike(pattern),
                        EventoContacto.invitado_apellidos.ilike(pattern),
                        EventoContacto.invitado_numero_documento.ilike(pattern),
                        EventoContacto.invitado_correo.ilike(pattern),
                        EventoContacto.invitado_celular.ilike(pattern),
                    ),
                )
                .exists()
            )
            conditions.append(
                or_(
                    Empresa.nombre_empresa.ilike(pattern),
                    Empresa.razon_social.ilike(pattern),
                    Empresa.nombre_comercial.ilike(pattern),
                    Empresa.ruc.ilike(pattern),
                    participant_match,
                )
            )
        return (
            select(
                EventoEmpresa.id_evento_empresa.label("id_evento_empresa"),
                ProgramacionEvento.id_programacion_evento.label(
                    "id_programacion_evento"
                ),
                EventoEmpresa.id_empresa.label("id_empresa"),
                EventoEmpresa.estado.label("estado_afiliacion"),
                Empresa.nombre_empresa.label("nombre_empresa"),
                Empresa.ruc.label("ruc"),
                Empresa.razon_social.label("razon_social"),
                Empresa.nombre_comercial.label("nombre_comercial"),
                Empresa.estado.label("estado_empresa"),
                classification_id.label("id_detalle_categoria"),
                DetalleCategoria.id_grupo.label("id_grupo"),
                Grupo.nombre_grupo.label("nombre_grupo"),
                DetalleCategoria.id_categoria.label("id_categoria"),
                Categoria.nombre_categoria.label("nombre_categoria"),
                ProgramacionEvento.modalidad.label("modalidad"),
                first_day.label("fecha_referencia"),
            )
            .select_from(EventoEmpresa)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == EventoEmpresa.id_programacion_evento,
            )
            .join(Empresa, Empresa.id_empresa == EventoEmpresa.id_empresa)
            .outerjoin(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == classification_id,
            )
            .outerjoin(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .outerjoin(
                Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria
            )
            .where(*conditions)
        )

    def _participation_select(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> Select[Any]:
        classification_id, first_day = self._classification_expr(
            filtros, company_column=Empresa.id_detalle_categoria
        )
        conditions = self._program_conditions(id_evento, filtros)
        if filtros.alcance == ReporteAlcance.VIGENTE:
            conditions.extend(
                [EventoContacto.estado.is_(True), EventoEmpresa.estado.is_(True)]
            )
        if filtros.estado_participacion is not None:
            conditions.append(
                EventoContacto.estado.is_(filtros.estado_participacion)
            )
        if filtros.estado_afiliacion is not None:
            conditions.append(EventoEmpresa.estado.is_(filtros.estado_afiliacion))
        if filtros.asistencia is not None:
            conditions.append(EventoContacto.asistencia_evento.is_(filtros.asistencia))
        if filtros.id_empresa is not None:
            conditions.append(EventoContacto.id_empresa == filtros.id_empresa)
        if filtros.id_cargo is not None:
            conditions.append(Contacto.id_cargo == filtros.id_cargo)
        if filtros.id_beneficio is not None:
            conditions.append(
                AsignacionBeneficio.id_beneficio == filtros.id_beneficio
            )
        if filtros.requiere_coordinacion is not None:
            conditions.append(
                EventoContacto.requiere_coordinacion.is_(
                    filtros.requiere_coordinacion
                )
            )
        if filtros.tipo_participante == ReporteTipoParticipante.CONTACTO:
            conditions.append(EventoContacto.id_contacto.is_not(None))
        if filtros.tipo_participante == ReporteTipoParticipante.INVITADO:
            conditions.append(EventoContacto.id_contacto.is_(None))
        conditions.extend(self._classification_conditions(filtros))
        if filtros.search:
            pattern = f"%{filtros.search}%"
            conditions.append(
                or_(
                    Empresa.nombre_empresa.ilike(pattern),
                    Empresa.razon_social.ilike(pattern),
                    Empresa.nombre_comercial.ilike(pattern),
                    Empresa.ruc.ilike(pattern),
                    Contacto.nombres.ilike(pattern),
                    Contacto.apellidos.ilike(pattern),
                    Contacto.numero_documento.ilike(pattern),
                    Contacto.correo.ilike(pattern),
                    Contacto.celular.ilike(pattern),
                    EventoContacto.invitado_nombres.ilike(pattern),
                    EventoContacto.invitado_apellidos.ilike(pattern),
                    EventoContacto.invitado_numero_documento.ilike(pattern),
                    EventoContacto.invitado_correo.ilike(pattern),
                    EventoContacto.invitado_celular.ilike(pattern),
                )
            )
        return (
            select(
                Evento.id_evento.label("id_evento"),
                Evento.nombre_evento.label("nombre_evento"),
                Evento.estado.label("estado_evento"),
                EventoContacto.id_evento_contacto.label("id_evento_contacto"),
                EventoContacto.id_programacion_evento.label(
                    "id_programacion_evento"
                ),
                ProgramacionEvento.modalidad.label("modalidad_programacion"),
                ProgramacionEvento.estado.label("estado_programacion"),
                first_day.label("primera_fecha_programacion"),
                EventoContacto.id_contacto.label("id_contacto"),
                Contacto.id_tipo_documento.label("id_tipo_documento"),
                TipoDocumento.nombre_documento.label("tipo_documento"),
                Contacto.numero_documento.label("contacto_numero_documento"),
                Contacto.nombres.label("contacto_nombres"),
                Contacto.apellidos.label("contacto_apellidos"),
                Contacto.genero.label("genero"),
                Contacto.id_cargo.label("id_cargo"),
                Cargo.nombre_cargo.label("nombre_cargo"),
                Contacto.correo.label("contacto_correo"),
                Contacto.celular.label("contacto_celular"),
                EventoContacto.invitado_numero_documento.label(
                    "invitado_numero_documento"
                ),
                EventoContacto.invitado_nombres.label("invitado_nombres"),
                EventoContacto.invitado_apellidos.label("invitado_apellidos"),
                EventoContacto.invitado_correo.label("invitado_correo"),
                EventoContacto.invitado_celular.label("invitado_celular"),
                EventoContacto.id_empresa.label("id_empresa"),
                Empresa.nombre_empresa.label("nombre_empresa"),
                classification_id.label("id_detalle_categoria"),
                DetalleCategoria.id_grupo.label("id_grupo"),
                Grupo.nombre_grupo.label("nombre_grupo"),
                DetalleCategoria.id_categoria.label("id_categoria"),
                Categoria.nombre_categoria.label("nombre_categoria"),
                first_day.label("fecha_referencia"),
                EventoContacto.estado.label("estado_participacion"),
                EventoContacto.asistencia_evento.label("asistencia"),
                EventoContacto.hora_ingreso.label("hora_ingreso"),
                EventoContacto.requiere_coordinacion.label(
                    "requiere_coordinacion"
                ),
                EventoContacto.credencial_impresa.label("credencial_impresa"),
                AsignacionBeneficio.id_asignacion_beneficio.label(
                    "id_asignacion_beneficio"
                ),
                AsignacionBeneficio.id_beneficio.label("id_beneficio"),
                AsignacionBeneficio.fecha_asignacion.label("fecha_asignacion"),
                AsignacionBeneficio.codigo_grupo.label("codigo_grupo"),
                Beneficio.nombre.label("nombre_beneficio"),
                Beneficio.tipo_calculo.label("tipo_calculo_beneficio"),
                ParticipanteQr.id_participante_qr.label("id_participante_qr"),
                ParticipanteQr.fecha_generacion.label("qr_fecha_generacion"),
                ParticipanteQr.fecha_envio.label("qr_fecha_envio"),
                ParticipanteQr.estado.label("qr_estado"),
            )
            .select_from(EventoContacto)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == EventoContacto.id_programacion_evento,
            )
            .join(Evento, Evento.id_evento == ProgramacionEvento.id_evento)
            .join(Empresa, Empresa.id_empresa == EventoContacto.id_empresa)
            .join(
                EventoEmpresa,
                and_(
                    EventoEmpresa.id_programacion_evento
                    == EventoContacto.id_programacion_evento,
                    EventoEmpresa.id_empresa == EventoContacto.id_empresa,
                ),
            )
            .outerjoin(Contacto, Contacto.id_contacto == EventoContacto.id_contacto)
            .outerjoin(
                TipoDocumento,
                TipoDocumento.id_tipo_documento == Contacto.id_tipo_documento,
            )
            .outerjoin(Cargo, Cargo.id_cargo == Contacto.id_cargo)
            .outerjoin(
                AsignacionBeneficio,
                AsignacionBeneficio.id_evento_contacto
                == EventoContacto.id_evento_contacto,
            )
            .outerjoin(
                Beneficio,
                Beneficio.id_beneficio == AsignacionBeneficio.id_beneficio,
            )
            .outerjoin(
                ParticipanteQr,
                ParticipanteQr.id_evento_contacto
                == EventoContacto.id_evento_contacto,
            )
            .outerjoin(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == classification_id,
            )
            .outerjoin(Grupo, Grupo.id_grupo == DetalleCategoria.id_grupo)
            .outerjoin(
                Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria
            )
            .where(*conditions)
        )

    async def get_kpi_values(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> dict[str, int]:
        p = self._participation_select(id_evento, filtros).subquery()
        a = self._affiliation_select(id_evento, filtros).subquery()

        program_conditions = self._program_conditions(id_evento, filtros)
        program_ids = select(ProgramacionEvento.id_programacion_evento).where(
            *program_conditions
        )
        day_conditions: list[Any] = [
            DetalleProgramacionEvento.id_programacion_evento.in_(program_ids)
        ]
        if filtros.alcance == ReporteAlcance.VIGENTE:
            day_conditions.append(DetalleProgramacionEvento.estado.is_(True))
        if filtros.fecha_desde is not None:
            day_conditions.append(
                DetalleProgramacionEvento.fecha >= filtros.fecha_desde
            )
        if filtros.fecha_hasta is not None:
            day_conditions.append(
                DetalleProgramacionEvento.fecha <= filtros.fecha_hasta
            )

        stmt = select(
            select(func.count())
            .select_from(program_ids.subquery())
            .scalar_subquery()
            .label("total_programaciones"),
            select(func.count())
            .select_from(DetalleProgramacionEvento)
            .where(*day_conditions)
            .scalar_subquery()
            .label("total_dias"),
            select(func.count(func.distinct(a.c.id_evento_empresa)))
            .select_from(a)
            .scalar_subquery().label(
                "total_empresas_afiliadas"
            ),
            select(func.count(func.distinct(a.c.id_empresa)))
            .select_from(a)
            .scalar_subquery()
            .label("total_empresas_unicas"),
            select(
                func.count(
                    func.distinct(case((p.c.asistencia.is_(True), p.c.id_empresa)))
                )
            )
            .select_from(p)
            .scalar_subquery()
            .label("total_empresas_representadas"),
            select(func.count()).select_from(p).scalar_subquery().label(
                "total_participaciones"
            ),
            select(func.count())
            .select_from(p)
            .where(p.c.id_contacto.is_not(None))
            .scalar_subquery()
            .label("total_contactos_maestros"),
            select(func.count())
            .select_from(p)
            .where(p.c.id_contacto.is_(None))
            .scalar_subquery()
            .label("total_invitados"),
            select(func.count(func.distinct(p.c.id_contacto)))
            .select_from(p)
            .where(p.c.id_contacto.is_not(None))
            .scalar_subquery()
            .label("contactos_unicos"),
            select(func.count())
            .select_from(p)
            .where(p.c.asistencia.is_(True))
            .scalar_subquery()
            .label("total_asistencias"),
            select(func.count())
            .select_from(p)
            .where(p.c.asistencia.is_(False))
            .scalar_subquery()
            .label("total_sin_asistencia"),
            select(func.count())
            .select_from(p)
            .where(p.c.id_asignacion_beneficio.is_not(None))
            .scalar_subquery()
            .label("asignaciones_beneficio"),
            select(func.count())
            .select_from(p)
            .where(p.c.requiere_coordinacion.is_(True))
            .scalar_subquery()
            .label("requieren_coordinacion"),
            select(func.count())
            .select_from(p)
            .where(p.c.id_participante_qr.is_not(None))
            .scalar_subquery()
            .label("qr_generados"),
            select(func.count())
            .select_from(p)
            .where(p.c.qr_fecha_envio.is_not(None))
            .scalar_subquery()
            .label("qr_enviados"),
            select(func.count())
            .select_from(p)
            .where(
                p.c.id_participante_qr.is_not(None),
                p.c.qr_fecha_envio.is_(None),
                p.c.qr_estado.is_(True),
            )
            .scalar_subquery()
            .label("qr_pendientes"),
            select(func.count())
            .select_from(p)
            .where(p.c.credencial_impresa.is_(True))
            .scalar_subquery()
            .label("credenciales_impresas"),
            select(func.count())
            .select_from(p)
            .where(p.c.credencial_impresa.is_(False))
            .scalar_subquery()
            .label("credenciales_no_impresas"),
        )
        row = (await self.db.execute(stmt)).mappings().one()
        return {key: int(value or 0) for key, value in row.items()}

    async def get_universe_count(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> int:
        conditions: list[Any] = [Empresa.estado.is_(True)]
        if filtros.id_empresa is not None:
            conditions.append(Empresa.id_empresa == filtros.id_empresa)

        if filtros.clasificacion == ReporteClasificacion.ACTUAL:
            stmt = (
                select(func.count(func.distinct(Empresa.id_empresa)))
                .select_from(Empresa)
                .join(
                    DetalleCategoria,
                    DetalleCategoria.id_detalle_categoria
                    == Empresa.id_detalle_categoria,
                )
                .where(*conditions, *self._classification_conditions(filtros))
            )
            return int(await self.db.scalar(stmt) or 0)

        program_base = select(
            ProgramacionEvento.id_programacion_evento.label("id_programacion_evento"),
            self._first_day(filtros).label("fecha_referencia"),
        ).where(*self._program_conditions(id_evento, filtros))
        programs = program_base.subquery()
        historical_id = (
            select(EmpresaHistorialClasificacion.id_detalle_categoria)
            .where(
                EmpresaHistorialClasificacion.id_empresa == Empresa.id_empresa,
                func.date(EmpresaHistorialClasificacion.fecha_inicio)
                <= programs.c.fecha_referencia,
                or_(
                    EmpresaHistorialClasificacion.fecha_fin.is_(None),
                    func.date(EmpresaHistorialClasificacion.fecha_fin)
                    > programs.c.fecha_referencia,
                ),
            )
            .order_by(EmpresaHistorialClasificacion.fecha_inicio.desc())
            .limit(1)
            .correlate(Empresa, programs)
            .scalar_subquery()
        )
        stmt = (
            select(func.count(func.distinct(Empresa.id_empresa)))
            .select_from(Empresa)
            .join(programs, true())
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == historical_id,
            )
            .where(*conditions, *self._classification_conditions(filtros))
        )
        return int(await self.db.scalar(stmt) or 0)

    async def list_distribution(
        self, id_evento: int, filtros: ReporteEventoFiltros, *, by: str
    ) -> list[dict[str, Any]]:
        a = self._affiliation_select(id_evento, filtros).subquery()
        p = self._participation_select(id_evento, filtros).subquery()
        p_company = (
            select(
                p.c.id_programacion_evento,
                p.c.id_empresa,
                func.count().label("participaciones"),
                func.count().filter(p.c.asistencia.is_(True)).label("asistencias"),
                func.count().filter(p.c.asistencia.is_(False)).label(
                    "sin_asistencia"
                ),
                func.count()
                .filter(p.c.id_asignacion_beneficio.is_not(None))
                .label("asignaciones_beneficio"),
                func.count()
                .filter(p.c.requiere_coordinacion.is_(True))
                .label("requieren_coordinacion"),
            )
            .group_by(p.c.id_programacion_evento, p.c.id_empresa)
            .subquery()
        )
        if by == "grupo":
            keys = [a.c.id_grupo, a.c.nombre_grupo]
        else:
            keys = [
                a.c.id_detalle_categoria,
                a.c.id_grupo,
                a.c.nombre_grupo,
                a.c.id_categoria,
                a.c.nombre_categoria,
            ]
        stmt = (
            select(
                *keys,
                func.count(func.distinct(a.c.id_evento_empresa)).label(
                    "afiliaciones"
                ),
                func.count(func.distinct(a.c.id_empresa)).label("empresas_unicas"),
                func.count(
                    func.distinct(
                        case(
                            (
                                func.coalesce(p_company.c.asistencias, 0) > 0,
                                a.c.id_empresa,
                            )
                        )
                    )
                ).label("empresas_representadas"),
                func.coalesce(func.sum(p_company.c.participaciones), 0).label(
                    "participaciones"
                ),
                func.coalesce(func.sum(p_company.c.asistencias), 0).label(
                    "asistencias"
                ),
                func.coalesce(func.sum(p_company.c.sin_asistencia), 0).label(
                    "sin_asistencia"
                ),
                func.coalesce(func.sum(p_company.c.asignaciones_beneficio), 0).label(
                    "asignaciones_beneficio"
                ),
                func.coalesce(func.sum(p_company.c.requieren_coordinacion), 0).label(
                    "requieren_coordinacion"
                ),
            )
            .select_from(a)
            .outerjoin(
                p_company,
                and_(
                    p_company.c.id_programacion_evento
                    == a.c.id_programacion_evento,
                    p_company.c.id_empresa == a.c.id_empresa,
                ),
            )
            .group_by(*keys)
            .order_by(keys[-1].asc())
        )
        return [dict(row) for row in (await self.db.execute(stmt)).mappings()]

    async def universe_by_classification(
        self, id_evento: int, filtros: ReporteEventoFiltros, *, by: str
    ) -> dict[Any, int]:
        keys = (
            [DetalleCategoria.id_grupo]
            if by == "grupo"
            else [DetalleCategoria.id_detalle_categoria]
        )
        if filtros.clasificacion == ReporteClasificacion.ACTUAL:
            stmt = (
                select(
                    *keys,
                    func.count(func.distinct(Empresa.id_empresa)).label("total"),
                )
                .select_from(Empresa)
                .join(
                    DetalleCategoria,
                    DetalleCategoria.id_detalle_categoria
                    == Empresa.id_detalle_categoria,
                )
                .where(
                    Empresa.estado.is_(True),
                    *self._classification_conditions(filtros),
                )
                .group_by(*keys)
            )
            return {row[0]: int(row[1]) for row in (await self.db.execute(stmt)).all()}

        programs = (
            select(
                ProgramacionEvento.id_programacion_evento.label(
                    "id_programacion_evento"
                ),
                self._first_day(filtros).label("fecha_referencia"),
            )
            .where(*self._program_conditions(id_evento, filtros))
            .subquery()
        )
        historical_id = (
            select(EmpresaHistorialClasificacion.id_detalle_categoria)
            .where(
                EmpresaHistorialClasificacion.id_empresa == Empresa.id_empresa,
                func.date(EmpresaHistorialClasificacion.fecha_inicio)
                <= programs.c.fecha_referencia,
                or_(
                    EmpresaHistorialClasificacion.fecha_fin.is_(None),
                    func.date(EmpresaHistorialClasificacion.fecha_fin)
                    > programs.c.fecha_referencia,
                ),
            )
            .order_by(EmpresaHistorialClasificacion.fecha_inicio.desc())
            .limit(1)
            .correlate(Empresa, programs)
            .scalar_subquery()
        )
        stmt = (
            select(*keys, func.count(func.distinct(Empresa.id_empresa)).label("total"))
            .select_from(Empresa)
            .join(programs, true())
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria == historical_id,
            )
            .where(
                Empresa.estado.is_(True),
                *self._classification_conditions(filtros),
            )
            .group_by(*keys)
        )
        return {row[0]: int(row[1]) for row in (await self.db.execute(stmt)).all()}

    async def list_companies(
        self,
        id_evento: int,
        filtros: ReporteEventoFiltros,
        *,
        paginated: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        a = self._affiliation_select(id_evento, filtros).subquery()
        p = self._participation_select(id_evento, filtros).subquery()
        p_company = (
            select(
                p.c.id_programacion_evento,
                p.c.id_empresa,
                func.count().label("participantes"),
                func.count().filter(p.c.asistencia.is_(True)).label("asistentes"),
                func.count().filter(p.c.asistencia.is_(False)).label("sin_asistencia"),
                func.count()
                .filter(p.c.id_asignacion_beneficio.is_not(None))
                .label("beneficios"),
                func.count()
                .filter(p.c.requiere_coordinacion.is_(True))
                .label("requieren_coordinacion"),
                func.count()
                .filter(p.c.id_participante_qr.is_not(None))
                .label("qr_generados"),
                func.count()
                .filter(p.c.qr_fecha_envio.is_not(None))
                .label("qr_enviados"),
                func.count()
                .filter(p.c.credencial_impresa.is_(True))
                .label("credenciales_impresas"),
            )
            .group_by(p.c.id_programacion_evento, p.c.id_empresa)
            .subquery()
        )
        keys = [
            a.c.id_empresa,
            a.c.nombre_empresa,
            a.c.ruc,
            a.c.razon_social,
            a.c.nombre_comercial,
            a.c.estado_empresa,
            a.c.id_detalle_categoria,
            a.c.id_grupo,
            a.c.nombre_grupo,
            a.c.id_categoria,
            a.c.nombre_categoria,
            a.c.fecha_referencia,
        ]
        grouped = (
            select(
                *keys,
                func.bool_and(a.c.estado_afiliacion).label("estado_afiliacion"),
                func.array_agg(
                    func.distinct(a.c.id_programacion_evento)
                ).label("programaciones"),
                func.count(func.distinct(a.c.id_evento_empresa)).label(
                    "afiliaciones"
                ),
                func.coalesce(func.sum(p_company.c.participantes), 0).label(
                    "participantes"
                ),
                func.coalesce(func.sum(p_company.c.asistentes), 0).label("asistentes"),
                func.coalesce(func.sum(p_company.c.sin_asistencia), 0).label(
                    "sin_asistencia"
                ),
                func.coalesce(func.sum(p_company.c.beneficios), 0).label("beneficios"),
                func.coalesce(func.sum(p_company.c.requieren_coordinacion), 0).label(
                    "requieren_coordinacion"
                ),
                func.coalesce(func.sum(p_company.c.qr_generados), 0).label(
                    "qr_generados"
                ),
                func.coalesce(func.sum(p_company.c.qr_enviados), 0).label(
                    "qr_enviados"
                ),
                func.coalesce(func.sum(p_company.c.credenciales_impresas), 0).label(
                    "credenciales_impresas"
                ),
            )
            .select_from(a)
            .outerjoin(
                p_company,
                and_(
                    p_company.c.id_programacion_evento
                    == a.c.id_programacion_evento,
                    p_company.c.id_empresa == a.c.id_empresa,
                ),
            )
            .group_by(*keys)
        )
        total = int(
            await self.db.scalar(select(func.count()).select_from(grouped.subquery()))
            or 0
        )
        result = grouped.subquery()
        sort_columns = {
            "nombre_empresa": result.c.nombre_empresa,
            "ruc": result.c.ruc,
            "participantes": result.c.participantes,
        }
        column = sort_columns.get(filtros.sort or "nombre_empresa", result.c.nombre_empresa)
        direction = (
            column.desc() if filtros.order == ReporteOrden.DESC else column.asc()
        )
        stmt = select(result).order_by(direction, result.c.id_empresa.asc())
        if paginated:
            stmt = stmt.offset((filtros.page - 1) * filtros.page_size).limit(
                filtros.page_size
            )
        rows = [dict(row) for row in (await self.db.execute(stmt)).mappings()]
        return rows, total

    async def list_participations(
        self,
        id_evento: int,
        filtros: ReporteEventoFiltros,
        *,
        paginated: bool = True,
    ) -> tuple[list[dict[str, Any]], int]:
        base = self._participation_select(id_evento, filtros)
        subq = base.subquery()
        total = int(
            await self.db.scalar(select(func.count()).select_from(subq)) or 0
        )
        sort_columns = {
            "apellidos": func.coalesce(
                subq.c.contacto_apellidos, subq.c.invitado_apellidos
            ),
            "nombres": func.coalesce(
                subq.c.contacto_nombres, subq.c.invitado_nombres
            ),
            "id_evento_contacto": subq.c.id_evento_contacto,
            "id_programacion_evento": subq.c.id_programacion_evento,
            "id_empresa": subq.c.id_empresa,
        }
        default_sort = "apellidos" if paginated else "id_programacion_evento"
        column = sort_columns.get(filtros.sort or default_sort, subq.c.id_evento_contacto)
        direction = (
            column.desc() if filtros.order == ReporteOrden.DESC else column.asc()
        )
        stmt = select(subq).order_by(
            direction,
            func.coalesce(subq.c.contacto_nombres, subq.c.invitado_nombres).asc(),
            subq.c.id_evento_contacto.asc(),
        )
        if paginated:
            stmt = stmt.offset((filtros.page - 1) * filtros.page_size).limit(
                filtros.page_size
            )
        return [dict(row) for row in (await self.db.execute(stmt)).mappings()], total

    async def list_filter_options(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> dict[str, list[Any]]:
        a = self._affiliation_select(id_evento, filtros).subquery()
        p = self._participation_select(id_evento, filtros).subquery()
        programs = (
            select(
                ProgramacionEvento.id_programacion_evento,
                ProgramacionEvento.modalidad,
                self._first_day(filtros).label("primera_fecha"),
            )
            .where(*self._program_conditions(id_evento, filtros))
            .order_by(self._first_day(filtros).asc().nulls_last())
            .limit(101)
        )
        program_rows = list((await self.db.execute(programs)).all())
        classifications = list(
            (
                await self.db.execute(
                    select(
                        a.c.id_detalle_categoria,
                        a.c.id_grupo,
                        a.c.nombre_grupo,
                        a.c.id_categoria,
                        a.c.nombre_categoria,
                    )
                    .distinct()
                    .order_by(a.c.nombre_grupo, a.c.nombre_categoria)
                    .limit(101)
                )
            ).all()
        )
        companies = list(
            (
                await self.db.execute(
                    select(a.c.id_empresa, a.c.nombre_empresa)
                    .distinct()
                    .order_by(a.c.nombre_empresa)
                    .limit(101)
                )
            ).all()
        )
        participant_options = list(
            (
                await self.db.execute(
                    select(
                        p.c.id_cargo,
                        p.c.nombre_cargo,
                        p.c.id_beneficio,
                        p.c.nombre_beneficio,
                    )
                    .distinct()
                    .limit(1000)
                )
            ).all()
        )
        return {
            "programaciones": program_rows,
            "clasificaciones": classifications,
            "empresas": companies,
            "participante_opciones": participant_options,
        }

    async def list_programs(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> tuple[list[dict[str, Any]], list[Any], list[Any]]:
        p = self._participation_select(id_evento, filtros).subquery()
        a = self._affiliation_select(id_evento, filtros).subquery()
        p_stats = (
            select(
                p.c.id_programacion_evento,
                func.count().label("participaciones"),
                func.count().filter(p.c.asistencia.is_(True)).label("asistencias"),
            )
            .group_by(p.c.id_programacion_evento)
            .subquery()
        )
        a_stats = (
            select(
                a.c.id_programacion_evento,
                func.count().label("empresas_afiliadas"),
            )
            .group_by(a.c.id_programacion_evento)
            .subquery()
        )
        conditions = self._program_conditions(id_evento, filtros)
        stmt = (
            select(
                ProgramacionEvento.id_programacion_evento,
                ProgramacionEvento.modalidad,
                ProgramacionEvento.estado,
                ProgramacionEvento.enlace_general,
                Lugar.id_lugar,
                Lugar.pais,
                Lugar.provincia,
                Lugar.distrito,
                Lugar.direccion,
                Lugar.estado.label("lugar_estado"),
                func.coalesce(a_stats.c.empresas_afiliadas, 0).label(
                    "empresas_afiliadas"
                ),
                func.coalesce(p_stats.c.participaciones, 0).label("participaciones"),
                func.coalesce(p_stats.c.asistencias, 0).label("asistencias"),
            )
            .outerjoin(Lugar, Lugar.id_lugar == ProgramacionEvento.id_lugar)
            .outerjoin(
                a_stats,
                a_stats.c.id_programacion_evento
                == ProgramacionEvento.id_programacion_evento,
            )
            .outerjoin(
                p_stats,
                p_stats.c.id_programacion_evento
                == ProgramacionEvento.id_programacion_evento,
            )
            .where(*conditions)
            .order_by(ProgramacionEvento.id_programacion_evento)
        )
        rows = [dict(row) for row in (await self.db.execute(stmt)).mappings()]
        ids = [row["id_programacion_evento"] for row in rows]
        if not ids:
            return [], [], []
        day_conditions: list[Any] = [
            DetalleProgramacionEvento.id_programacion_evento.in_(ids)
        ]
        responsible_conditions: list[Any] = [
            ResponsableEvento.id_programacion_evento.in_(ids)
        ]
        if filtros.alcance == ReporteAlcance.VIGENTE:
            day_conditions.append(DetalleProgramacionEvento.estado.is_(True))
            responsible_conditions.append(ResponsableEvento.estado.is_(True))
        if filtros.fecha_desde is not None:
            day_conditions.append(
                DetalleProgramacionEvento.fecha >= filtros.fecha_desde
            )
        if filtros.fecha_hasta is not None:
            day_conditions.append(
                DetalleProgramacionEvento.fecha <= filtros.fecha_hasta
            )
        days = list(
            (
                await self.db.execute(
                    select(DetalleProgramacionEvento)
                    .where(*day_conditions)
                    .order_by(
                        DetalleProgramacionEvento.id_programacion_evento,
                        DetalleProgramacionEvento.fecha,
                    )
                )
            ).scalars()
        )
        responsibles = list(
            (
                await self.db.execute(
                    select(
                        ResponsableEvento.id_responsable_evento,
                        ResponsableEvento.id_programacion_evento,
                        ResponsableEvento.id_usuario,
                        Usuario.nombre_usuario,
                        Usuario.nombres,
                        Usuario.apellidos,
                        ResponsableEvento.estado,
                    )
                    .join(Usuario, Usuario.id_usuario == ResponsableEvento.id_usuario)
                    .where(*responsible_conditions)
                    .order_by(
                        ResponsableEvento.id_programacion_evento,
                        Usuario.apellidos,
                    )
                )
            ).all()
        )
        return rows, days, responsibles

    async def list_series(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> list[tuple[str, str, int]]:
        p = self._participation_select(id_evento, filtros).subquery()
        a = self._affiliation_select(id_evento, filtros).subquery()
        day_conditions = [
            DetalleProgramacionEvento.id_programacion_evento
            == ProgramacionEvento.id_programacion_evento,
            *self._program_conditions(
                id_evento, filtros, include_date_overlap=False
            ),
        ]
        if filtros.alcance == ReporteAlcance.VIGENTE:
            day_conditions.append(DetalleProgramacionEvento.estado.is_(True))
        if filtros.fecha_desde is not None:
            day_conditions.append(
                DetalleProgramacionEvento.fecha >= filtros.fecha_desde
            )
        if filtros.fecha_hasta is not None:
            day_conditions.append(
                DetalleProgramacionEvento.fecha <= filtros.fecha_hasta
            )
        day_period = func.to_char(DetalleProgramacionEvento.fecha, "YYYY-MM")
        first_period_p = func.to_char(p.c.primera_fecha_programacion, "YYYY-MM")
        first_period_a = func.to_char(a.c.fecha_referencia, "YYYY-MM")
        assignment_period = func.to_char(p.c.fecha_asignacion, "YYYY-MM")
        qr_generation_period = func.to_char(p.c.qr_fecha_generacion, "YYYY-MM")
        qr_sent_period = func.to_char(p.c.qr_fecha_envio, "YYYY-MM")
        statements = [
            select(
                literal("dias_programados").label("metrica"),
                day_period.label("periodo"),
                func.count().label("valor"),
            )
            .select_from(DetalleProgramacionEvento)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == DetalleProgramacionEvento.id_programacion_evento,
            )
            .where(*day_conditions)
            .group_by(day_period),
            select(
                literal("programaciones_programadas"),
                first_period_a,
                func.count(func.distinct(a.c.id_programacion_evento)),
            )
            .select_from(a)
            .where(a.c.fecha_referencia.is_not(None))
            .group_by(first_period_a),
            select(
                literal("empresas_programadas"),
                first_period_a,
                func.count(func.distinct(a.c.id_empresa)),
            )
            .select_from(a)
            .where(a.c.fecha_referencia.is_not(None))
            .group_by(first_period_a),
            select(
                literal("participaciones_programadas"),
                first_period_p,
                func.count(),
            )
            .select_from(p)
            .where(p.c.primera_fecha_programacion.is_not(None))
            .group_by(first_period_p),
            select(
                literal("asistencias_programadas"),
                first_period_p,
                func.count().filter(p.c.asistencia.is_(True)),
            )
            .select_from(p)
            .where(p.c.primera_fecha_programacion.is_not(None))
            .group_by(first_period_p),
            select(
                literal("empresas_representadas_programadas"),
                first_period_p,
                func.count(
                    func.distinct(case((p.c.asistencia.is_(True), p.c.id_empresa)))
                ),
            )
            .select_from(p)
            .where(p.c.primera_fecha_programacion.is_not(None))
            .group_by(first_period_p),
            select(
                literal("asignaciones_beneficio"),
                assignment_period,
                func.count(),
            )
            .select_from(p)
            .where(p.c.fecha_asignacion.is_not(None))
            .group_by(assignment_period),
            select(
                literal("qr_generados"),
                qr_generation_period,
                func.count(),
            )
            .select_from(p)
            .where(p.c.qr_fecha_generacion.is_not(None))
            .group_by(qr_generation_period),
            select(
                literal("qr_enviados"),
                qr_sent_period,
                func.count(),
            )
            .select_from(p)
            .where(p.c.qr_fecha_envio.is_not(None))
            .group_by(qr_sent_period),
        ]
        combined = union_all(*statements).subquery()
        stmt = select(combined).order_by(combined.c.metrica, combined.c.periodo)
        return [
            (str(row[0]), str(row[1]), int(row[2] or 0))
            for row in (await self.db.execute(stmt)).all()
        ]

    async def list_policy_details(self, id_evento: int) -> list[Any]:
        stmt = (
            select(DetallePoliticaEvento, Beneficio, Categoria)
            .join(
                Evento,
                Evento.id_politica_evento
                == DetallePoliticaEvento.id_politica_evento,
            )
            .join(Beneficio, Beneficio.id_beneficio == DetallePoliticaEvento.id_beneficio)
            .join(Categoria, Categoria.id_categoria == DetallePoliticaEvento.id_categoria)
            .where(Evento.id_evento == id_evento)
            .order_by(Categoria.nombre_categoria, Beneficio.nombre)
        )
        return list((await self.db.execute(stmt)).all())

    async def benefit_usage(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> tuple[
        dict[tuple[int, int], dict[str, int]],
        dict[tuple[int, int], int],
    ]:
        p = self._participation_select(id_evento, filtros).subquery()
        grouped = (
            select(
                p.c.id_beneficio,
                p.c.id_categoria,
                p.c.codigo_grupo,
                func.count().label("asignaciones"),
                case(
                    (
                        p.c.codigo_grupo.is_(None),
                        func.count().filter(p.c.asistencia.is_(True)),
                    ),
                    else_=case(
                        (func.bool_and(p.c.asistencia.is_(True)), func.count()),
                        else_=0,
                    ),
                ).label("usados"),
            )
            .where(p.c.id_beneficio.is_not(None))
            .group_by(p.c.id_beneficio, p.c.id_categoria, p.c.codigo_grupo)
            .subquery()
        )
        assigned = (
            select(
                grouped.c.id_beneficio,
                grouped.c.id_categoria,
                func.sum(grouped.c.asignaciones).label("asignaciones"),
                func.sum(grouped.c.usados).label("usados"),
            )
            .group_by(grouped.c.id_beneficio, grouped.c.id_categoria)
        )
        usage = {
            (int(row[0]), int(row[1])): {
                "asignaciones": int(row[2]),
                "usados": int(row[3]),
            }
            for row in (await self.db.execute(assigned)).all()
            if row[1] is not None
        }
        coordination = {
            (int(row[0]), int(row[1])): int(row[2])
            for row in (
                await self.db.execute(
                    select(
                        p.c.id_beneficio,
                        p.c.id_categoria,
                        func.count().filter(p.c.requiere_coordinacion.is_(True)),
                    )
                    .where(
                        p.c.id_beneficio.is_not(None),
                        p.c.id_categoria.is_not(None),
                    )
                    .group_by(p.c.id_beneficio, p.c.id_categoria)
                )
            ).all()
        }
        return usage, coordination

    async def policy_company_counts(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> tuple[dict[int, int], dict[int, int]]:
        a = self._affiliation_select(id_evento, filtros).subquery()
        per_program = {
            int(row[0]): int(row[1])
            for row in (
                await self.db.execute(
                    select(a.c.id_categoria, func.count())
                    .where(a.c.id_categoria.is_not(None))
                    .group_by(a.c.id_categoria)
                )
            ).all()
        }
        unique_companies = {
            int(row[0]): int(row[1])
            for row in (
                await self.db.execute(
                    select(
                        a.c.id_categoria,
                        func.count(func.distinct(a.c.id_empresa)),
                    )
                    .where(a.c.id_categoria.is_not(None))
                    .group_by(a.c.id_categoria)
                )
            ).all()
        }
        return per_program, unique_companies

    async def accreditation(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> tuple[dict[str, int], int]:
        p = self._participation_select(id_evento, filtros).subquery()
        stmt = select(
            func.count().filter(p.c.id_participante_qr.is_not(None)).label(
                "qr_generados"
            ),
            func.count().filter(p.c.qr_fecha_envio.is_not(None)).label("qr_enviados"),
            func.count()
            .filter(
                p.c.id_participante_qr.is_not(None),
                p.c.qr_fecha_envio.is_(None),
                p.c.qr_estado.is_(True),
            )
            .label("qr_pendientes"),
            func.count().filter(p.c.credencial_impresa.is_(True)).label(
                "credenciales_impresas"
            ),
            func.count().filter(p.c.credencial_impresa.is_(False)).label(
                "credenciales_no_impresas"
            ),
        ).select_from(p)
        values = {
            key: int(value or 0)
            for key, value in (await self.db.execute(stmt)).mappings().one().items()
        }
        reprints = int(
            await self.db.scalar(
                select(func.count())
                .select_from(Auditoria)
                .where(
                    Auditoria.entidad == "evento_contacto",
                    Auditoria.accion == "REIMPRESION_CREDENCIAL",
                    Auditoria.id_entidad.in_(
                        select(cast(p.c.id_evento_contacto, String))
                    ),
                )
            )
            or 0
        )
        return values, reprints

    async def list_agenda(
        self, id_evento: int, filtros: ReporteEventoFiltros
    ) -> list[dict[str, Any]]:
        conditions = self._program_conditions(
            id_evento, filtros, include_date_overlap=False
        )
        if filtros.alcance == ReporteAlcance.VIGENTE:
            conditions.append(DetalleProgramacionEvento.estado.is_(True))
        if filtros.fecha_desde is not None:
            conditions.append(DetalleProgramacionEvento.fecha >= filtros.fecha_desde)
        if filtros.fecha_hasta is not None:
            conditions.append(DetalleProgramacionEvento.fecha <= filtros.fecha_hasta)
        stmt = (
            select(
                DetalleProgramacionEvento.id_detalle_programacion,
                DetalleProgramacionEvento.id_programacion_evento,
                DetalleProgramacionEvento.fecha,
                DetalleProgramacionEvento.hora_inicio,
                DetalleProgramacionEvento.hora_fin,
                DetalleProgramacionEvento.enlace,
                DetalleProgramacionEvento.estado,
            )
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == DetalleProgramacionEvento.id_programacion_evento,
            )
            .where(*conditions)
            .order_by(
                DetalleProgramacionEvento.fecha,
                DetalleProgramacionEvento.id_detalle_programacion,
            )
        )
        return [dict(row) for row in (await self.db.execute(stmt)).mappings()]

    # -- Cupos "por año" (todas las empresas, todos los eventos) ----------

    async def list_afiliaciones_activas_todos_eventos(self) -> list[Any]:
        """Empresas activamente afiliadas a alguna programación, agrupadas
        por evento (una fila por combinación evento+empresa+categoría)."""
        stmt = (
            select(
                Evento.id_evento,
                Evento.nombre_evento,
                Evento.estado,
                Empresa.id_empresa,
                Empresa.nombre_empresa,
                Empresa.ruc,
                Categoria.id_categoria,
                Categoria.nombre_categoria,
            )
            .distinct()
            .select_from(EventoEmpresa)
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == EventoEmpresa.id_programacion_evento,
            )
            .join(Evento, Evento.id_evento == ProgramacionEvento.id_evento)
            .join(Empresa, Empresa.id_empresa == EventoEmpresa.id_empresa)
            .join(
                DetalleCategoria,
                DetalleCategoria.id_detalle_categoria
                == Empresa.id_detalle_categoria,
            )
            .join(Categoria, Categoria.id_categoria == DetalleCategoria.id_categoria)
            .where(EventoEmpresa.estado.is_(True))
        )
        return (await self.db.execute(stmt)).all()

    async def list_politica_por_anio_todos_eventos(self) -> list[Any]:
        """Configuración de beneficios 'por año' por evento y categoría."""
        stmt = (
            select(
                Evento.id_evento,
                DetallePoliticaEvento.id_categoria,
                Beneficio.id_beneficio,
                Beneficio.nombre,
                Beneficio.personas_por_asignacion,
                DetallePoliticaEvento.entradas_gratuitas,
            )
            .select_from(DetallePoliticaEvento)
            .join(Beneficio, Beneficio.id_beneficio == DetallePoliticaEvento.id_beneficio)
            .join(
                PoliticaEvento,
                PoliticaEvento.id_politica_evento
                == DetallePoliticaEvento.id_politica_evento,
            )
            .join(Evento, Evento.id_politica_evento == PoliticaEvento.id_politica_evento)
            .where(Beneficio.tipo_calculo == TipoCalculoBeneficio.POR_ANIO)
        )
        return (await self.db.execute(stmt)).all()

    async def list_asignaciones_por_anio_todos_eventos(self) -> list[Any]:
        """Asignaciones usadas de beneficios 'por año', ya filtradas a los
        días dentro del rango de la política del evento correspondiente."""
        dentro_de_rango = (
            select(DetalleProgramacionEvento.id_detalle_programacion)
            .where(
                DetalleProgramacionEvento.id_programacion_evento
                == EventoContacto.id_programacion_evento,
                DetalleProgramacionEvento.fecha >= PoliticaEvento.fecha_inicio,
                DetalleProgramacionEvento.fecha <= PoliticaEvento.fecha_fin,
            )
            .exists()
        )
        stmt = (
            select(
                Evento.id_evento,
                EventoContacto.id_empresa,
                AsignacionBeneficio.id_beneficio,
                AsignacionBeneficio.id_asignacion_beneficio,
                AsignacionBeneficio.codigo_grupo,
                EventoContacto.asistencia_evento,
            )
            .select_from(AsignacionBeneficio)
            .join(
                EventoContacto,
                EventoContacto.id_evento_contacto
                == AsignacionBeneficio.id_evento_contacto,
            )
            .join(
                ProgramacionEvento,
                ProgramacionEvento.id_programacion_evento
                == EventoContacto.id_programacion_evento,
            )
            .join(Evento, Evento.id_evento == ProgramacionEvento.id_evento)
            .join(
                PoliticaEvento,
                PoliticaEvento.id_politica_evento == Evento.id_politica_evento,
            )
            .join(Beneficio, Beneficio.id_beneficio == AsignacionBeneficio.id_beneficio)
            .where(
                Beneficio.tipo_calculo == TipoCalculoBeneficio.POR_ANIO,
                dentro_de_rango,
            )
        )
        return (await self.db.execute(stmt)).all()
