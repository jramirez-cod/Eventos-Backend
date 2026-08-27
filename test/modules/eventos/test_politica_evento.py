import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.models import Categoria
from app.modules.maestros.models import Beneficio
from test.modules.eventos.conftest import (
    create_evento_dependencies,
    crear_evento_http,
    future_date,
    seed_event_actor,
)


pytestmark = pytest.mark.asyncio


async def test_actualizar_politica_reemplaza_fechas_y_detalles(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
    evento = await crear_evento_http(client, headers, session_factory)

    async with session_factory() as session:
        nuevo_beneficio = Beneficio(nombre="Beneficio Nuevo", estado=True)
        nueva_categoria = Categoria(nombre_categoria="Categoria Nueva", estado=True)
        session.add_all([nuevo_beneficio, nueva_categoria])
        await session.commit()
        id_beneficio, id_categoria = (
            nuevo_beneficio.id_beneficio,
            nueva_categoria.id_categoria,
        )

    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/politica",
        headers=headers,
        json={
            "fecha_inicio": future_date(20),
            "fecha_fin": future_date(90),
            "detalles": [
                {
                    "id_beneficio": id_beneficio,
                    "id_categoria": id_categoria,
                    "entradas_gratuitas": 5,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["politica"]["fecha_inicio"] == future_date(20)
    assert len(body["politica"]["detalles"]) == 1
    assert body["politica"]["detalles"][0]["entradas_gratuitas"] == 5

    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "ACTUALIZAR_POLITICA_EVENTO"
            )
        )
        assert audit is not None


async def test_actualizar_politica_evento_no_abierto_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        _, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        id_beneficio, id_categoria = beneficio.id_beneficio, categoria.id_categoria
    evento = await crear_evento_http(client, headers, session_factory)
    await client.patch(
        f"/api/v1/eventos/{evento['id_evento']}/inactivar",
        headers=headers,
        json={},
    )

    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/politica",
        headers=headers,
        json={
            "fecha_inicio": future_date(20),
            "fecha_fin": future_date(90),
            "detalles": [
                {
                    "id_beneficio": id_beneficio,
                    "id_categoria": id_categoria,
                    "entradas_gratuitas": 1,
                }
            ],
        },
    )
    assert response.status_code == 409


async def test_actualizar_politica_con_beneficio_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        _, _, categoria = await create_evento_dependencies(session)
        await session.commit()
        id_categoria = categoria.id_categoria
    evento = await crear_evento_http(client, headers, session_factory)

    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/politica",
        headers=headers,
        json={
            "fecha_inicio": future_date(20),
            "fecha_fin": future_date(90),
            "detalles": [
                {
                    "id_beneficio": 999999,
                    "id_categoria": id_categoria,
                    "entradas_gratuitas": 1,
                }
            ],
        },
    )
    assert response.status_code == 404


async def test_politica_con_detalles_duplicados_recibe_422(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_event_actor(session)
        _, beneficio, categoria = await create_evento_dependencies(session)
        await session.commit()
        id_beneficio, id_categoria = beneficio.id_beneficio, categoria.id_categoria
    evento = await crear_evento_http(client, headers, session_factory)

    detalle = {
        "id_beneficio": id_beneficio,
        "id_categoria": id_categoria,
        "entradas_gratuitas": 1,
    }
    response = await client.put(
        f"/api/v1/eventos/{evento['id_evento']}/politica",
        headers=headers,
        json={
            "fecha_inicio": future_date(20),
            "fecha_fin": future_date(90),
            "detalles": [detalle, dict(detalle)],
        },
    )
    assert response.status_code == 422
