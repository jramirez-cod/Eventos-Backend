import pytest
from sqlalchemy import func, select

from app.modules.auditoria.models import Auditoria
from app.modules.empresas.models import Empresa
from app.modules.grupos.models import Grupo
from test.modules.catalogos_helpers import (
    create_company,
    create_group,
    seed_catalog_actor,
)


pytestmark = pytest.mark.asyncio


async def test_inactivar_grupo_sin_empresas_conserva_registro_y_audita(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        actor, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Asociado")
        await session.commit()
        group_id = grupo.id_grupo
        actor_id = actor.id_usuario

    response = await client.patch(
        f"/api/v1/grupos/{group_id}/inactivar",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["estado"] is False
    async with session_factory() as session:
        stored = await session.get(Grupo, group_id)
        assert stored is not None
        assert stored.estado is False
        count = await session.scalar(
            select(func.count()).select_from(Grupo).where(
                Grupo.id_grupo == group_id
            )
        )
        assert count == 1
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "INACTIVAR_GRUPO"
            )
        )
        assert audit is not None
        assert audit.id_usuario == actor_id
        assert audit.valor_anterior == {"estado": True}
        assert audit.valor_nuevo == {"estado": False}


async def test_inactivar_grupo_inexistente_devuelve_404(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)

    response = await client.patch(
        "/api/v1/grupos/9999/inactivar",
        headers=headers,
    )
    assert response.status_code == 404


async def test_empresa_activa_bloquea_inactivacion_e_informa_dependencia(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Asociado")
        empresa = await create_company(session, grupo, sequence=1, estado=True)
        await session.commit()
        group_id = grupo.id_grupo
        company_id = empresa.id_empresa

    response = await client.patch(
        f"/api/v1/grupos/{group_id}/inactivar",
        headers=headers,
    )

    assert response.status_code == 409
    dependencies = response.json()["detail"]["empresas_dependientes"]
    assert dependencies == [
        {
            "id_empresa": company_id,
            "nombre_empresa": "Empresa 1",
            "ruc": "20000000001",
        }
    ]
    async with session_factory() as session:
        assert (await session.get(Grupo, group_id)).estado is True


async def test_solo_empresas_inactivas_permiten_inactivar_grupo(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(session, name="Histórico")
        await create_company(session, grupo, sequence=2, estado=False)
        await session.commit()
        group_id = grupo.id_grupo

    response = await client.patch(
        f"/api/v1/grupos/{group_id}/inactivar",
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["estado"] is False

    async with session_factory() as session:
        companies = (await session.scalars(select(Empresa))).all()
        assert len(companies) == 1


async def test_reactivar_grupo_conserva_id_y_audita(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(
            session,
            name="Expositor",
            estado=False,
        )
        await session.commit()
        group_id = grupo.id_grupo

    response = await client.patch(
        f"/api/v1/grupos/{group_id}/reactivar",
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["id_grupo"] == group_id
    assert response.json()["estado"] is True
    async with session_factory() as session:
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "REACTIVAR_GRUPO"
            )
        )
        assert audit is not None


async def test_configuracion_categoria_cambia_y_conserva_historial(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)
        grupo = await create_group(
            session,
            name="Expositor",
            requiere_categoria=True,
        )
        await session.commit()
        group_id = grupo.id_grupo

    response = await client.patch(
        f"/api/v1/grupos/{group_id}/configuracion-categoria",
        headers=headers,
        json={"requiere_categoria": False},
    )

    assert response.status_code == 200
    assert response.json()["requiere_categoria"] is False
    async with session_factory() as session:
        stored = await session.get(Grupo, group_id)
        assert stored.requiere_categoria is False
        audit = await session.scalar(
            select(Auditoria).where(
                Auditoria.accion == "CAMBIAR_REQUIERE_CATEGORIA"
            )
        )
        assert audit is not None
        assert audit.valor_anterior == {"requiere_categoria": True}
        assert audit.valor_nuevo == {"requiere_categoria": False}
