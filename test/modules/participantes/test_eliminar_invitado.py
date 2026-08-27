import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.participantes.models import EventoContacto
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def test_eliminar_invitado_sin_registrar(client, session_factory) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, _, _ = await evento_contacto_context(
            session, client
        )
        await session.commit()

    creado = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        f"/empresas/{empresa.id_empresa}/invitados",
        headers=headers,
        json={
            "nombres": "Invitado",
            "apellidos": "Suelto",
            "numero_documento": None,
            "correo": None,
            "celular": None,
        },
    )
    assert creado.status_code == 201, creado.text
    id_evento_contacto = creado.json()["id_evento_contacto"]

    eliminado = await client.delete(
        f"/api/v1/participantes/evento-contactos/{id_evento_contacto}",
        headers=headers,
        params={"motivo": "Invitado registrado por error"},
    )
    assert eliminado.status_code == 204, eliminado.text

    async with session_factory() as session:
        fila = await session.get(EventoContacto, id_evento_contacto)
        assert fila is None
        audit = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ELIMINAR_INVITADO")
        )
        assert audit is not None
        assert audit.id_usuario == actor.id_usuario
        assert audit.motivo == "Invitado registrado por error"


async def test_no_se_puede_eliminar_un_contacto_registrado(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )
        await session.commit()

    creado = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        f"/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    id_evento_contacto = creado.json()["evento_contactos"][0]["id_evento_contacto"]

    respuesta = await client.delete(
        f"/api/v1/participantes/evento-contactos/{id_evento_contacto}",
        headers=headers,
    )
    assert respuesta.status_code == 400, respuesta.text

    async with session_factory() as session:
        fila = await session.get(EventoContacto, id_evento_contacto)
        assert fila is not None


async def test_eliminar_invitado_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, _, _, _, _ = await evento_contacto_context(session, client)
        await session.commit()

    respuesta = await client.delete(
        "/api/v1/participantes/evento-contactos/999999", headers=headers
    )
    assert respuesta.status_code == 404
