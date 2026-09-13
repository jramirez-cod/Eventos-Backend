from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.modules.contactos.models import Contacto
from app.modules.eventos.models import DetalleProgramacionEvento
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
        expira_en_lima = codigo.expira_en.astimezone(ZoneInfo("America/Lima"))
        assert expira_en_lima.date() == date.today() + timedelta(days=10)
        assert expira_en_lima.time() == time(18, 0)


async def test_codigo_creado_para_evento_de_manana_no_nace_expirado(
    client, session_factory, monkeypatch
) -> None:
    codigo_plano = "ABCD1234"
    monkeypatch.setattr(
        "app.modules.participantes.service.generate_portal_code",
        lambda: codigo_plano,
    )
    async with session_factory() as session:
        _, headers, programacion, _, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        dia = await session.scalar(
            select(DetalleProgramacionEvento).where(
                DetalleProgramacionEvento.id_programacion_evento
                == programacion.id_programacion_evento
            )
        )
        assert dia is not None
        dia.fecha = datetime.now(ZoneInfo("America/Lima")).date() + timedelta(days=1)
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    principal = await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    assert principal.status_code == 200, principal.text

    envio = await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={},
    )
    assert envio.status_code == 200, envio.text

    validacion = await client.post(
        "/api/v1/portal/validar-codigo",
        json={"codigo": codigo_plano},
    )
    assert validacion.status_code == 200, validacion.text

    async with session_factory() as session:
        codigo = await session.scalar(
            select(CodigoAccesoPrincipal).where(
                CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
                CodigoAccesoPrincipal.estado.is_(True),
            )
        )
        assert codigo is not None
        expira_en_lima = codigo.expira_en.astimezone(ZoneInfo("America/Lima"))
        assert expira_en_lima.date() == datetime.now(
            ZoneInfo("America/Lima")
        ).date() + timedelta(days=1)
        assert expira_en_lima.time() == time(18, 0)


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
                    "numero_documento": f"INV{i:05d}",
                    "correo": f"invitado{i}@example.com",
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
        json={
            "nombres": "Uno mas",
            "apellidos": "Prueba",
            "numero_documento": "INV99999",
            "correo": "invitado-limite@example.com",
        },
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


async def test_codigo_para_evento_de_hoy_sirve_hasta_que_termina_el_dia(
    client, session_factory, monkeypatch
) -> None:
    """Caso real: evento creado para hoy mismo (p. ej. de 13:00 a 14:00).

    Con la regla anterior (vencer el día previo) el código nacía vencido y el
    portal lo rechazaba, dejando sin portal a cualquier evento creado con poca
    antelación. La hora de fin se calcula desde "ahora" para que la prueba no
    dependa de la hora en que se ejecute.
    """
    codigo_plano = "HOY12345"
    monkeypatch.setattr(
        "app.modules.participantes.service.generate_portal_code",
        lambda: codigo_plano,
    )

    ahora_lima = datetime.now(ZoneInfo("America/Lima"))
    hoy = ahora_lima.date()
    # Ventana que siempre termina más tarde que "ahora", sin cruzar la medianoche.
    hora_fin = time(23, 59) if ahora_lima.hour >= 22 else time(ahora_lima.hour + 1, 0)
    hora_inicio = time(ahora_lima.hour, 0)

    async with session_factory() as session:
        _, headers, programacion, _, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        await session.commit()

    async with session_factory() as session:
        dia = await session.scalar(
            select(DetalleProgramacionEvento).where(
                DetalleProgramacionEvento.id_programacion_evento
                == programacion.id_programacion_evento
            )
        )
        assert dia is not None
        dia.fecha = hoy
        dia.hora_inicio = hora_inicio
        dia.hora_fin = hora_fin
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    principal = await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    assert principal.status_code == 200, principal.text

    envio = await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={},
    )
    assert envio.status_code == 200, envio.text

    # El contacto principal puede usarlo de inmediato.
    validacion = await client.post(
        "/api/v1/portal/validar-codigo",
        json={"codigo": codigo_plano},
    )
    assert validacion.status_code == 200, validacion.text

    async with session_factory() as session:
        codigo = await session.scalar(
            select(CodigoAccesoPrincipal).where(
                CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
                CodigoAccesoPrincipal.estado.is_(True),
            )
        )
        assert codigo is not None
        expira_en_lima = codigo.expira_en.astimezone(ZoneInfo("America/Lima"))
        assert expira_en_lima.date() == hoy
        assert expira_en_lima.time() == hora_fin


async def test_codigo_usa_fin_del_dia_cuando_el_dia_no_tiene_hora_fin(
    client, session_factory
) -> None:
    """hora_fin es opcional en el modelo: sin ella se usa el fin del día."""
    async with session_factory() as session:
        _, headers, programacion, _, contacto, afiliacion = (
            await evento_contacto_context(session, client)
        )
        await session.commit()

    async with session_factory() as session:
        dia = await session.scalar(
            select(DetalleProgramacionEvento).where(
                DetalleProgramacionEvento.id_programacion_evento
                == programacion.id_programacion_evento
            )
        )
        assert dia is not None
        dia.hora_fin = None
        fecha_dia = dia.fecha
        await session.commit()

    id_evento_empresa = afiliacion["id_evento_empresa"]
    await client.patch(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal",
        headers=headers,
        json={"id_contacto": contacto.id_contacto},
    )
    envio = await client.post(
        f"/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo",
        headers=headers,
        json={},
    )
    assert envio.status_code == 200, envio.text

    async with session_factory() as session:
        codigo = await session.scalar(
            select(CodigoAccesoPrincipal).where(
                CodigoAccesoPrincipal.id_evento_empresa == id_evento_empresa,
                CodigoAccesoPrincipal.estado.is_(True),
            )
        )
        assert codigo is not None
        expira_en_lima = codigo.expira_en.astimezone(ZoneInfo("America/Lima"))
        assert expira_en_lima.date() == fecha_dia
        assert expira_en_lima.time() == time.max
