import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.eventos.models import EventoEstado, ProgramacionEvento
from app.modules.participantes.models import (
    CodigoAccesoPrincipal,
    EventoContacto,
    EventoEmpresa,
    ParticipanteQr,
)
from test.modules.contactos.conftest import create_empresa
from test.modules.participantes.conftest import (
    create_programacion,
    evento_contacto_context,
    next_sequence,
    seed_participante_actor,
)


pytestmark = pytest.mark.asyncio


async def test_desafiliar_empresa_sin_contactos_ni_codigo(
    client, session_factory
) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        _, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session, sequence=sequence)
        empresa = await create_empresa(session, sequence=30_000 + sequence)
        await session.commit()

    afiliada = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}/empresas",
        headers=headers,
        json={"id_empresa": empresa.id_empresa},
    )
    id_evento_empresa = afiliada.json()["id_evento_empresa"]

    respuesta = await client.delete(
        f"/api/v1/participantes/empresas/{id_evento_empresa}",
        headers=headers,
        params={"motivo": "Empresa se retiró del evento"},
    )
    assert respuesta.status_code == 204, respuesta.text

    async with session_factory() as session:
        fila = await session.get(EventoEmpresa, id_evento_empresa)
        assert fila.estado is False
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "DESAFILIAR_EMPRESA_EVENTO")
        )
        assert audit is not None
        assert audit.motivo == "Empresa se retiró del evento"

    listado = await client.get(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}/empresas",
        headers=headers,
    )
    assert listado.json() == []


async def test_desafiliar_empresa_invalida_codigo_y_desactiva_contactos(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    id_prog = programacion.id_programacion_evento

    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={},
    )
    agregado = await client.post(
        f"/api/v1/participantes/programaciones/{id_prog}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    id_ec = agregado.json()["evento_contactos"][0]["id_evento_contacto"]

    async with session_factory() as session:
        qr = await session.scalar(
            select(ParticipanteQr).where(ParticipanteQr.id_evento_contacto == id_ec)
        )
        assert qr is not None and qr.estado is True

    respuesta = await client.delete(
        f"/api/v1/participantes/empresas/{id_evento_empresa}",
        headers=headers,
    )
    assert respuesta.status_code == 204, respuesta.text

    async with session_factory() as session:
        codigo = await session.scalar(
            select(CodigoAccesoPrincipal).where(
                CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa
            )
        )
        assert codigo.estado is False

        evento_contacto = await session.get(EventoContacto, id_ec)
        assert evento_contacto.estado is False

        qr = await session.scalar(
            select(ParticipanteQr).where(ParticipanteQr.id_evento_contacto == id_ec)
        )
        assert qr.estado is False


async def test_reafiliar_empresa_previamente_desafiliada(
    client, session_factory
) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        _, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session, sequence=sequence)
        empresa = await create_empresa(session, sequence=30_000 + sequence)
        await session.commit()

    url = f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}/empresas"
    primera = await client.post(url, headers=headers, json={"id_empresa": empresa.id_empresa})
    id_evento_empresa = primera.json()["id_evento_empresa"]

    await client.delete(
        f"/api/v1/participantes/empresas/{id_evento_empresa}", headers=headers
    )

    reafiliada = await client.post(
        url, headers=headers, json={"id_empresa": empresa.id_empresa}
    )
    assert reafiliada.status_code == 201, reafiliada.text
    assert reafiliada.json()["id_evento_empresa"] == id_evento_empresa
    assert reafiliada.json()["estado"] is True

    async with session_factory() as session:
        total = await session.scalar(
            select(EventoEmpresa).where(
                EventoEmpresa.id_programacion_evento
                == programacion.id_programacion_evento,
                EventoEmpresa.id_empresa == empresa.id_empresa,
            )
        )
        assert total is not None
        audit_reafiliar = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "REAFILIAR_EMPRESA_EVENTO")
        )
        assert audit_reafiliar is not None


async def test_desafiliar_empresa_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_participante_actor(session)

    respuesta = await client.delete(
        "/api/v1/participantes/empresas/999999", headers=headers
    )
    assert respuesta.status_code == 404


async def test_desafiliar_empresa_en_programacion_no_abierta_recibe_409(
    client, session_factory
) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        _, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session, sequence=sequence)
        empresa = await create_empresa(session, sequence=30_000 + sequence)
        await session.commit()

    afiliada = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}/empresas",
        headers=headers,
        json={"id_empresa": empresa.id_empresa},
    )
    id_evento_empresa = afiliada.json()["id_evento_empresa"]

    async with session_factory() as session:
        prog_row = await session.get(ProgramacionEvento, programacion.id_programacion_evento)
        prog_row.estado = EventoEstado.FINALIZADO
        await session.commit()

    respuesta = await client.delete(
        f"/api/v1/participantes/empresas/{id_evento_empresa}", headers=headers
    )
    assert respuesta.status_code == 409, respuesta.text
