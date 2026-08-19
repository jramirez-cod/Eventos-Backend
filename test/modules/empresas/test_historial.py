import pytest

from test.modules.empresas.conftest import create_grupo_categoria_detalle
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorHistorial")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="EMPRESAS"
        )
    actor = await create_user(session, rol, username="actor.historial")
    await session.commit()
    return actor


async def test_historial_incluye_clasificacion_inicial(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        _, _, detalle = await create_grupo_categoria_detalle(session, id_grupo=730)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    crear = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Empresa Historial",
            "ruc": "20222222222",
            "id_detalle_categoria": id_detalle_categoria,
        },
    )
    id_empresa = crear.json()["id_empresa"]

    historial = await client.get(
        f"/api/v1/empresas/{id_empresa}/historial", headers=headers
    )
    assert historial.status_code == 200
    filas = historial.json()
    assert len(filas) == 1
    assert filas[0]["id_detalle_categoria"] == id_detalle_categoria
    assert filas[0]["fecha_fin"] is None


async def test_historial_empresa_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        headers = auth_header(actor)

    response = await client.get(
        "/api/v1/empresas/999999/historial", headers=headers
    )
    assert response.status_code == 404
