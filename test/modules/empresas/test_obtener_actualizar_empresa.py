import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.empresas.models import Empresa, EmpresaHistorialClasificacion
from test.modules.empresas.conftest import create_grupo_categoria_detalle
from test.modules.usuarios.conftest import (
    auth_header,
    create_role,
    create_user,
    grant_permission,
)


pytestmark = pytest.mark.asyncio


async def _actor(session, *, con_permiso: bool = True):
    rol = await create_role(session, "ActorDetalleEmpresa")
    if con_permiso:
        await grant_permission(
            session,
            rol,
            permiso_nombre="CREAR_EMPRESA",
            modulo_nombre="EMPRESAS",
        )
    actor = await create_user(session, rol, username="actor.detalle.empresa")
    await session.commit()
    return actor


async def _empresa(session, *, id_grupo: int = 830) -> Empresa:
    _, _, detalle = await create_grupo_categoria_detalle(
        session,
        id_grupo=id_grupo,
        nombre_grupo=f"Grupo {id_grupo}",
    )
    empresa = Empresa(
        id_detalle_categoria=detalle.id_detalle_categoria,
        nombre_empresa="Empresa inicial",
        razon_social="EMPRESA INICIAL S.A.C.",
        nombre_comercial="Inicial",
        ruc=f"20{id_grupo:09d}",
        estado=False,
    )
    session.add(empresa)
    await session.flush()
    session.add(
        EmpresaHistorialClasificacion(
            id_empresa=empresa.id_empresa,
            id_detalle_categoria=detalle.id_detalle_categoria,
        )
    )
    await session.flush()
    return empresa


async def test_obtener_y_actualizar_empresa_preserva_campos_protegidos(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        empresa = await _empresa(session)
        await session.commit()
        id_empresa = empresa.id_empresa
        ruc = empresa.ruc
        id_detalle = empresa.id_detalle_categoria
        headers = auth_header(actor)

    detalle = await client.get(f"/api/v1/empresas/{id_empresa}", headers=headers)
    assert detalle.status_code == 200
    assert detalle.json()["ruc"] == ruc
    assert detalle.json()["nombre_grupo"] == "Grupo 830"

    response = await client.put(
        f"/api/v1/empresas/{id_empresa}",
        headers=headers,
        json={
            "nombre_empresa": "  Empresa   corregida  ",
            "razon_social": "  EMPRESA CORREGIDA S.A.C.  ",
            "nombre_comercial": "  Corregida  ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id_empresa"] == id_empresa
    assert body["nombre_empresa"] == "Empresa corregida"
    assert body["razon_social"] == "EMPRESA CORREGIDA S.A.C."
    assert body["nombre_comercial"] == "Corregida"
    assert body["ruc"] == ruc
    assert body["estado"] is False

    async with session_factory() as session:
        actualizada = await session.get(Empresa, id_empresa)
        assert actualizada is not None
        assert actualizada.id_detalle_categoria == id_detalle
        historial_total = await session.scalar(
            select(func.count())
            .select_from(EmpresaHistorialClasificacion)
            .where(EmpresaHistorialClasificacion.id_empresa == id_empresa)
        )
        assert historial_total == 1

        auditoria = await session.scalar(
            select(Auditoria).where(Auditoria.accion == "ACTUALIZAR_EMPRESA")
        )
        assert auditoria is not None
        assert auditoria.id_usuario == actor.id_usuario
        assert auditoria.valor_anterior["ruc"] == ruc
        assert auditoria.valor_nuevo["nombre_empresa"] == "Empresa corregida"


@pytest.mark.parametrize("method", ["get", "put"])
async def test_empresa_inexistente_recibe_404(
    client, session_factory, method: str
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        headers = auth_header(actor)

    if method == "get":
        response = await client.get("/api/v1/empresas/999999", headers=headers)
    else:
        response = await client.put(
            "/api/v1/empresas/999999",
            headers=headers,
            json={
                "nombre_empresa": "Inexistente",
                "razon_social": None,
                "nombre_comercial": None,
            },
        )
    assert response.status_code == 404


async def test_actualizar_empresa_rechaza_campos_protegidos(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session)
        empresa = await _empresa(session, id_grupo=831)
        await session.commit()
        id_empresa = empresa.id_empresa
        headers = auth_header(actor)

    response = await client.put(
        f"/api/v1/empresas/{id_empresa}",
        headers=headers,
        json={
            "nombre_empresa": "Intento",
            "razon_social": None,
            "nombre_comercial": None,
            "ruc": "20999999999",
            "id_detalle_categoria": 999,
            "estado": True,
        },
    )
    assert response.status_code == 422


async def test_detalle_empresa_requiere_autenticacion(client) -> None:
    response = await client.get("/api/v1/empresas/1")
    assert response.status_code == 401


async def test_actualizar_empresa_sin_permiso_recibe_403(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor(session, con_permiso=False)
        empresa = await _empresa(session, id_grupo=832)
        await session.commit()
        id_empresa = empresa.id_empresa
        headers = auth_header(actor)

    response = await client.put(
        f"/api/v1/empresas/{id_empresa}",
        headers=headers,
        json={
            "nombre_empresa": "No autorizada",
            "razon_social": None,
            "nombre_comercial": None,
        },
    )
    assert response.status_code == 403
