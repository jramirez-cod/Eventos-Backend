import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.eventos.models import EventoEstado
from app.modules.participantes.models import EventoContacto, EventoEmpresa
from test.modules.contactos.conftest import create_empresa
from test.modules.participantes.conftest import (
    create_programacion,
    next_sequence,
    seed_participante_actor,
)
from test.modules.usuarios.conftest import auth_header, create_role, create_user


pytestmark = pytest.mark.asyncio


async def test_empresa_puede_afiliarse_sin_contactos_y_genera_auditoria(
    client, session_factory
) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        _, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session, sequence=sequence)
        empresa = await create_empresa(session, sequence=30_000 + sequence)
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/empresas",
        headers=headers,
        json={"id_empresa": empresa.id_empresa},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_programacion_evento"] == programacion.id_programacion_evento
    assert body["id_empresa"] == empresa.id_empresa
    assert body["estado"] is True

    async with session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(EventoContacto))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(Auditoria)
                .where(Auditoria.accion == "AFILIAR_EMPRESA_EVENTO")
            )
            == 1
        )


async def test_afiliacion_duplicada_devuelve_409_y_no_duplica(
    client, session_factory
) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        _, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session, sequence=sequence)
        empresa = await create_empresa(session, sequence=30_000 + sequence)
        await session.commit()

    url = (
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/empresas"
    )
    first = await client.post(
        url, headers=headers, json={"id_empresa": empresa.id_empresa}
    )
    second = await client.post(
        url, headers=headers, json={"id_empresa": empresa.id_empresa}
    )

    assert first.status_code == 201
    assert second.status_code == 409
    async with session_factory() as session:
        assert (
            await session.scalar(select(func.count()).select_from(EventoEmpresa))
            == 1
        )


@pytest.mark.parametrize("estado", [EventoEstado.FINALIZADO, EventoEstado.INACTIVO])
async def test_no_afilia_empresa_a_evento_no_abierto(
    client, session_factory, estado
) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        _, headers = await seed_participante_actor(session)
        programacion = await create_programacion(
            session, sequence=sequence, evento_estado=estado
        )
        empresa = await create_empresa(session, sequence=30_000 + sequence)
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/empresas",
        headers=headers,
        json={"id_empresa": empresa.id_empresa},
    )
    assert response.status_code == 409


async def test_no_afilia_empresa_inactiva(client, session_factory) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        _, headers = await seed_participante_actor(session)
        programacion = await create_programacion(session, sequence=sequence)
        empresa = await create_empresa(
            session, sequence=30_000 + sequence, estado=False
        )
        await session.commit()

    response = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/empresas",
        headers=headers,
        json={"id_empresa": empresa.id_empresa},
    )
    assert response.status_code == 409


async def test_afiliar_requiere_autenticacion_y_permiso(
    client, session_factory
) -> None:
    async with session_factory() as session:
        sequence = next_sequence()
        role = await create_role(session, "Sin permiso participantes")
        actor = await create_user(
            session, role, username="sin.permiso.participantes"
        )
        programacion = await create_programacion(session, sequence=sequence)
        empresa = await create_empresa(session, sequence=30_000 + sequence)
        await session.commit()
        headers = auth_header(actor)

    url = (
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/empresas"
    )
    assert (
        await client.post(url, json={"id_empresa": empresa.id_empresa})
    ).status_code == 401
    assert (
        await client.post(
            url, headers=headers, json={"id_empresa": empresa.id_empresa}
        )
    ).status_code == 403
