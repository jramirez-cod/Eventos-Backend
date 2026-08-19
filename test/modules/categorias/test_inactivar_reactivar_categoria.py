import pytest

from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorCategorias")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="CATEGORIAS"
        )
    actor = await create_user(session, rol, username="actor.cat.estado")
    await session.commit()
    return actor


async def test_ciclo_inactivar_reactivar(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(
            session, permisos=["CREAR_CATEGORIA", "INACTIVAR_CATEGORIA"]
        )
        categoria = Categoria(nombre_categoria="D", estado=True)
        session.add(categoria)
        await session.commit()
        id_categoria = categoria.id_categoria
        headers = auth_header(actor)

    inactivar = await client.patch(
        f"/api/v1/categorias/{id_categoria}/inactivar",
        headers=headers,
        json={"motivo": "ya no se usa"},
    )
    assert inactivar.status_code == 200
    assert inactivar.json()["estado"] is False

    reactivar = await client.patch(
        f"/api/v1/categorias/{id_categoria}/reactivar", headers=headers
    )
    assert reactivar.status_code == 200
    assert reactivar.json()["estado"] is True


async def test_categoria_inexistente_recibe_404(client, session_factory) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["INACTIVAR_CATEGORIA"])
        headers = auth_header(actor)

    response = await client.patch(
        "/api/v1/categorias/999999/inactivar",
        headers=headers,
        json={"motivo": None},
    )
    assert response.status_code == 404


async def test_categoria_en_uso_por_empresa_activa_no_se_puede_inactivar(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["INACTIVAR_CATEGORIA"])
        categoria = Categoria(nombre_categoria="E", estado=True)
        grupo = Grupo(id_grupo=900, nombre_grupo="GrupoEnUso", estado=True)
        session.add_all([categoria, grupo])
        await session.commit()
        detalle = DetalleCategoria(
            id_grupo=grupo.id_grupo, id_categoria=categoria.id_categoria, estado=True
        )
        session.add(detalle)
        await session.commit()
        empresa = Empresa(
            nombre_empresa="EmpresaEnUso",
            ruc="20333333333",
            id_detalle_categoria=detalle.id_detalle_categoria,
            estado=True,
        )
        session.add(empresa)
        await session.commit()
        id_categoria = categoria.id_categoria
        headers = auth_header(actor)

    response = await client.patch(
        f"/api/v1/categorias/{id_categoria}/inactivar",
        headers=headers,
        json={"motivo": None},
    )
    assert response.status_code == 409
    assert "EmpresaEnUso" in response.json()["detail"]

    async with session_factory() as session:
        from sqlalchemy import select

        aun_activa = await session.scalar(
            select(Categoria).where(Categoria.id_categoria == id_categoria)
        )
        assert aun_activa.estado is True


async def test_categoria_sin_empresas_activas_se_puede_inactivar(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["INACTIVAR_CATEGORIA"])
        categoria = Categoria(nombre_categoria="F", estado=True)
        grupo = Grupo(id_grupo=901, nombre_grupo="GrupoDesvinculado", estado=True)
        session.add_all([categoria, grupo])
        await session.commit()
        detalle = DetalleCategoria(
            id_grupo=grupo.id_grupo,
            id_categoria=categoria.id_categoria,
            estado=True,
        )
        session.add(detalle)
        await session.commit()
        empresa_inactiva = Empresa(
            nombre_empresa="EmpresaInactiva",
            ruc="20444444444",
            id_detalle_categoria=detalle.id_detalle_categoria,
            estado=False,
        )
        session.add(empresa_inactiva)
        await session.commit()
        id_categoria = categoria.id_categoria
        headers = auth_header(actor)

    response = await client.patch(
        f"/api/v1/categorias/{id_categoria}/inactivar",
        headers=headers,
        json={"motivo": None},
    )
    assert response.status_code == 200
    assert response.json()["estado"] is False
