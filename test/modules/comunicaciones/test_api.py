from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.modules.auditoria.models import Auditoria
from app.modules.comunicaciones.email_service import (
    ParticipanteQrEmail,
    SMTPEmailSender,
)
from app.modules.comunicaciones.models import (
    CorreoEnvio,
    CorreoPlantilla,
    CorreoPlantillaHistorial,
)
from app.modules.comunicaciones.service import CorreoDeliveryService
from test.modules.comunicaciones import seed_comunicacion_actor
from test.modules.usuarios.conftest import auth_header, create_role, create_user


pytestmark = pytest.mark.asyncio


async def test_qr_participante_codifica_el_codigo_plano() -> None:
    service = CorreoDeliveryService(None)  # type: ignore[arg-type]
    notifier = AsyncMock()
    service._notify_with_console_fallback = notifier  # type: ignore[method-assign]

    await service.notify_participante_qr(
        ParticipanteQrEmail(
            sender_email="codip@example.com",
            recipient_email="participante@example.com",
            recipient_name="Participante",
            codigo_seguro="CODIGO-PLANO-QR",
        )
    )

    assert notifier.await_args.kwargs["qr_url"] == "CODIGO-PLANO-QR"
    # Por seguridad el código solo viaja dentro del QR, nunca en texto.
    assert notifier.await_args.kwargs["contexto"] == {"recipient_name": "Participante"}


async def test_listado_requiere_autenticacion(client) -> None:
    response = await client.get("/api/v1/comunicaciones/plantillas")
    assert response.status_code == 401


async def test_usuario_sin_permiso_recibe_403(client, session_factory) -> None:
    async with session_factory() as session:
        role = await create_role(session, "Sin permisos correo")
        actor = await create_user(session, role, username="sin.correo")
        await session.commit()
        headers = auth_header(actor)

    response = await client.get(
        "/api/v1/comunicaciones/plantillas", headers=headers
    )
    assert response.status_code == 403


async def test_lista_y_obtiene_las_cuatro_plantillas(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)

    response = await client.get(
        "/api/v1/comunicaciones/plantillas", headers=headers
    )
    assert response.status_code == 200
    assert {item["codigo"] for item in response.json()} == {
        "PRIMER_INGRESO",
        "RECUPERACION_PASSWORD",
        "QR_PARTICIPANTE",
        "ACCESO_EMPRESA",
    }

    detail = await client.get(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["version_actual"] == 1
    assert "code" in detail.json()["variables_permitidas"]


async def test_actualiza_version_historial_y_auditoria(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)

    payload = {
        "asunto": "Bienvenido {{ recipient_name }}",
        "cuerpo_html": "<html><body><p>Código: {{ code }}</p></body></html>",
        "cuerpo_texto": "Código: {{ code }}",
        "estado": True,
        "version_esperada": 1,
        "motivo": "Actualización de identidad corporativa",
    }
    response = await client.put(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 200
    assert response.json()["version_actual"] == 2

    async with session_factory() as session:
        plantilla = await session.scalar(
            select(CorreoPlantilla).where(
                CorreoPlantilla.codigo == "PRIMER_INGRESO"
            )
        )
        assert plantilla is not None
        versions = await session.scalar(
            select(func.count())
            .select_from(CorreoPlantillaHistorial)
            .where(
                CorreoPlantillaHistorial.id_plantilla == plantilla.id_plantilla
            )
        )
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "ACTUALIZAR_PLANTILLA_CORREO"
            )
        )
        assert versions == 2
        assert audit is not None
        assert "cuerpo_html" not in (audit.valor_nuevo or {})


async def test_version_optimista_evitar_perdida_de_cambios(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)

    payload = {
        "asunto": "Asunto",
        "cuerpo_html": "<p>{{ recipient_name }} {{ code }}</p>",
        "cuerpo_texto": "{{ recipient_name }} {{ code }}",
        "estado": True,
        "version_esperada": 99,
        "motivo": "Edición obsoleta",
    }
    response = await client.put(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 409


async def test_rechaza_variable_no_autorizada_y_script(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)

    base = {
        "asunto": "Asunto",
        "cuerpo_texto": "Código {{ code }}",
        "estado": True,
        "version_esperada": 1,
        "motivo": "Validación de seguridad",
    }
    response = await client.put(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO",
        headers=headers,
        json={**base, "cuerpo_html": "<p>{{ password_hash }}</p>"},
    )
    assert response.status_code == 400

    response = await client.put(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO",
        headers=headers,
        json={**base, "cuerpo_html": "<script>alert(1)</script>"},
    )
    assert response.status_code == 400


async def test_preview_renderiza_sin_guardar(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)

    response = await client.post(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO/previsualizar",
        headers=headers,
        json={
            "contexto": {
                "recipient_name": "Dylan",
                "code": "123456",
                "expires_minutes": 10,
            }
        },
    )
    assert response.status_code == 200
    assert "123456" in response.json()["cuerpo_html"]
    assert "Dylan" in response.json()["cuerpo_texto"]


async def test_restaura_version_como_nueva_version(client, session_factory) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)

    update = {
        "asunto": "Versión dos",
        "cuerpo_html": "<p>{{ code }}</p>",
        "cuerpo_texto": "{{ code }}",
        "estado": True,
        "version_esperada": 1,
        "motivo": "Crear versión dos",
    }
    await client.put(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO",
        headers=headers,
        json=update,
    )
    restored = await client.post(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO/restaurar/1",
        headers=headers,
        json={"version_esperada": 2, "motivo": "Restaurar diseño inicial"},
    )
    assert restored.status_code == 200
    assert restored.json()["version_actual"] == 3
    assert "configurar tu acceso" in restored.json()["asunto"]


async def test_configuracion_global_consulta_y_actualiza(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)
        role = await create_role(session, "Remitente alternativo")
        sender = await create_user(
            session,
            role,
            username="sender.alterno",
            email="correos@codip.pe",
        )
        await session.commit()
        sender_id = sender.id_usuario

    response = await client.put(
        "/api/v1/comunicaciones/configuracion-global",
        headers=headers,
        json={
            "id_usuario_emisor": sender_id,
            "nombre_remitente": "CODIP Eventos",
            "reply_to": "soporte@codip.pe",
            "estado": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["correo_emisor"] == "correos@codip.pe"
    assert response.json()["nombre_remitente"] == "CODIP Eventos"


async def test_envio_prueba_usa_plantilla_y_registra_metadatos(
    client, session_factory, monkeypatch
) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session)

    monkeypatch.setattr(settings, "email_enabled", True)
    sender = AsyncMock()
    monkeypatch.setattr(SMTPEmailSender, "send_rendered", sender)

    response = await client.post(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO/enviar-prueba",
        headers=headers,
        json={
            "destinatario": "destino@codip.pe",
            "contexto": {
                "recipient_name": "Destino",
                "code": "654321",
                "expires_minutes": 10,
            },
        },
    )
    assert response.status_code == 200
    sent = sender.await_args.args[0]
    assert sent.recipient_email == "destino@codip.pe"
    assert "654321" in sent.html

    async with session_factory() as session:
        envio = await session.scalar(select(CorreoEnvio))
        assert envio is not None
        assert envio.estado == "ENVIADO"
        assert envio.destinatario == "destino@codip.pe"
        assert "654321" not in (envio.error_detalle or "")


async def test_envio_prueba_de_qr_adjunta_la_imagen(
    client, session_factory, monkeypatch
) -> None:
    """La plantilla de QR referencia cid:qr_image; sin adjunto llegaría rota."""
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session, username="actor.qr.prueba")

    monkeypatch.setattr(settings, "email_enabled", True)
    sender = AsyncMock()
    monkeypatch.setattr(SMTPEmailSender, "send_rendered", sender)

    response = await client.post(
        "/api/v1/comunicaciones/plantillas/QR_PARTICIPANTE/enviar-prueba",
        headers=headers,
        json={
            "destinatario": "destino@codip.pe",
            "contexto": {"recipient_name": "Destino"},
        },
    )

    assert response.status_code == 200, response.text
    enviado = sender.await_args.args[0]
    assert enviado.qr_url, "el envío de prueba debe codificar un QR"
    assert "cid:qr_image" in enviado.html
    assert enviado.qr_url not in enviado.html, "el código nunca va en texto"


async def test_envio_prueba_sin_qr_no_adjunta_imagen(
    client, session_factory, monkeypatch
) -> None:
    async with session_factory() as session:
        _, headers = await seed_comunicacion_actor(session, username="actor.sinqr.prueba")

    monkeypatch.setattr(settings, "email_enabled", True)
    sender = AsyncMock()
    monkeypatch.setattr(SMTPEmailSender, "send_rendered", sender)

    response = await client.post(
        "/api/v1/comunicaciones/plantillas/PRIMER_INGRESO/enviar-prueba",
        headers=headers,
        json={
            "destinatario": "destino@codip.pe",
            "contexto": {
                "recipient_name": "Destino",
                "code": "654321",
                "expires_minutes": 10,
            },
        },
    )

    assert response.status_code == 200, response.text
    assert sender.await_args.args[0].qr_url is None


async def test_mensaje_con_qr_embebe_la_imagen_real() -> None:
    """Construye el mensaje de verdad (usa qrcode/Pillow).

    El resto de pruebas mockea el envío SMTP, así que una dependencia de imagen
    ausente no se notaría hasta producción: aquí sí se ejecuta qrcode.make.
    También fija la estructura MIME que los clientes (Gmail incluido) exigen
    para mostrar la imagen embebida y no como adjunto suelto.
    """
    from io import BytesIO

    from PIL import Image

    from app.modules.comunicaciones.email_service import RenderedEmail, build_qr_png

    codigo = "CODIGO-PLANO-DEL-PARTICIPANTE"
    mensaje = SMTPEmailSender._build_rendered_message(
        RenderedEmail(
            sender_email="remitente@codip.pe",
            recipient_email="destino@codip.pe",
            subject="Tu código de ingreso",
            plain_text="texto",
            html='<img src="cid:qr_image">',
            from_name="Sistema Eventos CODIP",
            qr_url=codigo,
        )
    )

    # alternative → [text/plain, related(type=text/html) → [text/html, image/png]]
    assert mensaje.get_content_type() == "multipart/alternative"
    relacionado = mensaje.get_payload()[-1]
    assert relacionado.get_content_type() == "multipart/related"
    assert relacionado.get_param("type") == "text/html"  # RFC 2387
    html, imagen = relacionado.get_payload()
    assert html.get_content_type() == "text/html"
    assert imagen.get_content_type() == "image/png"
    assert imagen.get("Content-ID") == "<qr_image>"
    assert imagen.get_content_disposition() == "inline"
    assert imagen.get_filename() == "codigo-qr-ingreso.png"

    png = imagen.get_payload(decode=True)
    # PNG RGB: el de 1 bit que genera qrcode.make no se renderiza en Gmail.
    assert Image.open(BytesIO(png)).mode == "RGB"
    # La pistola lee el código plano: el QR no debe codificar una URL.
    assert png == build_qr_png(codigo)


async def test_mensaje_del_sender_directo_de_qr_tiene_la_misma_estructura() -> None:
    """El camino sin plantilla de BD debe embeber el QR igual que el renderizado."""
    mensaje = SMTPEmailSender()._build_participante_qr_message(
        ParticipanteQrEmail(
            sender_email="remitente@codip.pe",
            recipient_email="destino@codip.pe",
            recipient_name="Participante",
            codigo_seguro="CODIGO-DIRECTO",
        )
    )
    relacionado = mensaje.get_payload()[-1]
    assert relacionado.get_content_type() == "multipart/related"
    assert relacionado.get_param("type") == "text/html"
    html, imagen = relacionado.get_payload()
    assert "cid:qr_image" in html.get_content()
    assert "CODIGO-DIRECTO" not in html.get_content(), "el código nunca va en texto"
    assert imagen.get("Content-ID") == "<qr_image>"
    assert imagen.get_content_disposition() == "inline"


async def test_seed_amplia_variables_y_refresca_plantilla_no_editada(
    session_factory,
) -> None:
    """Una variable nueva del catálogo debe quedar permitida en filas ya sembradas.

    El renderer valida contra `variables_permitidas` de la BD, así que sin
    ampliarla la plantilla nueva se rechazaría; y el cuerpo debe refrescarse
    solo si nadie la editó desde el panel.
    """
    from app.modules.comunicaciones.seed import seed_default_templates
    from app.modules.comunicaciones.template_catalog import (
        ACCESO_EMPRESA,
        PLANTILLAS_POR_CODIGO,
    )

    base = PLANTILLAS_POR_CODIGO[ACCESO_EMPRESA]

    async with session_factory() as session:
        await seed_default_templates(session)
        plantilla = await session.scalar(
            select(CorreoPlantilla).where(CorreoPlantilla.codigo == ACCESO_EMPRESA)
        )
        assert plantilla is not None
        # Simula el estado anterior: cuerpo viejo y lista blanca reducida.
        plantilla.variables_permitidas = ["recipient_name", "nombre_empresa"]
        plantilla.cuerpo_html = "<p>cuerpo antiguo</p>"
        plantilla.version_actual = 1
        await session.commit()

        await seed_default_templates(session)
        await session.commit()

    async with session_factory() as session:
        plantilla = await session.scalar(
            select(CorreoPlantilla).where(CorreoPlantilla.codigo == ACCESO_EMPRESA)
        )
        assert plantilla is not None
        for variable in ("nombre_evento", "fecha_evento", "expira_en"):
            assert variable in plantilla.variables_permitidas
        assert plantilla.cuerpo_html == base.cuerpo_html


async def test_seed_no_pisa_una_plantilla_editada_en_el_panel(
    session_factory,
) -> None:
    from app.modules.comunicaciones.seed import seed_default_templates
    from app.modules.comunicaciones.template_catalog import ACCESO_EMPRESA

    async with session_factory() as session:
        await seed_default_templates(session)
        plantilla = await session.scalar(
            select(CorreoPlantilla).where(CorreoPlantilla.codigo == ACCESO_EMPRESA)
        )
        assert plantilla is not None
        plantilla.cuerpo_html = "<p>personalizado por el cliente</p>"
        plantilla.version_actual = 2
        await session.commit()

        await seed_default_templates(session)
        await session.commit()

    async with session_factory() as session:
        plantilla = await session.scalar(
            select(CorreoPlantilla).where(CorreoPlantilla.codigo == ACCESO_EMPRESA)
        )
        assert plantilla is not None
        assert plantilla.cuerpo_html == "<p>personalizado por el cliente</p>"
        # Las variables sí se amplían: no rompen nada y habilitan el catálogo.
        assert "nombre_evento" in plantilla.variables_permitidas


async def test_envio_completa_date_y_message_id() -> None:
    """Sin Date/Message-ID los filtros antispam castigan el correo, y en spam
    Gmail no muestra el QR embebido."""
    from email.message import EmailMessage

    mensaje = EmailMessage()
    mensaje["Subject"] = "x"
    SMTPEmailSender._ensure_delivery_headers(mensaje, "eventos@codip.pe")
    assert mensaje["Date"]
    assert mensaje["Message-ID"].endswith("@codip.pe>")

    fijo = EmailMessage()
    fijo["Message-ID"] = "<propio@codip.pe>"
    SMTPEmailSender._ensure_delivery_headers(fijo, "eventos@codip.pe")
    assert fijo["Message-ID"] == "<propio@codip.pe>"
