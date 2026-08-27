import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.participantes.models import EventoContacto
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def test_service_rechaza_evento_contacto_duplicado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )

    url = (
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos"
    )
    payload = {"ids_contacto": [contacto.id_contacto]}
    assert (
        await client.post(url, headers=headers, json=payload)
    ).status_code == 201
    duplicate = await client.post(url, headers=headers, json=payload)

    assert duplicate.status_code == 409
    assert "ya participan" in duplicate.json()["detail"].lower()


async def test_constraint_bd_impide_misma_programacion_y_contacto(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    assert response.status_code == 201

    async with session_factory() as session:
        session.add(
            EventoContacto(
                id_programacion_evento=programacion.id_programacion_evento,
                id_contacto=contacto.id_contacto,
                id_empresa=contacto.id_empresa,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with session_factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(EventoContacto)
                .where(
                    EventoContacto.id_programacion_evento
                    == programacion.id_programacion_evento,
                    EventoContacto.id_contacto == contacto.id_contacto,
                )
            )
            == 1
        )
