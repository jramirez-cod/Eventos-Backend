from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.categorias.models import Categoria
from app.modules.categorias.repository import CategoriaRepository
from app.modules.contactos.dto import ContactoCreate, ContactoResponse
from app.modules.contactos.service import ContactoService
from app.modules.empresas.dto import (
    CambiarClasificacionDTO,
    EmpresaCreateDTO,
    EmpresaRegistroCompletoDTO,
    EmpresaUpdateDTO,
)
from app.modules.empresas.models import Empresa, EmpresaHistorialClasificacion
from app.modules.empresas.repository import EmpresaRepository
from app.modules.empresas.ruc_client import RucConsultor, RucInfo, get_ruc_consultor
from app.modules.grupos.models import Grupo
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_EMPRESAS = "EMPRESAS"


class EmpresaServiceError(Exception):
    pass


class EmpresaNotFoundError(EmpresaServiceError):
    pass


class DuplicateRucError(EmpresaServiceError):
    pass


class DetalleCategoriaInvalidoError(EmpresaServiceError):
    pass


class InvalidEmpresaNameError(EmpresaServiceError):
    pass


class EmpresaService:
    def __init__(
        self, db: AsyncSession, *, ruc_consultor: RucConsultor | None = None
    ) -> None:
        self.db = db
        self.empresas = EmpresaRepository(db)
        self.categorias = CategoriaRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)
        self.ruc_consultor = ruc_consultor or get_ruc_consultor()

    async def consultar_ruc(self, ruc: str) -> RucInfo:
        return await self.ruc_consultor.consultar(ruc)

    async def crear_empresa(
        self, *, data: EmpresaCreateDTO, actor: Usuario, commit: bool = True
    ) -> tuple[Empresa, Grupo, Categoria]:
        if await self.empresas.get_by_ruc(data.ruc):
            raise DuplicateRucError("El RUC ya está registrado.")

        detalle_completo = await self._validar_detalle_categoria(
            data.id_detalle_categoria
        )

        try:
            empresa = await self.empresas.create(
                nombre_empresa=data.nombre_empresa,
                ruc=data.ruc,
                id_detalle_categoria=data.id_detalle_categoria,
                razon_social=data.razon_social,
                nombre_comercial=data.nombre_comercial,
            )
            await self.empresas.create_historial(
                id_empresa=empresa.id_empresa,
                id_detalle_categoria=data.id_detalle_categoria,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="empresa",
                id_entidad=empresa.id_empresa,
                accion="CREACION_EMPRESA",
                valor_nuevo={
                    "id_empresa": empresa.id_empresa,
                    "nombre_empresa": empresa.nombre_empresa,
                    "ruc": empresa.ruc,
                    "id_detalle_categoria": empresa.id_detalle_categoria,
                    "estado": empresa.estado,
                },
            )
            if commit:
                await self.db.commit()
                await self.db.refresh(empresa)
            else:
                await self.db.flush()
        except Exception:
            await self.db.rollback()
            raise

        _, grupo, categoria = detalle_completo
        return empresa, grupo, categoria

    async def crear_empresa_con_contactos(
        self, *, data: EmpresaRegistroCompletoDTO, actor: Usuario
    ) -> tuple[tuple[Empresa, Grupo, Categoria], list[ContactoResponse]]:
        contactos_service = ContactoService(self.db)
        contactos: list[ContactoResponse] = []

        try:
            empresa_detallada = await self.crear_empresa(
                data=data.empresa,
                actor=actor,
                commit=False,
            )
            empresa = empresa_detallada[0]

            for contacto_data in data.contactos:
                contacto = await contactos_service.crear_contacto(
                    data=ContactoCreate(
                        id_empresa=empresa.id_empresa,
                        **contacto_data.model_dump(),
                    ),
                    actor=actor,
                    commit=False,
                )
                contactos.append(contacto)

            await self.db.commit()
            await self.db.refresh(empresa)
        except Exception:
            await self.db.rollback()
            raise

        return empresa_detallada, contactos

    async def obtener_empresa(
        self, id_empresa: int
    ) -> tuple[Empresa, Grupo, Categoria]:
        detallado = await self.empresas.get_detallado(id_empresa)
        if detallado is None:
            raise EmpresaNotFoundError("Empresa no encontrada.")
        return detallado

    async def actualizar_empresa(
        self, *, id_empresa: int, data: EmpresaUpdateDTO, actor: Usuario
    ) -> tuple[Empresa, Grupo, Categoria]:
        empresa, _, _ = await self.obtener_empresa(id_empresa)
        nombre_empresa = self._normalize_required_text(
            data.nombre_empresa,
            field_name="nombre de la empresa",
        )
        razon_social = self._normalize_optional_text(data.razon_social)
        nombre_comercial = self._normalize_optional_text(data.nombre_comercial)
        anterior = self._audit_values(empresa)

        try:
            await self.empresas.update_general(
                empresa,
                nombre_empresa=nombre_empresa,
                razon_social=razon_social,
                nombre_comercial=nombre_comercial,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="empresa",
                id_entidad=empresa.id_empresa,
                accion="ACTUALIZAR_EMPRESA",
                valor_anterior=anterior,
                valor_nuevo=self._audit_values(empresa),
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_empresa(id_empresa)

    async def cambiar_clasificacion(
        self, *, id_empresa: int, data: CambiarClasificacionDTO, actor: Usuario
    ) -> tuple[Empresa, Grupo, Categoria]:
        empresa = await self.empresas.get_by_id(id_empresa)
        if empresa is None:
            raise EmpresaNotFoundError("Empresa no encontrada.")

        detalle_completo = await self._validar_detalle_categoria(
            data.id_detalle_categoria
        )

        anterior = {"id_detalle_categoria": empresa.id_detalle_categoria}
        try:
            await self.empresas.cerrar_historial_vigente(id_empresa)
            await self.empresas.update_clasificacion(
                empresa, id_detalle_categoria=data.id_detalle_categoria
            )
            await self.empresas.create_historial(
                id_empresa=id_empresa,
                id_detalle_categoria=data.id_detalle_categoria,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="empresa",
                id_entidad=empresa.id_empresa,
                accion="CAMBIO_CLASIFICACION_EMPRESA",
                valor_anterior=anterior,
                valor_nuevo={"id_detalle_categoria": empresa.id_detalle_categoria},
                motivo=data.motivo,
            )
            await self.db.commit()
            await self.db.refresh(empresa)
        except Exception:
            await self.db.rollback()
            raise

        _, grupo, categoria = detalle_completo
        return empresa, grupo, categoria

    async def inactivar_empresa(
        self, *, id_empresa: int, motivo: str | None, actor: Usuario
    ) -> Empresa:
        return await self._set_estado(
            id_empresa=id_empresa,
            estado=False,
            accion="INACTIVACION_EMPRESA",
            motivo=motivo,
            actor=actor,
        )

    async def reactivar_empresa(self, *, id_empresa: int, actor: Usuario) -> Empresa:
        return await self._set_estado(
            id_empresa=id_empresa,
            estado=True,
            accion="REACTIVACION_EMPRESA",
            motivo=None,
            actor=actor,
        )

    async def listar_historial(
        self, id_empresa: int
    ) -> list[tuple[EmpresaHistorialClasificacion, Grupo, Categoria]]:
        empresa = await self.empresas.get_by_id(id_empresa)
        if empresa is None:
            raise EmpresaNotFoundError("Empresa no encontrada.")
        return await self.empresas.list_historial(id_empresa)

    async def _set_estado(
        self,
        *,
        id_empresa: int,
        estado: bool,
        accion: str,
        motivo: str | None,
        actor: Usuario,
    ) -> Empresa:
        empresa = await self.empresas.get_by_id(id_empresa)
        if empresa is None:
            raise EmpresaNotFoundError("Empresa no encontrada.")

        anterior = {"estado": empresa.estado}
        try:
            await self.empresas.set_estado(empresa, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="empresa",
                id_entidad=empresa.id_empresa,
                accion=accion,
                valor_anterior=anterior,
                valor_nuevo={"estado": empresa.estado},
                motivo=motivo,
            )
            await self.db.commit()
            await self.db.refresh(empresa)
            return empresa
        except Exception:
            await self.db.rollback()
            raise

    async def _validar_detalle_categoria(
        self, id_detalle_categoria: int
    ) -> tuple[object, Grupo, Categoria]:
        detalle_completo = await self.categorias.get_detalle_completo_by_id(
            id_detalle_categoria
        )
        if detalle_completo is None:
            raise DetalleCategoriaInvalidoError(
                "La combinación de grupo y categoría no existe."
            )

        _, grupo, categoria = detalle_completo
        if not grupo.estado or not categoria.estado:
            raise DetalleCategoriaInvalidoError(
                "El grupo o la categoría seleccionados están inactivos."
            )
        return detalle_completo

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_EMPRESAS)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def _normalize_required_text(value: str, *, field_name: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise InvalidEmpresaNameError(f"El {field_name} es obligatorio.")
        return normalized

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _audit_values(empresa: Empresa) -> dict[str, object]:
        return {
            "id_empresa": empresa.id_empresa,
            "nombre_empresa": empresa.nombre_empresa,
            "razon_social": empresa.razon_social,
            "nombre_comercial": empresa.nombre_comercial,
            "ruc": empresa.ruc,
            "id_detalle_categoria": empresa.id_detalle_categoria,
            "estado": empresa.estado,
        }
