from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.categorias.models import DetalleCategoria
from app.modules.categorias.repository import CategoriaRepository
from app.modules.grupos.dto import (
    AsignarCategoriaDTO,
    GrupoCreateDTO,
    GrupoUpdateDTO,
    InactivarGrupoDTO,
)
from app.modules.grupos.models import Grupo
from app.modules.grupos.repository import GrupoRepository
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_GRUPOS = "GRUPOS"


class GrupoServiceError(Exception):
    pass


class GrupoNotFoundError(GrupoServiceError):
    pass


class DuplicateGrupoIdError(GrupoServiceError):
    pass


class DuplicateGrupoNameError(GrupoServiceError):
    pass


class InvalidGrupoNameError(GrupoServiceError):
    pass


class CategoriaNotFoundError(GrupoServiceError):
    pass


class CategoriaYaAsignadaError(GrupoServiceError):
    pass


class AsignacionNotFoundError(GrupoServiceError):
    pass


class GrupoEnUsoError(GrupoServiceError):
    def __init__(self, *, nombres_empresas: list[str]) -> None:
        self.nombres_empresas = nombres_empresas
        super().__init__(
            "El grupo está siendo usado por empresas activas: "
            + ", ".join(nombres_empresas)
        )


class GrupoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.grupos = GrupoRepository(db)
        self.categorias = CategoriaRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_grupo(self, *, data: GrupoCreateDTO, actor: Usuario) -> Grupo:
        if await self.grupos.get_by_id(data.id_grupo):
            raise DuplicateGrupoIdError("El id de grupo ya existe.")
        if await self.grupos.get_by_nombre(data.nombre_grupo):
            raise DuplicateGrupoNameError("El nombre del grupo ya existe.")

        try:
            grupo = await self.grupos.create(
                id_grupo=data.id_grupo,
                nombre_grupo=data.nombre_grupo,
                descripcion=data.descripcion,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="grupo",
                id_entidad=grupo.id_grupo,
                accion="CREACION_GRUPO",
                valor_nuevo={
                    "id_grupo": grupo.id_grupo,
                    "nombre_grupo": grupo.nombre_grupo,
                    "estado": grupo.estado,
                },
            )
            await self.db.commit()
            await self.db.refresh(grupo)
            return grupo
        except Exception:
            await self.db.rollback()
            raise

    async def obtener_grupo(self, id_grupo: int) -> Grupo:
        grupo = await self.grupos.get_by_id(id_grupo)
        if grupo is None:
            raise GrupoNotFoundError("Grupo no encontrado.")
        return grupo

    async def actualizar_grupo(
        self, *, id_grupo: int, data: GrupoUpdateDTO, actor: Usuario
    ) -> Grupo:
        grupo = await self.obtener_grupo(id_grupo)
        nombre = self._normalize_name(data.nombre_grupo)
        descripcion = self._normalize_description(data.descripcion)
        if await self.grupos.get_by_nombre(nombre, exclude_id=id_grupo):
            raise DuplicateGrupoNameError("El nombre del grupo ya existe.")

        anterior = self._audit_values(grupo)
        try:
            await self.grupos.update(
                grupo,
                nombre_grupo=nombre,
                descripcion=descripcion,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="grupo",
                id_entidad=grupo.id_grupo,
                accion="ACTUALIZAR_GRUPO",
                valor_anterior=anterior,
                valor_nuevo=self._audit_values(grupo),
            )
            await self.db.commit()
            await self.db.refresh(grupo)
            return grupo
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateGrupoNameError(
                "El nombre del grupo ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def inactivar_grupo(
        self, *, id_grupo: int, data: InactivarGrupoDTO, actor: Usuario
    ) -> Grupo:
        grupo = await self.grupos.get_by_id(id_grupo)
        if grupo is None:
            raise GrupoNotFoundError("Grupo no encontrado.")

        empresas = await self.grupos.list_empresas_activas_usando(id_grupo)
        if empresas:
            raise GrupoEnUsoError(
                nombres_empresas=[empresa.nombre_empresa for empresa in empresas]
            )

        return await self._set_estado(
            id_grupo=id_grupo,
            estado=False,
            accion="INACTIVACION_GRUPO",
            motivo=data.motivo,
            actor=actor,
        )

    async def reactivar_grupo(self, *, id_grupo: int, actor: Usuario) -> Grupo:
        return await self._set_estado(
            id_grupo=id_grupo,
            estado=True,
            accion="REACTIVACION_GRUPO",
            motivo=None,
            actor=actor,
        )

    async def _set_estado(
        self,
        *,
        id_grupo: int,
        estado: bool,
        accion: str,
        motivo: str | None,
        actor: Usuario,
    ) -> Grupo:
        grupo = await self.grupos.get_by_id(id_grupo)
        if grupo is None:
            raise GrupoNotFoundError("Grupo no encontrado.")

        anterior = {"estado": grupo.estado}
        try:
            await self.grupos.set_estado(grupo, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="grupo",
                id_entidad=grupo.id_grupo,
                accion=accion,
                valor_anterior=anterior,
                valor_nuevo={"estado": grupo.estado},
                motivo=motivo,
            )
            await self.db.commit()
            await self.db.refresh(grupo)
            return grupo
        except Exception:
            await self.db.rollback()
            raise

    async def asignar_categoria(
        self, *, id_grupo: int, data: AsignarCategoriaDTO, actor: Usuario
    ) -> DetalleCategoria:
        grupo = await self.grupos.get_by_id(id_grupo)
        if grupo is None or not grupo.estado:
            raise GrupoNotFoundError("Grupo no encontrado.")

        categoria = await self.categorias.get_by_id(data.id_categoria)
        if categoria is None or not categoria.estado:
            raise CategoriaNotFoundError("Categoría no encontrada.")

        existente = await self.categorias.get_detalle(
            id_grupo=id_grupo, id_categoria=data.id_categoria
        )
        if existente is not None and existente.estado:
            raise CategoriaYaAsignadaError(
                "La categoría ya está asignada a este grupo."
            )

        try:
            if existente is not None:
                detalle = await self.categorias.set_detalle_estado(
                    existente, estado=True
                )
            else:
                detalle = await self.categorias.create_detalle(
                    id_grupo=id_grupo, id_categoria=data.id_categoria
                )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="detalle_categoria",
                id_entidad=detalle.id_detalle_categoria,
                accion="ASIGNACION_CATEGORIA_GRUPO",
                valor_nuevo={
                    "id_grupo": id_grupo,
                    "id_categoria": data.id_categoria,
                    "estado": detalle.estado,
                },
            )
            await self.db.commit()
            await self.db.refresh(detalle)
            return detalle
        except Exception:
            await self.db.rollback()
            raise

    async def quitar_categoria(
        self, *, id_grupo: int, id_categoria: int, actor: Usuario
    ) -> DetalleCategoria:
        detalle = await self.categorias.get_detalle(
            id_grupo=id_grupo, id_categoria=id_categoria
        )
        if detalle is None or not detalle.estado:
            raise AsignacionNotFoundError(
                "La categoría no está asignada a este grupo."
            )

        try:
            await self.categorias.set_detalle_estado(detalle, estado=False)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="detalle_categoria",
                id_entidad=detalle.id_detalle_categoria,
                accion="DESASIGNACION_CATEGORIA_GRUPO",
                valor_anterior={"estado": True},
                valor_nuevo={"estado": False},
            )
            await self.db.commit()
            await self.db.refresh(detalle)
            return detalle
        except Exception:
            await self.db.rollback()
            raise

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_GRUPOS)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def _normalize_name(value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise InvalidGrupoNameError("El nombre del grupo es obligatorio.")
        return normalized

    @staticmethod
    def _normalize_description(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _audit_values(grupo: Grupo) -> dict[str, object]:
        return {
            "id_grupo": grupo.id_grupo,
            "nombre_grupo": grupo.nombre_grupo,
            "descripcion": grupo.descripcion,
            "estado": grupo.estado,
        }
