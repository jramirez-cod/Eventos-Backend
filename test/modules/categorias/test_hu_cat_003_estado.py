import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.models import Empresa
from test.modules.catalogos_helpers import (
    create_category_detail,
    create_company,
    create_group,
    seed_catalog_actor,
)


pytestmark = pytest.mark.asyncio


async def test_inactivar_categoria_sin_empresas_conserva_detalle_y_audita(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Asociado")
        categoria, detail = await create_category_detail(session, grupo)
        await session.commit()
        category_id = categoria.id_categoria
        detail_id = detail.id_detalle_categoria
        actor_id = actor.id_usuario

    response = await client.patch(
        f"/api/v1/categorias/{category_id}/inactivar",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["estado"] is False
    async with session_factory() as session:
        assert await session.get(DetalleCategoria, detail_id) is not None
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "INACTIVAR_CATEGORIA"
            )
        )
        assert audit is not None
        assert audit.id_usuario == actor_id
        assert audit.valor_anterior == {"estado": True}
        assert audit.valor_nuevo == {"estado": False}


async def test_inactivar_categoria_inexistente_devuelve_404(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)

    response = await client.patch(
        "/api/v1/categorias/9999/inactivar",
        headers=headers,
    )
    assert response.status_code == 404


async def test_empresa_activa_bloquea_categoria_e_informa_afectada(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Asociado")
        categoria, detail = await create_category_detail(session, grupo)
        empresa = await create_company(
            session,
            grupo,
            sequence=3,
            detail=detail,
            estado=True,
        )
        await session.commit()
        category_id = categoria.id_categoria
        company_id = empresa.id_empresa

    response = await client.patch(
        f"/api/v1/categorias/{category_id}/inactivar",
        headers=headers,
    )

    assert response.status_code == 409
    assert response.json()["detail"]["empresas_dependientes"] == [
        {
            "id_empresa": company_id,
            "nombre_empresa": "Empresa 3",
            "ruc": "20000000003",
        }
    ]
    async with session_factory() as session:
        assert (await session.get(Categoria, category_id)).estado is True


async def test_empresa_inactiva_permite_inactivar_y_conserva_historial(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Histórico")
        categoria, detail = await create_category_detail(session, grupo)
        empresa = await create_company(
            session,
            grupo,
            sequence=4,
            detail=detail,
            estado=False,
        )
        await session.commit()
        category_id = categoria.id_categoria
        detail_id = detail.id_detalle_categoria
        company_id = empresa.id_empresa

    response = await client.patch(
        f"/api/v1/categorias/{category_id}/inactivar",
        headers=headers,
    )

    assert response.status_code == 200
    async with session_factory() as session:
        assert await session.get(DetalleCategoria, detail_id) is not None
        assert await session.get(Empresa, company_id) is not None


async def test_reactivar_categoria_conserva_id_y_audita(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Expositor")
        categoria, _ = await create_category_detail(
            session,
            grupo,
            category_estado=False,
        )
        await session.commit()
        category_id = categoria.id_categoria

    response = await client.patch(
        f"/api/v1/categorias/{category_id}/reactivar",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id_categoria"] == category_id
    assert response.json()["estado"] is True
    async with session_factory() as session:
        category_count = await session.scalar(
            select(func.count()).select_from(Categoria).where(
                Categoria.id_categoria == category_id
            )
        )
        assert category_count == 1
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "REACTIVAR_CATEGORIA"
            )
        )
        assert audit is not None
