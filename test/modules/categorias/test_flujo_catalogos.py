import pytest

from test.modules.catalogos_helpers import seed_catalog_actor


pytestmark = pytest.mark.asyncio


async def test_flujo_completo_grupos_y_categoria_compartida(
    client,
    session_factory,
) -> None:
    async with session_factory() as session:
        _, headers = await seed_catalog_actor(session)

    asociado = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={
            "nombre_grupo": "Asociado",
            "descripcion": "Empresas asociadas",
            "requiere_categoria": True,
        },
    )
    expositor = await client.post(
        "/api/v1/grupos",
        headers=headers,
        json={
            "nombre_grupo": "Expositor",
            "descripcion": "Empresas expositoras",
            "requiere_categoria": False,
        },
    )
    assert asociado.status_code == 201
    assert expositor.status_code == 201

    asociado_id = asociado.json()["id_grupo"]
    expositor_id = expositor.json()["id_grupo"]
    categoria_asociado = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json={
            "id_grupo": asociado_id,
            "nombre_categoria": "A",
            "descripcion": "Categoría A",
        },
    )
    categoria_expositor = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json={
            "id_grupo": expositor_id,
            "nombre_categoria": "A",
            "descripcion": "Categoría A",
        },
    )
    duplicate = await client.post(
        "/api/v1/categorias",
        headers=headers,
        json={
            "id_grupo": asociado_id,
            "nombre_categoria": "A",
            "descripcion": "Categoría A",
        },
    )

    assert categoria_asociado.status_code == 201
    assert categoria_expositor.status_code == 201
    assert duplicate.status_code == 409
    assert categoria_asociado.json()["id_categoria"] == (
        categoria_expositor.json()["id_categoria"]
    )

    category_id = categoria_asociado.json()["id_categoria"]
    inactivate_category = await client.patch(
        f"/api/v1/categorias/{category_id}/inactivar",
        headers=headers,
    )
    reactivate_category = await client.patch(
        f"/api/v1/categorias/{category_id}/reactivar",
        headers=headers,
    )
    inactivate_group = await client.patch(
        f"/api/v1/grupos/{asociado_id}/inactivar",
        headers=headers,
    )
    reactivate_group = await client.patch(
        f"/api/v1/grupos/{asociado_id}/reactivar",
        headers=headers,
    )

    assert inactivate_category.status_code == 200
    assert reactivate_category.status_code == 200
    assert inactivate_group.status_code == 200
    assert reactivate_group.status_code == 200
    assert reactivate_group.json()["id_grupo"] == asociado_id
