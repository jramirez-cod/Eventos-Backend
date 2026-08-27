from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.modules.contactos.models import Contacto
from app.modules.eventos.models import Evento, EventoEstado, ProgramacionEvento
from app.modules.maestros.models import TipoCalculoBeneficio
from app.modules.participantes.models import EventoContacto, EventoEmpresa
from test.modules.contactos.conftest import create_contacto, create_empresa
from test.modules.participantes.conftest import (
    create_codigo_acceso,
    crear_contexto_beneficio,
    crear_programacion_con_dia,
)


pytestmark = pytest.mark.asyncio


async def _build_portal_context(
    session_factory, *, entradas_gratuitas: int = 2
) -> dict[str, object]:
    async with session_factory() as session:
        ctx = await crear_contexto_beneficio(
            session,
            tipo_calculo=TipoCalculoBeneficio.POR_EVENTO,
            entradas_gratuitas=entradas_gratuitas,
        )
        prog = await crear_programacion_con_dia(
            session,
            evento=ctx["evento"],
            empresa=ctx["empresa"],
            fecha=date.today() + timedelta(days=5),
        )
        contacto1 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=60_001
        )
        contacto2 = await create_contacto(
            session, empresa=ctx["empresa"], actor=ctx["actor"], sequence=60_002
        )
        await session.commit()

        evento_empresa = await session.scalar(
            select(EventoEmpresa).where(
                EventoEmpresa.id_programacion_evento == prog.id_programacion_evento,
                EventoEmpresa.id_empresa == ctx["empresa"].id_empresa,
            )
        )
        assert evento_empresa is not None
        id_evento_empresa = evento_empresa.id_evento_empresa

    return {
        **ctx,
        "programacion": prog,
        "contacto1": contacto1,
        "contacto2": contacto2,
        "id_evento_empresa": id_evento_empresa,
    }


async def test_flujo_completo_portal_agrega_existentes_e_invitado(
    client, session_factory
) -> None:
    data = await _build_portal_context(session_factory)
    headers = data["headers"]
    id_evento_empresa = data["id_evento_empresa"]
    contacto1 = data["contacto1"]

    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto1.id_contacto},
    )

    async with session_factory() as session:
        codigo = await create_codigo_acceso(
            session, id_evento_empresa=id_evento_empresa
        )

    validar = await client.post(
        "/api/v1/portal/validar-codigo", json={"codigo": codigo}
    )
    assert validar.status_code == 200, validar.text
    portal_headers = {"Authorization": f"Bearer {validar.json()['portal_token']}"}
    assert validar.json()["nombre_empresa"] == data["empresa"].nombre_empresa

    contactos = await client.get("/api/v1/portal/contactos", headers=portal_headers)
    assert contactos.status_code == 200, contactos.text
    listado = contactos.json()
    assert len(listado) == 2
    beneficio_disponible = next(
        b
        for item in listado
        for b in item["beneficios_disponibles"]
        if b["id_beneficio"] == data["beneficio"].id_beneficio
    )
    assert beneficio_disponible["disponible"] is True

    agregar = await client.post(
        "/api/v1/portal/participantes",
        headers=portal_headers,
        json={
            "selecciones": [
                {
                    "id_contacto": data["contacto2"].id_contacto,
                    "id_beneficio": data["beneficio"].id_beneficio,
                }
            ]
        },
    )
    assert agregar.status_code == 200, agregar.text
    assert agregar.json()[0]["nombre_beneficio_asignado"] == data["beneficio"].nombre

    invitado = await client.post(
        "/api/v1/portal/invitados",
        headers=portal_headers,
        json={"nombres": "Visitante", "apellidos": "Externo"},
    )
    assert invitado.status_code == 201, invitado.text
    assert invitado.json()["es_invitado"] is True

    async with session_factory() as session:
        total = await session.scalar(
            select(EventoContacto.id_evento_contacto).where(
                EventoContacto.id_programacion_evento
                == data["programacion"].id_programacion_evento
            )
        )
        assert total is not None


async def test_portal_rechaza_contacto_de_otra_empresa(
    client, session_factory
) -> None:
    data = await _build_portal_context(session_factory)
    headers = data["headers"]
    id_evento_empresa = data["id_evento_empresa"]

    async with session_factory() as session:
        otra_empresa = await create_empresa(session, sequence=61_000)
        ajeno = await create_contacto(
            session, empresa=otra_empresa, actor=data["actor"], sequence=61_001
        )
        await session.commit()

    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": data["contacto1"].id_contacto},
    )
    async with session_factory() as session:
        codigo = await create_codigo_acceso(
            session, id_evento_empresa=id_evento_empresa, codigo="OTRA0001"
        )

    validar = await client.post(
        "/api/v1/portal/validar-codigo", json={"codigo": codigo}
    )
    portal_headers = {"Authorization": f"Bearer {validar.json()['portal_token']}"}

    response = await client.post(
        "/api/v1/portal/participantes",
        headers=portal_headers,
        json={"selecciones": [{"id_contacto": ajeno.id_contacto}]},
    )
    assert response.status_code == 400, response.text


@pytest.mark.parametrize("estado", [EventoEstado.FINALIZADO, EventoEstado.INACTIVO])
async def test_portal_rechaza_codigo_si_evento_no_abierto(
    client, session_factory, estado
) -> None:
    data = await _build_portal_context(session_factory)
    headers = data["headers"]
    id_evento_empresa = data["id_evento_empresa"]

    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": data["contacto1"].id_contacto},
    )
    async with session_factory() as session:
        codigo = await create_codigo_acceso(
            session, id_evento_empresa=id_evento_empresa, codigo="NOABIER1"
        )

    async with session_factory() as session:
        evento = await session.get(Evento, data["evento"].id_evento)
        evento.estado = estado
        await session.commit()

    response = await client.post(
        "/api/v1/portal/validar-codigo", json={"codigo": codigo}
    )
    assert response.status_code == 403, response.text


async def test_portal_rechaza_codigo_si_programacion_no_abierta(
    client, session_factory
) -> None:
    data = await _build_portal_context(session_factory)
    headers = data["headers"]
    id_evento_empresa = data["id_evento_empresa"]

    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": data["contacto1"].id_contacto},
    )
    async with session_factory() as session:
        codigo = await create_codigo_acceso(
            session, id_evento_empresa=id_evento_empresa, codigo="NOABIER2"
        )

    async with session_factory() as session:
        prog = await session.get(
            ProgramacionEvento, data["programacion"].id_programacion_evento
        )
        prog.estado = EventoEstado.FINALIZADO
        await session.commit()

    response = await client.post(
        "/api/v1/portal/validar-codigo", json={"codigo": codigo}
    )
    assert response.status_code == 403, response.text


async def test_portal_rechaza_codigo_expirado_y_token_invalido(
    client, session_factory
) -> None:
    data = await _build_portal_context(session_factory)
    id_evento_empresa = data["id_evento_empresa"]

    async with session_factory() as session:
        codigo_vencido = await create_codigo_acceso(
            session,
            id_evento_empresa=id_evento_empresa,
            codigo="VENCIDO1",
            expira_en=datetime.now(UTC) - timedelta(days=1),
        )

    vencido = await client.post(
        "/api/v1/portal/validar-codigo", json={"codigo": codigo_vencido}
    )
    assert vencido.status_code == 403, vencido.text

    inexistente = await client.post(
        "/api/v1/portal/validar-codigo", json={"codigo": "NOEXISTE"}
    )
    assert inexistente.status_code == 403, inexistente.text

    token_invalido = await client.get(
        "/api/v1/portal/contactos",
        headers={"Authorization": "Bearer token-invalido"},
    )
    assert token_invalido.status_code == 403, token_invalido.text
