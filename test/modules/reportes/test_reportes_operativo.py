import pytest

from test.modules.reportes.conftest import seed_report_context


pytestmark = pytest.mark.asyncio


async def test_kpis_preservan_granos_y_coberturas(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
    response = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/kpis", headers=context["headers"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    kpis = body["kpis"]
    assert kpis["total_programaciones"]["valor"] == 3
    assert kpis["total_dias"]["valor"] == 3
    assert kpis["total_empresas_afiliadas"]["valor"] == 2
    assert kpis["total_empresas_unicas"]["valor"] == 2
    assert kpis["total_empresas_representadas"]["valor"] == 1
    assert kpis["total_participaciones"]["valor"] == 2
    assert kpis["total_contactos_maestros"]["valor"] == 1
    assert kpis["total_invitados"]["valor"] == 1
    assert kpis["contactos_unicos"]["valor"] == 1
    assert kpis["cobertura_afiliadas"] == {
        "tipo_universo": "AFILIADAS_EVENTO",
        "numerador": 1,
        "denominador": 2,
        "porcentaje": 50.0,
    }
    assert body["disponibilidad_datos"]["confirmacion"]["disponible"] is False
    assert body["disponibilidad_datos"]["asistencia_por_dia"]["disponible"] is False


async def test_empresa_sin_participantes_se_preserva(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
        empty_id = context["empty_company"].id_empresa
    headers = context["headers"]
    filters = await client.get(f"/api/v1/reportes/eventos/{event_id}/filtros", headers=headers)
    groups = await client.get(f"/api/v1/reportes/eventos/{event_id}/grupos", headers=headers)
    categories = await client.get(f"/api/v1/reportes/eventos/{event_id}/categorias", headers=headers)
    companies = await client.get(f"/api/v1/reportes/eventos/{event_id}/empresas", headers=headers)
    participants = await client.get(f"/api/v1/reportes/eventos/{event_id}/participantes", headers=headers)
    assert empty_id in {item["id"] for item in filters.json()["empresas"]}
    assert sum(item["afiliaciones"] for item in groups.json()["items"]) == 2
    assert sum(item["afiliaciones"] for item in categories.json()["items"]) == 2
    shared_category = context["category_a"].id_categoria
    assert len(
        [item for item in categories.json()["items"] if item["id_categoria"] == shared_category]
    ) == 2
    empty = next(item for item in companies.json()["items"] if item["id_empresa"] == empty_id)
    assert empty["participantes"] == 0
    assert empty["asistentes"] == 0
    assert empty_id not in {item["id_empresa"] for item in participants.json()["items"]}


async def test_participante_hibrido_no_inventa_canal_y_resuelve_invitado(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
    response = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/participantes?page_size=100",
        headers=context["headers"],
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    master = next(item for item in items if item["tipo_participante"] == "CONTACTO")
    guest = next(item for item in items if item["tipo_participante"] == "INVITADO")
    assert master["modalidad_programacion"] == "HIBRIDO"
    assert master["modalidad_asistencia"] == "NO_REGISTRADA"
    assert master["numero_documento"] == context["contact"].numero_documento
    assert guest["nombres"] == "Bruno"
    assert guest["id_contacto"] is None
    assert guest["modalidad_asistencia"] == "SIN_ASISTENCIA"


async def test_alcance_historico_incluye_inactivos(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
    current = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/kpis", headers=context["headers"]
    )
    historical = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/kpis?alcance=HISTORICO",
        headers=context["headers"],
    )
    assert current.json()["kpis"]["total_participaciones"]["valor"] == 2
    assert historical.status_code == 200, historical.text
    assert historical.json()["kpis"]["total_participaciones"]["valor"] == 3
    assert historical.json()["kpis"]["total_empresas_afiliadas"]["valor"] == 2
    assert historical.json()["advertencias"]


async def test_clasificacion_a_fecha_de_programacion(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
        program_id = context["programs"][0].id_programacion_evento
        old_detail = context["detail_b"].id_detalle_categoria
        company_id = context["company"].id_empresa
    response = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/empresas"
        f"?id_programacion_evento={program_id}&clasificacion=FECHA_PROGRAMACION",
        headers=context["headers"],
    )
    assert response.status_code == 200, response.text
    company = next(item for item in response.json()["items"] if item["id_empresa"] == company_id)
    assert company["clasificacion"]["id_detalle_categoria"] == old_detail
    assert company["clasificacion"]["fuente"] == "FECHA_PROGRAMACION"
    assert company["clasificacion"]["fecha_referencia"] == "2026-01-15"


async def test_programaciones_no_generan_producto_cartesiano(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
    response = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/programaciones",
        headers=context["headers"],
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 3
    assert sum(item["cantidad_dias"] for item in items) == 3
    hybrid = next(item for item in items if item["modalidad"] == "HIBRIDO")
    assert len(hybrid["responsables"]) == 1
    assert hybrid["empresas_afiliadas"] == 2


async def test_rango_temporal_limita_dias_agenda_y_serie(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
    query = "fecha_desde=2026-02-01&fecha_hasta=2026-02-28"
    kpis = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/kpis?{query}",
        headers=context["headers"],
    )
    programs = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/programaciones?{query}",
        headers=context["headers"],
    )
    series = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/series/mensual?{query}",
        headers=context["headers"],
    )
    assert kpis.json()["kpis"]["total_dias"]["valor"] == 1
    assert len(programs.json()["items"]) == 1
    assert programs.json()["items"][0]["dias"][0]["fecha"] == "2026-02-15"
    days = next(item for item in series.json()["series"] if item["metrica"] == "dias_programados")
    assert days["datos"] == [{"periodo": "2026-02", "valor": 1}]


async def test_filtros_individuales_y_combinados(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
    cases = (
        f"id_programacion_evento={context['programs'][0].id_programacion_evento}",
        f"id_grupo={context['group_a'].id_grupo}",
        f"id_categoria={context['category_a'].id_categoria}",
        f"id_detalle_categoria={context['detail_a'].id_detalle_categoria}",
        f"id_empresa={context['company'].id_empresa}",
        f"id_cargo={context['cargo'].id_cargo}",
        "estado_afiliacion=true",
        "estado_participacion=true",
        "asistencia=true",
        f"id_beneficio={context['annual'].id_beneficio}",
        "requiere_coordinacion=true",
        "tipo_participante=CONTACTO",
        "modalidad=HIBRIDO",
        "fecha_desde=2026-01-01&fecha_hasta=2026-01-31",
        "alcance=HISTORICO",
        "clasificacion=FECHA_PROGRAMACION",
        "search=Ana",
        f"id_grupo={context['group_a'].id_grupo}&id_categoria={context['category_a'].id_categoria}&asistencia=true",
    )
    for query in cases:
        response = await client.get(
            f"/api/v1/reportes/eventos/{event_id}/kpis?{query}",
            headers=context["headers"],
        )
        assert response.status_code == 200, (query, response.text)


async def test_paginacion_y_orden_estable(client, session_factory) -> None:
    async with session_factory() as session:
        context = await seed_report_context(session)
        event_id = context["event"].id_evento
    first = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/detalle?page=1&page_size=1&sort=id_evento_contacto",
        headers=context["headers"],
    )
    second = await client.get(
        f"/api/v1/reportes/eventos/{event_id}/detalle?page=2&page_size=1&sort=id_evento_contacto",
        headers=context["headers"],
    )
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == 2
    assert first.json()["pages"] == 2
    assert first.json()["items"][0]["id_evento_contacto"] != second.json()["items"][0]["id_evento_contacto"]
