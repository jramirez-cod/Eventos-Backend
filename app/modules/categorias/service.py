from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.categorias.dto import (
    CategoriaCreateDTO,
    CategoriaGrupoResponseDTO,
)
from app.modules.categorias.models import Categoria
from app.modules.categorias.repository import CategoriaRepository
from app.modules.empresas.models import Empresa
from app.modules.grupos.repository import GrupoRepository
from app.modules.usuarios.models import Usuario


class CategoriaServiceError(Exception):
    pass


class CategoriaNotFoundError(CategoriaServiceError):
    pass


class CategoriaGroupNotFoundError(CategoriaServiceError):
    pass


class InactiveGroupError(CategoriaServiceError):
    pass


class InactiveCategoryError(CategoriaServiceError):
    pass


class DuplicateCategoryRelationError(CategoriaServiceError):
    pass


class ActiveCompaniesInCategoryError(CategoriaServiceError):
    def __init__(self, empresas: list[Empresa]) -> None:
        self.empresas = empresas
        super().__init__(
            "No se puede inactivar la categoría porque existen empresas activas asociadas."
        )


class CategoriaService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.categorias = CategoriaRepository(db)
        self.grupos = GrupoRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_categoria(
        self,
        *,
        data: CategoriaCreateDTO,
        actor: Usuario,
    ) -> CategoriaGrupoResponseDTO:
        grupo = await self.grupos.get_by_id(data.id_grupo, for_update=True)
        if grupo is None:
            raise CategoriaGroupNotFoundError("Grupo no encontrado.")
        if not grupo.estado:
            raise InactiveGroupError("El grupo se encuentra inactivo.")

        categoria = await self.categorias.get_by_name(data.nombre_categoria)
        category_was_created = False
        if categoria is None:
            try:
                async with self.db.begin_nested():
                    categoria = await self.categorias.create_category(
                        nombre_categoria=data.nombre_categoria,
                        descripcion=data.descripcion,
                    )
                category_was_created = True
            except IntegrityError:
                categoria = await self.categorias.get_by_name(
                    data.nombre_categoria
                )
                if categoria is None:
                    await self.db.rollback()
                    raise

        if not categoria.estado:
            raise InactiveCategoryError(
                "La categoría existe pero se encuentra inactiva."
            )

        existing_detail = (
            await self.categorias.get_detail_by_group_and_category(
                id_grupo=grupo.id_grupo,
                id_categoria=categoria.id_categoria,
            )
        )
        if existing_detail is not None:
            raise DuplicateCategoryRelationError(
                "La categoría ya está asociada al grupo."
            )

        try:
            detail = await self.categorias.create_detail(
                id_grupo=grupo.id_grupo,
                id_categoria=categoria.id_categoria,
            )
            if category_was_created:
                await self.auditoria.create(
                    id_usuario=actor.id_usuario,
                    entidad="categoria",
                    id_entidad=categoria.id_categoria,
                    accion="CREAR_CATEGORIA",
                    valor_nuevo=self._audit_value(categoria),
                )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                entidad="detalle_categoria",
                id_entidad=detail.id_detalle_categoria,
                accion="ASOCIAR_CATEGORIA_GRUPO",
                valor_nuevo={
                    "id_detalle_categoria": detail.id_detalle_categoria,
                    "id_grupo": detail.id_grupo,
                    "id_categoria": detail.id_categoria,
                    "estado": detail.estado,
                },
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateCategoryRelationError(
                "La categoría ya está asociada al grupo."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return CategoriaGrupoResponseDTO(
            id_categoria=categoria.id_categoria,
            nombre_categoria=categoria.nombre_categoria,
            descripcion=categoria.descripcion,
            estado=categoria.estado,
            id_grupo=detail.id_grupo,
            id_detalle_categoria=detail.id_detalle_categoria,
            estado_relacion=detail.estado,
        )

    async def inactivar_categoria(
        self,
        *,
        id_categoria: int,
        actor: Usuario,
    ) -> Categoria:
        categoria = await self._get_for_update(id_categoria)
        if not categoria.estado:
            return categoria

        empresas = await self.categorias.get_active_companies_by_category(
            id_categoria
        )
        if empresas:
            raise ActiveCompaniesInCategoryError(empresas)

        return await self._change_estado(
            categoria=categoria,
            estado=False,
            accion="INACTIVAR_CATEGORIA",
            actor=actor,
        )

    async def reactivar_categoria(
        self,
        *,
        id_categoria: int,
        actor: Usuario,
    ) -> Categoria:
        categoria = await self._get_for_update(id_categoria)
        if categoria.estado:
            return categoria

        return await self._change_estado(
            categoria=categoria,
            estado=True,
            accion="REACTIVAR_CATEGORIA",
            actor=actor,
        )

    async def _get_for_update(self, id_categoria: int) -> Categoria:
        categoria = await self.categorias.get_by_id(
            id_categoria,
            for_update=True,
        )
        if categoria is None:
            raise CategoriaNotFoundError("Categoría no encontrada.")
        return categoria

    async def _change_estado(
        self,
        *,
        categoria: Categoria,
        estado: bool,
        accion: str,
        actor: Usuario,
    ) -> Categoria:
        previous_value = categoria.estado
        try:
            await self.categorias.update_estado(categoria, estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                entidad="categoria",
                id_entidad=categoria.id_categoria,
                accion=accion,
                valor_anterior={"estado": previous_value},
                valor_nuevo={"estado": categoria.estado},
            )
            await self.db.commit()
            return categoria
        except Exception:
            await self.db.rollback()
            raise

    @staticmethod
    def _audit_value(categoria: Categoria) -> dict[str, object]:
        return {
            "id_categoria": categoria.id_categoria,
            "nombre_categoria": categoria.nombre_categoria,
            "descripcion": categoria.descripcion,
            "estado": categoria.estado,
        }
