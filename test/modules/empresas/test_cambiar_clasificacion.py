import pytest
from sqlalchemy import select

from app.modules.empresas.models import Empresa, EmpresaHistorialClasificacion
from test.modules.empresas.conftest import create_grupo_categoria_detalle
from test.modules.usuarios.conftest import auth_header, create_role, create_user, grant_permission


pytestmark = pytest.mark.asyncio


async def _actor_con_permisos(session, *, permisos):
    rol = await create_role(session, "ActorClasificacion")
    for permiso in permisos:
        await grant_permission(
            session, rol, permiso_nombre=permiso, modulo_nombre="EMPRESAS"
        )
    actor = await create_user(session, rol, username="actor.clasificacion")
    await session.commit()
    return actor


async def test_cambiar_clasificacion_actualiza_historial(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        _, _, detalle_a = await create_grupo_categoria_detalle(
            session, id_grupo=710, nombre_grupo="GrupoA"
        )
        _, _, detalle_b = await create_grupo_categoria_detalle(
            session, id_grupo=711, nombre_grupo="GrupoB"
        )
        await session.commit()
        headers = auth_header(actor)
        id_detalle_a = detalle_a.id_detalle_categoria
        id_detalle_b = detalle_b.id_detalle_categoria

    crear = await client.post(
        "/api/v1/empresas",
        headers=headers,
        json={
            "nombre_empresa": "Empresa Reclasificable",
            "ruc": "20123456789",
            "id_detalle_categoria": id_detalle_a,
        },
    )
    assert crear.status_code == 201
    id_empresa = crear.json()["id_empresa"]

    cambiar = await client.patch(
        f"/api/v1/empresas/{id_empresa}/clasificacion",
        headers=headers,
        json={"id_detalle_categoria": id_detalle_b, "motivo": "cambio de grupo"},
    )
    assert cambiar.status_code == 200
    assert cambiar.json()["nombre_grupo"] == "GrupoB"

    async with session_factory() as session:
        empresa = await session.get(Empresa, id_empresa)
        assert empresa.id_detalle_categoria == id_detalle_b

        historial = (
            await session.execute(
                select(EmpresaHistorialClasificacion)
                .where(EmpresaHistorialClasificacion.id_empresa == id_empresa)
                .order_by(EmpresaHistorialClasificacion.id_historial)
            )
        ).scalars().all()

        assert len(historial) == 2
        assert historial[0].id_detalle_categoria == id_detalle_a
        assert historial[0].fecha_fin is not None
        assert historial[1].id_detalle_categoria == id_detalle_b
        assert historial[1].fecha_fin is None


async def test_cambiar_clasificacion_empresa_inexistente_recibe_404(
    client, session_factory
) -> None:
    async with session_factory() as session:
        actor = await _actor_con_permisos(session, permisos=["CREAR_EMPRESA"])
        _, _, detalle = await create_grupo_categoria_detalle(session, id_grupo=712)
        await session.commit()
        headers = auth_header(actor)
        id_detalle_categoria = detalle.id_detalle_categoria

    response = await client.patch(
        "/api/v1/empresas/999999/clasificacion",
        headers=headers,
        json={"id_detalle_categoria": id_detalle_categoria},
    )
    assert response.status_code == 404
