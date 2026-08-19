import pytest

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorGruposEstado")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="GRUPOS"
        )
    actor = await create_user(session, rol, username="actor.grupo.estado")
    await session.commit()
    return actor


async def test_ciclo_inactivar_reactivar(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(
            session, permisos=["CREAR_GRUPO", "INACTIVAR_GRUPO"]
        )
        grupo = Grupo(id_grupo=500, nombre_grupo="Temporal", estado=True)
        session.add(grupo)
        await session.commit()
        headers = auth_header(actor)

    inactivar = await client.patch(
        "/api/v1/grupos/500/inactivar",
        headers=headers,
        json={"motivo": "cierre de temporada"},
    )
    assert inactivar.status_code == 200
    assert inactivar.json()["estado"] is False

    reactivar = await client.patch("/api/v1/grupos/500/reactivar", headers=headers)
    assert reactivar.status_code == 200
    assert reactivar.json()["estado"] is True


async def test_grupo_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["INACTIVAR_GRUPO"])
        headers = auth_header(actor)

    response = await client.patch(
        "/api/v1/grupos/999999/inactivar",
        headers=headers,
        json={"motivo": None},
    )
    assert response.status_code == 404


async def test_grupo_con_empresa_activa_no_se_puede_inactivar(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(
            session, permisos=["CREAR_GRUPO", "INACTIVAR_GRUPO"]
        )
        grupo = Grupo(id_grupo=501, nombre_grupo="GrupoConEmpresa", estado=True)
        categoria = Categoria(nombre_categoria="CatGrupoEmpresa", estado=True)
        session.add_all([grupo, categoria])
        await session.commit()
        detalle = DetalleCategoria(
            id_grupo=grupo.id_grupo, id_categoria=categoria.id_categoria, estado=True
        )
        session.add(detalle)
        await session.commit()
        empresa = Empresa(
            nombre_empresa="EmpresaDelGrupo",
            ruc="20555555555",
            id_detalle_categoria=detalle.id_detalle_categoria,
            estado=True,
        )
        session.add(empresa)
        await session.commit()
        headers = auth_header(actor)

    response = await client.patch(
        "/api/v1/grupos/501/inactivar",
        headers=headers,
        json={"motivo": None},
    )
    assert response.status_code == 409
    assert "EmpresaDelGrupo" in response.json()["detail"]
