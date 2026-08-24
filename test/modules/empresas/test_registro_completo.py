import pytest
from sqlalchemy import func, select

from app.modules.contactos.models import Contacto
from app.modules.empresas.models import Empresa
from test.modules.empresas.conftest import create_grupo_categoria_detalle
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


pytestmark = pytest.mark.asyncio


async def _actor_registro_completo(session):
    rol = await create_role(session, "Actor Registro Empresa Completa")
    await grant_permission(
        session,
        rol,
        permiso_nombre="CREAR_EMPRESA",
        modulo_nombre="EMPRESAS",
    )
    await grant_permission(
        session,
        rol,
        permiso_nombre="CREAR_CONTACTO",
        modulo_nombre="CONTACTOS",
    )
    actor = await create_user(session, rol, username="actor.registro.completo")
    return actor


def _payload(id_detalle_categoria: int, *, contactos: list[dict[str, object]]):
    return {
        "empresa": {
            "nombre_empresa": "Empresa con contactos",
            "ruc": "20552103816",
            "id_detalle_categoria": id_detalle_categoria,
            "razon_social": "EMPRESA CON CONTACTOS S.A.C.",
            "nombre_comercial": "Empresa Contactos",
        },
        "contactos": contactos,
    }


def _contacto(
    numero_documento: str,
    *,
    nombres: str,
    id_tipo_documento: int,
) -> dict[str, object]:
    return {
        "id_cargo": None,
        "id_tipo_documento": id_tipo_documento,
        "numero_documento": numero_documento,
        "nombres": nombres,
        "apellidos": "Prueba",
        "genero": "M",
        "celular": "987654321",
        "correo": f"{nombres.lower()}@example.com",
        "es_contacto_principal": False,
    }


async def test_registro_completo_admite_cero_contactos(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_registro_completo(session)
        _, _, detalle = await create_grupo_categoria_detalle(session, id_grupo=710)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    response = await client.post(
        "/api/v1/empresas/registro-completo",
        headers=headers,
        json=_payload(id_detalle_categoria, contactos=[]),
    )

    assert response.status_code == 201
    assert response.json()["empresa"]["ruc"] == "20552103816"
    assert response.json()["contactos"] == []


async def test_registro_completo_asigna_todos_los_contactos(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_registro_completo(session)
        _, _, detalle = await create_grupo_categoria_detalle(session, id_grupo=711)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria
        id_tipo_documento = actor.id_tipo_documento

    response = await client.post(
        "/api/v1/empresas/registro-completo",
        headers=headers,
        json=_payload(
            id_detalle_categoria,
            contactos=[
                _contacto(
                    "76543210",
                    nombres="Ana",
                    id_tipo_documento=id_tipo_documento,
                ),
                _contacto(
                    "76543211",
                    nombres="Luis",
                    id_tipo_documento=id_tipo_documento,
                ),
            ],
        ),
    )

    assert response.status_code == 201
    body = response.json()
    id_empresa = body["empresa"]["id_empresa"]
    assert len(body["contactos"]) == 2
    assert {item["id_empresa"] for item in body["contactos"]} == {id_empresa}


async def test_registro_completo_revierte_empresa_y_contactos_si_uno_falla(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_registro_completo(session)
        _, _, detalle = await create_grupo_categoria_detalle(session, id_grupo=712)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria
        id_tipo_documento = actor.id_tipo_documento

    response = await client.post(
        "/api/v1/empresas/registro-completo",
        headers=headers,
        json=_payload(
            id_detalle_categoria,
            contactos=[
                _contacto(
                    "76543220",
                    nombres="Primer",
                    id_tipo_documento=id_tipo_documento,
                ),
                _contacto(
                    "76543220",
                    nombres="Duplicado",
                    id_tipo_documento=id_tipo_documento,
                ),
            ],
        ),
    )

    assert response.status_code == 409

    async with session_factory() as session:
        empresa = await session.scalar(
            select(Empresa).where(Empresa.ruc == "20552103816")
        )
        contactos = await session.scalar(select(func.count()).select_from(Contacto))

    assert empresa is None
    assert contactos == 0
