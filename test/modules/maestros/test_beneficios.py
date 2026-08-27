from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.models import Categoria
from app.modules.eventos.models import (
    DetallePoliticaEvento,
    Evento,
    EventoEstado,
    PoliticaEvento,
)
from app.modules.maestros.models import Area, Beneficio
from test.modules.maestros import create_area, create_beneficio, seed_maestro_actor


pytestmark = pytest.mark.asyncio


async def _crear_evento_abierto_con_beneficio(
    session, *, beneficio: Beneficio, area: Area
) -> Evento:
    categoria = Categoria(nombre_categoria=f"Categoria {beneficio.nombre}")
    session.add(categoria)
    await session.flush()

    politica = PoliticaEvento(
        fecha_inicio=date.today() + timedelta(days=1),
        fecha_fin=date.today() + timedelta(days=90),
    )
    session.add(politica)
    await session.flush()

    session.add(
        DetallePoliticaEvento(
            id_politica_evento=politica.id_politica_evento,
            id_beneficio=beneficio.id_beneficio,
            id_categoria=categoria.id_categoria,
            entradas_gratuitas=1,
        )
    )
    evento = Evento(
        nombre_evento=f"Evento usando {beneficio.nombre}",
        id_politica_evento=politica.id_politica_evento,
        id_area=area.id_area,
        estado=EventoEstado.ABIERTO,
    )
    session.add(evento)
    await session.flush()
    return evento


async def test_crear_beneficio_correcto_normaliza_y_audita(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_maestro_actor(session)

    response = await client.post(
        "/api/v1/maestros/beneficios",
        headers=headers,
        json={
            "nombre": "  Entrada   Gratuita ",
            "condicion": "  Solo categoría Oro  ",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_beneficio"] > 0
    assert body["nombre"] == "Entrada Gratuita"
    assert body["condicion"] == "Solo categoría Oro"
    assert body["estado"] is True

    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "CREAR_BENEFICIO")
        )
    assert audit is not None
    assert audit.id_usuario == actor.id_usuario
    assert audit.entidad == "beneficio"


async def test_nombre_beneficio_obligatorio(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    missing = await client.post(
        "/api/v1/maestros/beneficios", headers=headers, json={}
    )
    blank = await client.post(
        "/api/v1/maestros/beneficios",
        headers=headers,
        json={"nombre": "   ", "condicion": None},
    )

    assert missing.status_code == 422
    assert blank.status_code == 400


async def test_beneficio_duplicado_ignora_mayusculas_y_espacios(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    first = await client.post(
        "/api/v1/maestros/beneficios",
        headers=headers,
        json={"nombre": "Almuerzo"},
    )
    duplicate = await client.post(
        "/api/v1/maestros/beneficios",
        headers=headers,
        json={"nombre": "  almuerzo  "},
    )

    assert first.status_code == 201
    assert duplicate.status_code == 409


async def test_obtener_beneficio_y_beneficio_inexistente(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        beneficio = await create_beneficio(
            session,
            nombre="Estacionamiento",
            condicion="Solo para expositores",
        )
        await session.commit()
        id_beneficio = beneficio.id_beneficio

    found = await client.get(
        f"/api/v1/maestros/beneficios/{id_beneficio}", headers=headers
    )
    missing = await client.get(
        "/api/v1/maestros/beneficios/999999", headers=headers
    )

    assert found.status_code == 200
    assert found.json()["nombre"] == "Estacionamiento"
    assert missing.status_code == 404


async def test_sin_beneficio_aparece_primero_en_el_listado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        await create_beneficio(session, nombre="Almuerzo")
        await create_beneficio(session, nombre="Sin beneficio")
        await create_beneficio(session, nombre="Zapatillas")
        await session.commit()

    response = await client.get(
        "/api/v1/maestros/beneficios",
        headers=headers,
        params={"page_size": 100},
    )

    assert response.status_code == 200
    nombres = [item["nombre"] for item in response.json()["items"]]
    assert nombres[0] == "Sin beneficio"


async def test_listar_beneficios_con_paginacion(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        await create_beneficio(session, nombre="Almuerzo")
        await create_beneficio(session, nombre="Estacionamiento")
        await create_beneficio(session, nombre="Kit de bienvenida")
        await session.commit()

    response = await client.get(
        "/api/v1/maestros/beneficios",
        headers=headers,
        params={"page": 2, "page_size": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["pages"] == 2
    assert body["page"] == 2
    assert len(body["items"]) == 1


async def test_filtrar_beneficios_activos_y_buscar_por_nombre(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        await create_beneficio(session, nombre="Entrada Gratuita", estado=True)
        await create_beneficio(session, nombre="Entrada Histórica", estado=False)
        await create_beneficio(session, nombre="Kit de bienvenida", estado=True)
        await session.commit()

    active = await client.get(
        "/api/v1/maestros/beneficios",
        headers=headers,
        params={"estado": "true"},
    )
    search = await client.get(
        "/api/v1/maestros/beneficios",
        headers=headers,
        params={"search": "gratuita"},
    )

    assert active.status_code == 200
    assert active.json()["total"] == 2
    assert all(item["estado"] for item in active.json()["items"])
    assert search.status_code == 200
    assert search.json()["total"] == 1
    assert search.json()["items"][0]["nombre"] == "Entrada Gratuita"


async def test_actualizar_beneficio_y_auditar(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        beneficio = await create_beneficio(
            session,
            nombre="Almuerzo",
            condicion="Condición anterior",
        )
        await session.commit()
        id_beneficio = beneficio.id_beneficio

    response = await client.put(
        f"/api/v1/maestros/beneficios/{id_beneficio}",
        headers=headers,
        json={
            "nombre": "  Almuerzo   Ejecutivo ",
            "condicion": "  Nueva condición  ",
        },
    )

    assert response.status_code == 200
    assert response.json()["nombre"] == "Almuerzo Ejecutivo"
    assert response.json()["condicion"] == "Nueva condición"
    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ACTUALIZAR_BENEFICIO")
        )
    assert audit is not None
    assert audit.valor_anterior["nombre"] == "Almuerzo"
    assert audit.valor_nuevo["condicion"] == "Nueva condición"


async def test_actualizar_beneficio_no_permite_nombre_duplicado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        target = await create_beneficio(session, nombre="Almuerzo")
        await create_beneficio(session, nombre="Estacionamiento")
        await session.commit()
        id_beneficio = target.id_beneficio

    response = await client.put(
        f"/api/v1/maestros/beneficios/{id_beneficio}",
        headers=headers,
        json={"nombre": "estacionamiento", "condicion": None},
    )
    assert response.status_code == 409


async def test_inactivar_beneficio_es_idempotente_y_permite_reactivar(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        beneficio = await create_beneficio(session, nombre="Almuerzo")
        await session.commit()
        id_beneficio = beneficio.id_beneficio

    inactive = await client.patch(
        f"/api/v1/maestros/beneficios/{id_beneficio}/estado",
        headers=headers,
        json={"estado": False},
    )
    inactive_again = await client.patch(
        f"/api/v1/maestros/beneficios/{id_beneficio}/estado",
        headers=headers,
        json={"estado": False},
    )
    active_list = await client.get(
        "/api/v1/maestros/beneficios",
        headers=headers,
        params={"estado": "true", "search": "Almuerzo"},
    )
    active = await client.patch(
        f"/api/v1/maestros/beneficios/{id_beneficio}/estado",
        headers=headers,
        json={"estado": True},
    )

    assert inactive.status_code == 200
    assert inactive.json()["estado"] is False
    assert inactive_again.status_code == 200
    assert inactive_again.json()["estado"] is False
    assert active_list.status_code == 200
    assert active_list.json()["total"] == 0
    assert active.status_code == 200
    assert active.json()["id_beneficio"] == id_beneficio
    assert active.json()["estado"] is True

    async with session_factory() as session:
        stored = await session.get(Beneficio, id_beneficio)
        actions = set(
            (
                await session.scalars(
                    select(Auditoria.accion).where(Auditoria.entidad == "beneficio")
                )
            ).all()
        )
    assert stored is not None
    assert {"INACTIVAR_BENEFICIO", "REACTIVAR_BENEFICIO"} <= actions


async def test_no_permite_desactivar_beneficio_en_uso_por_evento_abierto(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        beneficio = await create_beneficio(session, nombre="Beneficio en uso")
        area = await create_area(session, nombre="Area beneficio en uso")
        evento = await _crear_evento_abierto_con_beneficio(
            session, beneficio=beneficio, area=area
        )
        await session.commit()
        id_beneficio = beneficio.id_beneficio
        nombre_evento = evento.nombre_evento

    response = await client.patch(
        f"/api/v1/maestros/beneficios/{id_beneficio}/estado",
        headers=headers,
        json={"estado": False},
    )

    assert response.status_code == 409, response.text
    assert nombre_evento in response.json()["detail"]

    async with session_factory() as session:
        stored = await session.get(Beneficio, id_beneficio)
    assert stored.estado is True


async def test_permite_desactivar_beneficio_en_uso_por_evento_finalizado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)
        beneficio = await create_beneficio(session, nombre="Beneficio evento cerrado")
        area = await create_area(session, nombre="Area beneficio cerrado")
        evento = await _crear_evento_abierto_con_beneficio(
            session, beneficio=beneficio, area=area
        )
        evento.estado = EventoEstado.FINALIZADO
        await session.commit()
        id_beneficio = beneficio.id_beneficio

    response = await client.patch(
        f"/api/v1/maestros/beneficios/{id_beneficio}/estado",
        headers=headers,
        json={"estado": False},
    )

    assert response.status_code == 200
    assert response.json()["estado"] is False


async def test_cambiar_estado_beneficio_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_maestro_actor(session)

    response = await client.patch(
        "/api/v1/maestros/beneficios/999999/estado",
        headers=headers,
        json={"estado": False},
    )
    assert response.status_code == 404
