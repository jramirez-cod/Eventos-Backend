from datetime import date, timedelta, timezone

import pytest
from sqlalchemy import select

from app.modules.contactos.models import Contacto
from app.modules.participantes.models import CodigoAccesoPrincipal, ParticipanteQr
from test.modules.contactos.conftest import create_contacto
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def test_reasignar_contacto_principal_invalida_codigo_anterior_y_permite_reenvio(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor, headers, programacion, empresa, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        otro = await create_contacto(
            session, empresa=empresa, actor=actor, sequence=50_001
        )
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]

    response = await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    assert response.status_code == 200, response.text
    assert response.json()["id_contacto_principal"] == contacto.id_contacto

    cambio = await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": otro.id_contacto},
    )
    assert cambio.status_code == 200, cambio.text
    assert cambio.json()["id_contacto_principal"] == otro.id_contacto

    envio = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        "/empresas/enviar-codigo-masivo",
        headers=headers,
    )
    assert envio.status_code == 200, envio.text
    assert envio.json() == {"enviados": 1, "omitidos": 0, "ya_enviados": 0}

    async with session_factory() as session:
        codigo_anterior = await session.scalar(
            select(CodigoAccesoPrincipal).where(
                CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
                CodigoAccesoPrincipal.estado.is_(True),
            )
        )
        assert codigo_anterior is not None
        id_codigo_anterior = codigo_anterior.id_codigo_acceso_principal

    # El envío masivo vuelve a correr sin cambios: como ya hay un código
    # vigente enviado al principal actual, se omite en vez de reenviarse.
    reenvio_omitido = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        "/empresas/enviar-codigo-masivo",
        headers=headers,
    )
    assert reenvio_omitido.status_code == 200, reenvio_omitido.text
    assert reenvio_omitido.json() == {"enviados": 0, "omitidos": 0, "ya_enviados": 1}

    # Cambiar el contacto principal ya no bloquea; en cambio invalida el
    # código que se le había enviado a la persona anterior.
    reasignado = await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    assert reasignado.status_code == 200, reasignado.text
    assert reasignado.json()["id_contacto_principal"] == contacto.id_contacto

    async with session_factory() as session:
        codigo_invalidado = await session.get(
            CodigoAccesoPrincipal, id_codigo_anterior
        )
        assert codigo_invalidado is not None
        assert codigo_invalidado.estado is False

    reenvio_tras_cambio = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        "/empresas/enviar-codigo-masivo",
        headers=headers,
    )
    assert reenvio_tras_cambio.status_code == 200, reenvio_tras_cambio.text
    assert reenvio_tras_cambio.json() == {
        "enviados": 1,
        "omitidos": 0,
        "ya_enviados": 0,
    }


async def test_codigo_expira_un_dia_antes_del_primer_dia(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, empresa, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        "/empresas/enviar-codigo-masivo",
        headers=headers,
    )

    async with session_factory() as session:
        codigo = await session.scalar(
            select(CodigoAccesoPrincipal).where(
                CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa
            )
        )
        assert codigo is not None
        expira_en_utc = codigo.expira_en.astimezone(timezone.utc)
        assert expira_en_utc.date() == date.today() + timedelta(days=9)


async def test_invitado_sin_registrar_no_crea_contacto_y_respeta_limite(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, empresa, _, _ = await evento_contacto_context(
            session, client
        )
        await session.commit()

    async with session_factory() as session:
        antes = await session.scalar(select(Contacto.id_contacto))

    for i in range(20):
        response = await client.post(
            f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
            f"/empresas/{empresa.id_empresa}/invitados",
            headers=headers,
            json={
                "nombres": f"Invitado{i}",
                "apellidos": "Prueba",
                "numero_documento": None,
                "correo": None,
                "celular": None,
            },
        )
        assert response.status_code == 201, response.text
        assert response.json()["es_invitado"] is True
        assert response.json()["id_contacto"] is None

    limite = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        f"/empresas/{empresa.id_empresa}/invitados",
        headers=headers,
        json={"nombres": "Uno mas", "apellidos": "Prueba"},
    )
    assert limite.status_code == 409, limite.text

    async with session_factory() as session:
        total_contactos = await session.scalar(
            select(Contacto.id_contacto).order_by(Contacto.id_contacto.desc()).limit(1)
        )
        # No se creó ningún Contacto nuevo por los invitados sin registrar.
        assert total_contactos == antes


async def test_desactivar_evento_contacto_invalida_qr_activo(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )
        await session.commit()

    created = await client.post(
        f"/api/v1/participantes/programaciones/{programacion.id_programacion_evento}"
        f"/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    id_evento_contacto = created.json()["evento_contactos"][0]["id_evento_contacto"]

    async with session_factory() as session:
        qr = await session.scalar(
            select(ParticipanteQr).where(
                ParticipanteQr.id_evento_contacto == id_evento_contacto
            )
        )
        assert qr is not None and qr.estado is True

    response = await client.patch(
        f"/api/v1/participantes/evento-contactos/{id_evento_contacto}/estado",
        headers=headers,
        json={"estado": False},
    )
    assert response.status_code == 200, response.text
    assert response.json()["estado"] is False

    async with session_factory() as session:
        qr = await session.scalar(
            select(ParticipanteQr).where(
                ParticipanteQr.id_evento_contacto == id_evento_contacto
            )
        )
        assert qr is not None and qr.estado is False
