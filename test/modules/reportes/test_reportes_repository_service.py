from time import perf_counter

import pytest
from sqlalchemy import event, func, select, text

from app.modules.participantes.models import EventoContacto
from app.modules.reportes.dto import ReporteEventoFiltros
from app.modules.reportes.repository import ReporteRepository
from app.modules.reportes.service import ReporteFiltroInconsistenteError, ReporteService
from test.modules.reportes.conftest import seed_report_context


pytestmark = pytest.mark.asyncio


class QueryCounter:
    def __init__(self, engine) -> None:
        self.engine = engine.sync_engine
        self.count = 0

    def _before_cursor_execute(self, *args) -> None:
        self.count += 1

    def __enter__(self) -> "QueryCounter":
        event.listen(self.engine, "before_cursor_execute", self._before_cursor_execute)
        return self

    def __exit__(self, *args) -> None:
        event.remove(self.engine, "before_cursor_execute", self._before_cursor_execute)


async def test_service_valida_relacion_padre_hijo(session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        with pytest.raises(ReporteFiltroInconsistenteError) as exc:
            await ReporteService(session).obtener_kpis(
                context["event"].id_evento,
                ReporteEventoFiltros(id_programacion_evento=999_999),
            )
        assert exc.value.campo == "id_programacion_evento"


async def test_query_count_participantes_no_crece_con_filas(session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        service = ReporteService(session)
        with QueryCounter(session.bind) as initial:
            first = await service.obtener_participantes(
                context["event"].id_evento, ReporteEventoFiltros(page_size=100)
            )
        program_id = context["programs"][0].id_programacion_evento
        company_id = context["company"].id_empresa
        session.add_all(
            [
                EventoContacto(
                    id_programacion_evento=program_id,
                    id_empresa=company_id,
                    invitado_nombres=f"Carga {index}",
                    invitado_apellidos="Reporte",
                    estado=True,
                    asistencia_evento=False,
                )
                for index in range(30)
            ]
        )
        await session.commit()
        with QueryCounter(session.bind) as expanded:
            second = await service.obtener_participantes(
                context["event"].id_evento, ReporteEventoFiltros(page_size=100)
            )
        assert first.total == 2
        assert second.total == 32
        assert initial.count == expanded.count == 3


async def test_query_count_dashboard_es_acotado(session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        with QueryCounter(session.bind) as counter:
            response = await ReporteService(session).obtener_dashboard(
                context["event"].id_evento, ReporteEventoFiltros()
            )
        assert response.kpis.total_participaciones.valor == 2
        assert counter.count <= 9


@pytest.mark.performance
async def test_baseline_100_participaciones(session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        program_id = context["programs"][0].id_programacion_evento
        company_id = context["company"].id_empresa
        session.add_all(
            [
                EventoContacto(
                    id_programacion_evento=program_id,
                    id_empresa=company_id,
                    invitado_nombres=f"Performance {index}",
                    invitado_apellidos="Reporte",
                    estado=True,
                    asistencia_evento=index % 2 == 0,
                )
                for index in range(98)
            ]
        )
        await session.commit()
        started = perf_counter()
        with QueryCounter(session.bind) as counter:
            response = await ReporteService(session).obtener_kpis(
                context["event"].id_evento, ReporteEventoFiltros()
            )
        elapsed_ms = (perf_counter() - started) * 1000
        assert response.kpis.total_participaciones.valor == 100
        assert counter.count == 3
        assert elapsed_ms > 0
        print(
            f"REPORT_PERF kpis rows=100 queries={counter.count} "
            f"elapsed_ms={elapsed_ms:.3f}"
        )


@pytest.mark.performance
async def test_explain_analyze_consultas_base(session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        repository = ReporteRepository(session)
        filters = ReporteEventoFiltros()
        participation = repository._participation_select(
            context["event"].id_evento, filters
        ).subquery()
        affiliation = repository._affiliation_select(
            context["event"].id_evento, filters
        ).subquery()
        statements = {
            "participantes_detalle": select(participation),
            "empresas_filtros": select(affiliation),
            "kpi_participaciones": select(func.count()).select_from(participation),
            "grupos": select(
                affiliation.c.id_grupo, func.count()
            ).group_by(affiliation.c.id_grupo),
            "beneficios": select(
                participation.c.id_beneficio, func.count()
            ).group_by(participation.c.id_beneficio),
        }
        for name, statement in statements.items():
            compiled = statement.compile(
                dialect=session.bind.sync_engine.dialect,
                compile_kwargs={"literal_binds": True},
            )
            plan = await session.scalar(
                text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {compiled}")
            )
            report = plan[0]
            print(
                f"REPORT_EXPLAIN query={name} planning_ms="
                f"{report['Planning Time']:.3f} execution_ms="
                f"{report['Execution Time']:.3f} rows="
                f"{report['Plan']['Actual Rows']} node={report['Plan']['Node Type']}"
            )
            assert report["Execution Time"] >= 0
            assert report["Planning Time"] >= 0
            assert report["Plan"]["Actual Rows"] >= 0


@pytest.mark.performance
async def test_query_count_por_operacion(session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        service = ReporteService(session)
        filters = ReporteEventoFiltros(page_size=100)
        event_id = context["event"].id_evento
        operations = (
            (
                "selector",
                lambda: service.listar_eventos(
                    search=None,
                    estado=None,
                    fecha_desde=None,
                    fecha_hasta=None,
                    page=1,
                    page_size=20,
                    sort="nombre_evento",
                    order=filters.order,
                ),
                2,
            ),
            ("filtros", lambda: service.obtener_filtros(event_id, filters), 5),
            ("kpis", lambda: service.obtener_kpis(event_id, filters), 3),
            ("grupos", lambda: service.obtener_grupos(event_id, filters), 3),
            ("categorias", lambda: service.obtener_categorias(event_id, filters), 3),
            ("empresas", lambda: service.obtener_empresas(event_id, filters), 3),
            ("participantes", lambda: service.obtener_participantes(event_id, filters), 3),
            ("programaciones", lambda: service.obtener_programaciones(event_id, filters), 4),
            ("detalle", lambda: service.obtener_detalle(event_id, filters), 3),
            ("dashboard", lambda: service.obtener_dashboard(event_id, filters), 8),
            ("series", lambda: service.obtener_series(event_id, filters), 2),
            ("beneficios", lambda: service.obtener_beneficios(event_id, filters), 6),
            ("acreditacion", lambda: service.obtener_acreditacion(event_id, filters), 3),
            ("exportar", lambda: service.exportar(event_id, filters, context["actor"]), 24),
        )
        for name, operation, maximum in operations:
            with QueryCounter(session.bind) as counter:
                await operation()
            print(f"REPORT_QUERY_COUNT endpoint={name} queries={counter.count}")
            assert counter.count <= maximum
