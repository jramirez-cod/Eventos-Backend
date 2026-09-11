from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.modules.auditoria.models import Auditoria
from app.modules.comunicaciones.email_service import SMTPEmailSender
from app.modules.comunicaciones.models import (
    CorreoEnvio,
    CorreoPlantilla,
    CorreoPlantillaHistorial,
)
from test.modules.comunicaciones import seed_comunicacion_actor
from test.modules.usuarios.conftest import auth_header, create_role, create_user


pytestmark = pytest.mark.asyncio


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
