from unittest.mock import AsyncMock

import pytest

from app.core.config import settings
from app.modules.comunicaciones.email_service import (
    EmailDeliveryError,
    SMTPEmailSender,
)
from app.modules.comunicaciones.models import CorreoConfiguracionGlobal
from app.modules.comunicaciones.seed import seed_default_templates
from test.modules.participantes.conftest import evento_contacto_context


pytestmark = pytest.mark.asyncio


async def _participante_con_qr(session_factory, client) -> tuple[dict[str, str], int]:
    async with session_factory() as session:
        actor, headers, programacion, _, contacto, _ = await evento_contacto_context(
            session, client
        )
        id_usuario = actor.id_usuario

    agregar = await client.post(
        f"/api/v1/participantes/programaciones/"
        f"{programacion.id_programacion_evento}/evento-contactos",
        headers=headers,
        json={"ids_contacto": [contacto.id_contacto]},
    )
    assert agregar.status_code == 201, agregar.text
    id_evento_contacto = agregar.json()["evento_contactos"][0]["id_evento_contacto"]
    return headers, id_evento_contacto, id_usuario


async def _configurar_correo(session_factory, id_usuario: int) -> None:
    async with session_factory() as session:
        await seed_default_templates(session)
        session.add(
            CorreoConfiguracionGlobal(
                codigo="GLOBAL",
                id_usuario_emisor=id_usuario,
                nombre_remitente="Sistema Eventos CODIP",
                estado=True,
                actualizado_por=id_usuario,
            )
        )
        await session.commit()


async def test_plantilla_de_qr_sin_configurar_responde_503(
    client, session_factory, monkeypatch
) -> None:
    headers, id_evento_contacto, _ = await _participante_con_qr(
        session_factory, client
    )
    # Sin plantillas sembradas: el envío no puede completarse por configuración
    # pendiente, no por un error del cliente ni por una caída del SMTP.
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_print_code_to_console", False)

    response = await client.post(
        f"/api/v1/participantes/evento-contactos/{id_evento_contacto}/qr/enviar",
        headers=headers,
    )

    assert response.status_code == 503, response.text
    assert "QR_PARTICIPANTE" in response.json()["detail"]


async def test_fallo_de_smtp_al_enviar_qr_responde_502(
    client, session_factory, monkeypatch
) -> None:
    headers, id_evento_contacto, id_usuario = await _participante_con_qr(
        session_factory, client
    )
    await _configurar_correo(session_factory, id_usuario)

    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_print_code_to_console", False)
    monkeypatch.setattr(
        SMTPEmailSender,
        "send_rendered",
        AsyncMock(side_effect=EmailDeliveryError("No se pudo conectar al SMTP.")),
    )

    response = await client.post(
        f"/api/v1/participantes/evento-contactos/{id_evento_contacto}/qr/enviar",
        headers=headers,
    )

    assert response.status_code == 502, response.text
    assert "SMTP" in response.json()["detail"]
