from app.modules.categorias.models import Categoria, DetalleCategoria
from app.modules.empresas.ruc_client import RucInfo, RucNoEncontradoError
from app.modules.grupos.models import Grupo


class FakeRucConsultor:
    def __init__(self, respuestas: dict[str, RucInfo] | None = None) -> None:
        self.respuestas = respuestas or {}
        self.llamadas: list[str] = []

    async def consultar(self, ruc: str) -> RucInfo:
        self.llamadas.append(ruc)
        if ruc not in self.respuestas:
            raise RucNoEncontradoError("RUC no encontrado.")
        return self.respuestas[ruc]


async def create_grupo(
    session, *, id_grupo: int, nombre_grupo: str, estado: bool = True
) -> Grupo:
    grupo = Grupo(id_grupo=id_grupo, nombre_grupo=nombre_grupo, estado=estado)
    session.add(grupo)
    await session.flush()
    return grupo


async def create_categoria(
    session, *, nombre_categoria: str, estado: bool = True
) -> Categoria:
    categoria = Categoria(nombre_categoria=nombre_categoria, estado=estado)
    session.add(categoria)
    await session.flush()
    return categoria


async def create_detalle_categoria(
    session, *, id_grupo: int, id_categoria: int, estado: bool = True
) -> DetalleCategoria:
    detalle = DetalleCategoria(
        id_grupo=id_grupo, id_categoria=id_categoria, estado=estado
    )
    session.add(detalle)
    await session.flush()
    return detalle


async def create_grupo_categoria_detalle(
    session, *, id_grupo: int = 700, nombre_grupo: str = "GrupoEmpresaTest"
) -> tuple[Grupo, Categoria, DetalleCategoria]:
    grupo = await create_grupo(session, id_grupo=id_grupo, nombre_grupo=nombre_grupo)
    categoria = await create_categoria(session, nombre_categoria=f"Cat{id_grupo}")
    detalle = await create_detalle_categoria(
        session, id_grupo=grupo.id_grupo, id_categoria=categoria.id_categoria
    )
    return grupo, categoria, detalle
