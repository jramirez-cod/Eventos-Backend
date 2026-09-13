import pytest
from sqlalchemy import select

from app.modules.participantes.models import ParticipanteQr
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def test_reenviar_qr_de_participante_reactivado_reutiliza_registro(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )

    agregar = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    assert agregar.status_code == 201, agregar.text
    id_evento_contacto = agregar.json()["evento_contactos"][0][
        "id_evento_contacto"
    ]

    async with session_factory() as session:
        qr_inicial = await session.scalar(
            select(ParticipanteQr).where(
                ParticipanteQr.id_evento_contacto == id_evento_contacto
            )
        )
        assert qr_inicial is not None
        id_qr = qr_inicial.id_participante_qr
        codigo_inicial = qr_inicial.codigo_seguro

    for estado in (False, True):
        response = await client.patch(
            f"/api/v1/participantes/evento-contactos/{id_evento_contacto}/estado",
            headers=headers,
            json={"estado": estado},
        )
        assert response.status_code == 200, response.text

    envio = await client.post(
        f"/api/v1/participantes/evento-contactos/{id_evento_contacto}/qr/enviar",
        headers=headers,
    )
    assert envio.status_code == 200, envio.text
    assert envio.json()["qr_enviado"] is True

    async with session_factory() as session:
        registros = list(
            (
                await session.scalars(
                    select(ParticipanteQr).where(
                        ParticipanteQr.id_evento_contacto == id_evento_contacto
                    )
                )
            ).all()
        )

    assert len(registros) == 1
    assert registros[0].id_participante_qr == id_qr
    assert registros[0].codigo_seguro != codigo_inicial
    assert registros[0].estado is True
    assert registros[0].fecha_envio is not None
