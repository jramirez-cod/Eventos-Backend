from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.empresas.models import Empresa
from app.modules.grupos.dto import (
    GrupoConfiguracionCategoriaDTO,
    GrupoCreateDTO,
)
from app.modules.grupos.models import Grupo
from app.modules.grupos.repository import GrupoRepository
from app.modules.usuarios.models import Usuario


class GrupoServiceError(Exception):
    pass


class GrupoNotFoundError(GrupoServiceError):
    pass


class DuplicateGroupNameError(GrupoServiceError):
    pass


class ActiveCompaniesInGroupError(GrupoServiceError):
    def __init__(self, empresas: list[Empresa]) -> None:
        self.empresas = empresas
        super().__init__(
            "No se puede inactivar el grupo porque existen empresas activas asociadas."
        )


class GrupoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.grupos = GrupoRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_grupo(
        self,
        *,
        data: GrupoCreateDTO,
        actor: Usuario,
    ) -> Grupo:
        if await self.grupos.get_by_name(data.nombre_grupo) is not None:
            raise DuplicateGroupNameError("El nombre del grupo ya existe.")

        try:
            grupo = await self.grupos.create(
                nombre_grupo=data.nombre_grupo,
                descripcion=data.descripcion,
                requiere_categoria=data.requiere_categoria,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                entidad="grupo",
                id_entidad=grupo.id_grupo,
                accion="CREAR_GRUPO",
                valor_nuevo=self._audit_value(grupo),
            )
            await self.db.commit()
            return grupo
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateGroupNameError(
                "El nombre del grupo ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def inactivar_grupo(
        self,
        *,
        id_grupo: int,
        actor: Usuario,
    ) -> Grupo:
        grupo = await self._get_for_update(id_grupo)
        if not grupo.estado:
            return grupo

        empresas = await self.grupos.get_active_companies_by_group(id_grupo)
        if empresas:
            raise ActiveCompaniesInGroupError(empresas)

        return await self._change_estado(
            grupo=grupo,
            estado=False,
            accion="INACTIVAR_GRUPO",
            actor=actor,
        )

    async def reactivar_grupo(
        self,
        *,
        id_grupo: int,
        actor: Usuario,
    ) -> Grupo:
        grupo = await self._get_for_update(id_grupo)
        if grupo.estado:
            return grupo

        return await self._change_estado(
            grupo=grupo,
            estado=True,
            accion="REACTIVAR_GRUPO",
            actor=actor,
        )

    async def configurar_categoria(
        self,
        *,
        id_grupo: int,
        data: GrupoConfiguracionCategoriaDTO,
        actor: Usuario,
    ) -> Grupo:
        grupo = await self._get_for_update(id_grupo)
        previous_value = grupo.requiere_categoria
        if previous_value == data.requiere_categoria:
            return grupo

        try:
            await self.grupos.update_requiere_categoria(
                grupo,
                data.requiere_categoria,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                entidad="grupo",
                id_entidad=grupo.id_grupo,
                accion="CAMBIAR_REQUIERE_CATEGORIA",
                valor_anterior={"requiere_categoria": previous_value},
                valor_nuevo={
                    "requiere_categoria": grupo.requiere_categoria
                },
            )
            await self.db.commit()
            return grupo
        except Exception:
            await self.db.rollback()
            raise

    async def _get_for_update(self, id_grupo: int) -> Grupo:
        grupo = await self.grupos.get_by_id(id_grupo, for_update=True)
        if grupo is None:
            raise GrupoNotFoundError("Grupo no encontrado.")
        return grupo

    async def _change_estado(
        self,
        *,
        grupo: Grupo,
        estado: bool,
        accion: str,
        actor: Usuario,
    ) -> Grupo:
        previous_value = grupo.estado
        try:
            await self.grupos.update_estado(grupo, estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                entidad="grupo",
                id_entidad=grupo.id_grupo,
                accion=accion,
                valor_anterior={"estado": previous_value},
                valor_nuevo={"estado": grupo.estado},
            )
            await self.db.commit()
            return grupo
        except Exception:
            await self.db.rollback()
            raise

    @staticmethod
    def _audit_value(grupo: Grupo) -> dict[str, object]:
        return {
            "id_grupo": grupo.id_grupo,
            "nombre_grupo": grupo.nombre_grupo,
            "descripcion": grupo.descripcion,
            "requiere_categoria": grupo.requiere_categoria,
            "estado": grupo.estado,
        }
