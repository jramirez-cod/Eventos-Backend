import pytest
from sqlalchemy import select

from app.modules.auditoria.models import Auditoria
from app.modules.participantes.models import CodigoAccesoPrincipal
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def test_reenviar_codigo_acceso_invalida_el_anterior_y_crea_uno_nuevo(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers, _, _, contacto, afiliacion = await evento_contacto_context(
            session, client
        )
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    primero = await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={"motivo": "Primer envío"},
    )
    assert primero.status_code == 200, primero.text

    async with session_factory() as session:
        codigo_inicial = await session.scalar(
            select(CodigoAccesoPrincipal).where(
                CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
                CodigoAccesoPrincipal.estado.is_(True),
            )
        )
        assert codigo_inicial is not None
        id_codigo_inicial = codigo_inicial.id_codigo_acceso_principal

    segundo = await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={"motivo": "El contacto no encontró el correo"},
    )
    assert segundo.status_code == 200, segundo.text

    async with session_factory() as session:
        codigo_anterior = await session.get(
            CodigoAccesoPrincipal, id_codigo_inicial
        )
        assert codigo_anterior.estado is False
        vigentes = list(
            (
                await session.scalars(
                    select(CodigoAccesoPrincipal).where(
                        CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
                        CodigoAccesoPrincipal.estado.is_(True),
                    )
                )
            ).all()
        )
        assert len(vigentes) == 1
        assert vigentes[0].id_codigo_acceso_principal != id_codigo_inicial

        audits = list(
            (
                await session.scalars(
                    select(Auditoria).where(
                        Auditoria.accion == "ENVIAR_CODIGO_ACCESO"
                    )
                )
            ).all()
        )
    assert len(audits) == 2
    assert audits[-1].motivo == "El contacto no encontró el correo"
    assert all(audit.id_usuario == actor.id_usuario for audit in audits)


async def test_reenviar_codigo_sin_contacto_principal_recibe_400(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, _, _, _, afiliacion = await evento_contacto_context(
            session, client
        )
        await session.commit()

    respuesta = await client.post(
        f"/api/v1/participantes/empresas/{afiliacion['id_evento_empresa']}"
        "/reenviar-codigo",
        headers=headers,
        json={},
    )
    assert respuesta.status_code == 400, respuesta.text


async def test_no_envia_codigo_si_el_primer_dia_ya_termino(
    client, session_factory
) -> None:
    """Un código para un día ya terminado nace vencido: avisar, no enviarlo.

    El portal lo rechazaría al validarlo, así que el contacto recibiría un
    correo con un código muerto y sin explicación.
    """
    from datetime import date, timedelta

    from sqlalchemy import update

    from app.modules.eventos.models import DetalleProgramacionEvento

    async with session_factory() as session:
        _, headers, programacion, _, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    respuesta = await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    assert respuesta.status_code == 200, respuesta.text

    async with session_factory() as session:
        await session.execute(
            update(DetalleProgramacionEvento)
            .where(
                DetalleProgramacionEvento.id_programacion_evento
                == programacion.id_programacion_evento
            )
            .values(fecha=date.today() - timedelta(days=3))
        )
        await session.commit()

    envio = await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={"motivo": "prueba"},
    )

    assert envio.status_code == 409, envio.text
    assert "ya terminó" in envio.json()["detail"]

    async with session_factory() as session:
        vigentes = list(
            (
                await session.scalars(
                    select(CodigoAccesoPrincipal).where(
                        CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
                        CodigoAccesoPrincipal.estado.is_(True),
                    )
                )
            ).all()
        )
        assert vigentes == []
