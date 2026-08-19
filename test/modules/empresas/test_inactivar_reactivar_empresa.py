import pytest

from test.modules.empresas.conftest import create_grupo_categoria_detalle
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorEmpresaEstado")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="EMPRESAS"
        )
    actor = await create_user(session, rol, username="actor.empresa.estado")
    await session.commit()
    return actor


async def test_ciclo_inactivar_reactivar(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(
            session, permisos=["CREAR_EMPRESA", "INACTIVAR_EMPRESA"]
        )
        _, _, detalle = await create_grupo_categoria_detalle(session, id_grupo=720)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    crear = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Empresa Ciclo",
            "ruc": "20111111111",
            "id_detalle_categoria": id_detalle_categoria,
        },
    )
    id_empresa = crear.json()["id_empresa"]

    inactivar = await client.patch(
        f"/api/v1/empresas/{id_empresa}/inactivar",
        headers=headers,
        json={"motivo": "cierre temporal"},
    )
    assert inactivar.status_code == 200
    assert inactivar.json()["estado"] is False

    reactivar = await client.patch(
        f"/api/v1/empresas/{id_empresa}/reactivar", headers=headers
    )
    assert reactivar.status_code == 200
    assert reactivar.json()["estado"] is True


async def test_empresa_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["INACTIVAR_EMPRESA"])
        headers = auth_header(actor)

    response = await client.patch(
        "/api/v1/empresas/999999/inactivar",
        headers=headers,
        json={"motivo": None},
    )
    assert response.status_code == 404
