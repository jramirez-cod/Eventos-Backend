from datetime import date, timedelta

import pytest

from app.modules.maestros.models import TipoCalculoBeneficio
from test.modules.participantes.conftest import (
    crear_contexto_beneficio,
    crear_programacion_con_dia,
    evento_contacto_context,
)


pytestmark = pytest.mark.asyncio


def _invitado_url(*, id_programacion_evento: int, id_empresa: int) -> str:
    return (
        f"/api/v1/participantes/programaciones/{id_programacion_evento}"
        f"/empresas/{id_empresa}/invitados"
    )


async def test_invitado_valida_documento_correo_y_celular(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, empresa, _, _ = await evento_contacto_context(
            session, client
        )

    url = _invitado_url(
        id_programacion_evento=programacion.id_programacion_evento,
        id_empresa=empresa.id_empresa,
    )
    casos_invalidos = (
        {
            "nombres": "Invitado",
            "apellidos": "Documento inválido",
            "numero_documento": "12-34",
            "correo": "documento@example.com",
        },
        {
            "nombres": "Invitado",
            "apellidos": "Correo inválido",
            "numero_documento": "INV00001",
            "correo": "correo-invalido",
        },
        {
            "nombres": "Invitado",
            "apellidos": "Celular inválido",
            "numero_documento": "INV00002",
            "correo": "celular@example.com",
            "celular": "12345678",
        },
    )

    for payload in casos_invalidos:
        response = await client.post(url, headers=headers, json=payload)
        assert response.status_code == 422, response.text

    valido = await client.post(
        url,
        headers=headers,
        json={
            "nombres": "  Invitado  ",
            "apellidos": "  Normalizado  ",
            "numero_documento": "  INV00003  ",
            "correo": "normalizado@example.com",
            "celular": "987 654 321",
        },
    )
    assert valido.status_code == 201, valido.text
    assert valido.json()["numero_documento"] == "INV00003"
    assert valido.json()["celular"] == "987654321"


async def test_duplicado_en_programacion_es_especifico_y_contacto_es_generico(
    client, session_factory
) -> None:
    async with session_factory() as session:
        _, headers, programacion, empresa, contacto, _ = (
            await evento_contacto_context(session, client)
        )

    url = _invitado_url(
        id_programacion_evento=programacion.id_programacion_evento,
        id_empresa=empresa.id_empresa,
    )
    payload = {
        "nombres": "Invitado",
        "apellidos": "Duplicado",
        "numero_documento": "INV10001",
        "correo": "duplicado@example.com",
    }
    creado = await client.post(url, headers=headers, json=payload)
    assert creado.status_code == 201, creado.text

    duplicado = await client.post(url, headers=headers, json=payload)
    assert duplicado.status_code == 409, duplicado.text
    assert "esta programación" in duplicado.json()["detail"]

    conflicto_contacto = await client.post(
        url,
        headers=headers,
        json={
            "nombres": "Tercero",
            "apellidos": "Existente",
            "numero_documento": contacto.numero_documento,
            "correo": "correo-distinto@example.com",
        },
    )
    assert conflicto_contacto.status_code == 409, conflicto_contacto.text
    assert conflicto_contacto.json()["detail"] == (
        "No se pudo registrar al invitado con los datos indicados. "
        "Comuníquese con CODIP para verificar y agregar al contacto."
    )


async def test_invitado_puede_recibir_beneficio_al_crearse(
    client, session_factory
) -> None:
    async with session_factory() as session:
        contexto = await crear_contexto_beneficio(
            session,
            tipo_calculo=TipoCalculoBeneficio.POR_EVENTO,
            entradas_gratuitas=1,
        )
        programacion = await crear_programacion_con_dia(
            session,
            evento=contexto["evento"],
            empresa=contexto["empresa"],
            fecha=date.today() + timedelta(days=5),
        )

    response = await client.post(
        _invitado_url(
            id_programacion_evento=programacion.id_programacion_evento,
            id_empresa=contexto["empresa"].id_empresa,
        ),
        headers=contexto["headers"],
        json={
            "nombres": "Invitado",
            "apellidos": "Con beneficio",
            "numero_documento": "INV20001",
            "correo": "beneficio@example.com",
            "celular": "+51987654321",
            "id_beneficio": contexto["beneficio"].id_beneficio,
        },
    )

    assert response.status_code == 201, response.text
    assert response.json()["id_beneficio_asignado"] == (
        contexto["beneficio"].id_beneficio
    )
    assert response.json()["celular"] == "+51987654321"
