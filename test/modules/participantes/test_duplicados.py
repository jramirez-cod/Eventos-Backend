import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.participantes.models import Participante
from test.modules.participantes.conftest import participante_context


pytestmark = pytest.mark.asyncio


async def test_service_rechaza_participante_duplicado(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers, evento, _, contacto, afiliacion = await participante_context(
            session, client
        )

    url = f"/api/v1/participantes/eventos/{evento.id_evento}"
    payload = {
        "id_evento_empresa": afiliacion["id_evento_empresa"],
        "ids_contacto": [contacto.id_contacto],
    }
    assert (await client.post(url, headers=headers, json=payload)).status_code == 201
    duplicate = await client.post(url, headers=headers, json=payload)

    assert duplicate.status_code == 409
    assert "ya participa" in duplicate.json()["detail"].lower()


async def test_constraint_bd_impide_mismo_evento_y_contacto(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers, evento, _, contacto, afiliacion = await participante_context(
            session, client
        )

    response = await client.post(
        f"/api/v1/participantes/eventos/{evento.id_evento}",
        headers=headers,
        json={
            "id_evento_empresa": afiliacion["id_evento_empresa"],
            "ids_contacto": [contacto.id_contacto],
        },
    )
    assert response.status_code == 201

    async with session_factory() as session:
        session.add(
            Participante(
                id_evento_empresa=afiliacion["id_evento_empresa"],
                id_evento=evento.id_evento,
                id_contacto=contacto.id_contacto,
                creado_por=actor.id_usuario,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()

    async with session_factory() as session:
        assert await session.scalar(
            select(func.count()).select_from(Participante).where(
                Participante.id_evento == evento.id_evento,
                Participante.id_contacto == contacto.id_contacto,
            )
        ) == 1
