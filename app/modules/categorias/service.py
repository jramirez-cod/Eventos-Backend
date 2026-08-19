from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.categorias.dto import CategoriaCreateDTO, InactivarCategoriaDTO
from app.modules.categorias.models import Categoria
from app.modules.categorias.repository import CategoriaRepository
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_CATEGORIAS = "CATEGORIAS"


class CategoriaServiceError(Exception):
    pass


class CategoriaNotFoundError(CategoriaServiceError):
    pass


class DuplicateCategoriaNameError(CategoriaServiceError):
    pass


class CategoriaEnUsoError(CategoriaServiceError):
    def __init__(self, *, nombres_empresas: list[str]) -> None:
        self.nombres_empresas = nombres_empresas
        super().__init__(
            "La categoría está siendo usada por empresas activas: "
            + ", ".join(nombres_empresas)
        )


class CategoriaService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.categorias = CategoriaRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_categoria(
        self, *, data: CategoriaCreateDTO, actor: Usuario
    ) -> Categoria:
        if await self.categorias.get_by_nombre(data.nombre_categoria):
            raise DuplicateCategoriaNameError("El nombre de la categoría ya existe.")

        try:
            categoria = await self.categorias.create(
                nombre_categoria=data.nombre_categoria,
                descripcion=data.descripcion,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="categoria",
                id_entidad=categoria.id_categoria,
                accion="CREACION_CATEGORIA",
                valor_nuevo={
                    "id_categoria": categoria.id_categoria,
                    "nombre_categoria": categoria.nombre_categoria,
                    "estado": categoria.estado,
                },
            )
            await self.db.commit()
            await self.db.refresh(categoria)
            return categoria
        except Exception:
            await self.db.rollback()
            raise

    async def inactivar_categoria(
        self, *, id_categoria: int, data: InactivarCategoriaDTO, actor: Usuario
    ) -> Categoria:
        categoria = await self.categorias.get_by_id(id_categoria)
        if categoria is None:
            raise CategoriaNotFoundError("Categoría no encontrada.")

        empresas = await self.categorias.list_empresas_activas_usando(id_categoria)
        if empresas:
            raise CategoriaEnUsoError(
                nombres_empresas=[empresa.nombre_empresa for empresa in empresas]
            )

        return await self._set_estado(
            id_categoria=id_categoria,
            estado=False,
            accion="INACTIVACION_CATEGORIA",
            motivo=data.motivo,
            actor=actor,
        )

    async def reactivar_categoria(
        self, *, id_categoria: int, actor: Usuario
    ) -> Categoria:
        return await self._set_estado(
            id_categoria=id_categoria,
            estado=True,
            accion="REACTIVACION_CATEGORIA",
            motivo=None,
            actor=actor,
        )

    async def _set_estado(
        self,
        *,
        id_categoria: int,
        estado: bool,
        accion: str,
        motivo: str | None,
        actor: Usuario,
    ) -> Categoria:
        categoria = await self.categorias.get_by_id(id_categoria)
        if categoria is None:
            raise CategoriaNotFoundError("Categoría no encontrada.")

        anterior = {"estado": categoria.estado}
        try:
            await self.categorias.set_estado(categoria, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="categoria",
                id_entidad=categoria.id_categoria,
                accion=accion,
                valor_anterior=anterior,
                valor_nuevo={"estado": categoria.estado},
                motivo=motivo,
            )
            await self.db.commit()
            await self.db.refresh(categoria)
            return categoria
        except Exception:
            await self.db.rollback()
            raise

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_CATEGORIAS)
        return modulo.id_modulo if modulo else None
