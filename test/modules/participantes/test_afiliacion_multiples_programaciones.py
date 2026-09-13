"""Escenario real que dejaba todo bloqueado.

La afiliación (evento_empresa) se comparte entre las programaciones de un
evento. Cuando se finaliza la programación vieja y se crea una nueva, las
acciones que llegan solo con id_evento_empresa (reenviar código, contacto
principal, quitar empresa, portal) resolvían la programación por `min(id)`:
la finalizada. Todo respondía "La programación debe estar ABIERTA".
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.modules.eventos.models import Evento, EventoEstado, ProgramacionEvento
from app.modules.participantes.models import CodigoAccesoPrincipal
from test.modules.participantes.conftest import (
    crear_programacion_con_dia,
    evento_contacto_context,
)


pytestmark = pytest.mark.asyncio


async def _evento_con_programacion_vieja_finalizada_y_nueva_abierta(
    session_factory, client
) -> dict[str, object]:
    async with session_factory() as session:
        _, headers, prog_vieja, empresa, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        evento = await session.get(Evento, prog_vieja.id_evento)
        assert evento is not None
        prog_nueva = await crear_programacion_con_dia(
            session,
            evento=evento,
            empresa=empresa,
            fecha=date.today() + timedelta(days=20),
        )
        vieja = await session.get(ProgramacionEvento, prog_vieja.id_programacion_evento)
        assert vieja is not None
        vieja.estado = EventoEstado.FINALIZADO
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    principal = await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    assert principal.status_code == 200, principal.text
    assert principal.json()["id_programacion_evento"] == prog_nueva.id_programacion_evento

    return {
        "headers": headers,
        "id_evento_empresa": id_evento_empresa,
        "vieja": prog_vieja.id_programacion_evento,
        "nueva": prog_nueva.id_programacion_evento,
    }


async def test_reenviar_codigo_sin_programacion_usa_la_abierta(
    client, session_factory, monkeypatch
) -> None:
    codigo_plano = "NUEVA123"
    monkeypatch.setattr(
        "app.modules.participantes.service.generate_portal_code",
        lambda: codigo_plano,
    )
    ctx = await _evento_con_programacion_vieja_finalizada_y_nueva_abierta(
        session_factory, client
    )

    envio = await client.post(
        f"/api/v1/participantes/empresas/{ctx['id_evento_empresa']}/reenviar-codigo",
        headers=ctx["headers"],
        json={},
    )
    assert envio.status_code == 200, envio.text
    assert envio.json()["id_programacion_evento"] == ctx["nueva"]

    # El portal también debe aterrizar en la programación abierta.
    validacion = await client.post(
        "/api/v1/portal/validar-codigo", json={"codigo": codigo_plano}
    )
    assert validacion.status_code == 200, validacion.text
    token = validacion.json()["portal_token"]
    contactos = await client.get(
        "/api/v1/portal/contactos", headers={"Authorization": f"Bearer {token}"}
    )
    assert contactos.status_code == 200, contactos.text


async def test_programacion_explicita_se_respeta(
    client, session_factory
) -> None:
    ctx = await _evento_con_programacion_vieja_finalizada_y_nueva_abierta(
        session_factory, client
    )
    base = f"/api/v1/participantes/empresas/{ctx['id_evento_empresa']}/reenviar-codigo"

    explicita_nueva = await client.post(
        base,
        headers=ctx["headers"],
        params={"id_programacion_evento": ctx["nueva"]},
        json={},
    )
    assert explicita_nueva.status_code == 200, explicita_nueva.text
    assert explicita_nueva.json()["id_programacion_evento"] == ctx["nueva"]

    explicita_vieja = await client.post(
        base,
        headers=ctx["headers"],
        params={"id_programacion_evento": ctx["vieja"]},
        json={},
    )
    assert explicita_vieja.status_code == 409, explicita_vieja.text
    assert "ABIERTA" in explicita_vieja.json()["detail"]


async def test_quitar_empresa_sin_programacion_usa_la_abierta(
    client, session_factory
) -> None:
    ctx = await _evento_con_programacion_vieja_finalizada_y_nueva_abierta(
        session_factory, client
    )
    quitar = await client.delete(
        f"/api/v1/participantes/empresas/{ctx['id_evento_empresa']}",
        headers=ctx["headers"],
    )
    assert quitar.status_code == 204, quitar.text

    async with session_factory() as session:
        vigentes = list(
            (
                await session.scalars(
                    select(CodigoAccesoPrincipal).where(
                        CodigoAccesoPrincipal.id_evento_empresa
                        == ctx["id_evento_empresa"],
                        CodigoAccesoPrincipal.estado.is_(True),
                    )
                )
            ).all()
        )
        assert vigentes == []


async def test_sin_programacion_abierta_resuelve_la_mas_reciente(
    client, session_factory
) -> None:
    """Si todas están cerradas no hay nada que hacer, pero el error debe ser
    el de programación cerrada, no un 404 ni un 500."""
    ctx = await _evento_con_programacion_vieja_finalizada_y_nueva_abierta(
        session_factory, client
    )
    async with session_factory() as session:
        nueva = await session.get(ProgramacionEvento, ctx["nueva"])
        assert nueva is not None
        nueva.estado = EventoEstado.FINALIZADO
        await session.commit()

    envio = await client.post(
        f"/api/v1/participantes/empresas/{ctx['id_evento_empresa']}/reenviar-codigo",
        headers=ctx["headers"],
        json={},
    )
    assert envio.status_code == 409, envio.text
    assert "ABIERTA" in envio.json()["detail"]
