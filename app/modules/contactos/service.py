from datetime import UTC, datetime
import math
import re
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.contactos.dto import (
    ContactoCambiarEmpresaRequest,
    ContactoCreate,
    ContactoFusionRequest,
    ContactoListItem,
    ContactoPage,
    ContactoResponse,
    ContactoUpdate,
)
from app.modules.contactos.models import Contacto
from app.modules.contactos.repository import ContactoDetalle, ContactoRepository
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_CONTACTOS = "CONTACTOS"


class ContactoServiceError(Exception):
    pass


class ContactoNotFoundError(ContactoServiceError):
    pass


class EmpresaNotFoundError(ContactoServiceError):
    pass


class EmpresaInactiveError(ContactoServiceError):
    pass


class CargoNotFoundError(ContactoServiceError):
    pass


class CargoInactiveError(ContactoServiceError):
    pass


class TipoDocumentoNotFoundError(ContactoServiceError):
    pass


class TipoDocumentoInactiveError(ContactoServiceError):
    pass


class DuplicateDocumentError(ContactoServiceError):
    pass


class InvalidDocumentPairError(ContactoServiceError):
    pass


class InvalidPhoneError(ContactoServiceError):
    pass


class SameCompanyError(ContactoServiceError):
    pass


class SameContactFusionError(ContactoServiceError):
    pass


class ContactoPersistenceConflictError(ContactoServiceError):
    pass


def normalize_phone(phone: str | None) -> str | None:
    if phone is None:
        return None

    normalized = "".join(phone.split())
    if not normalized:
        return None

    local_phone = re.fullmatch(r"9\d{8}", normalized)
    international_phone = re.fullmatch(r"\+[1-9]\d{9,14}", normalized)
    if local_phone is None and international_phone is None:
        raise InvalidPhoneError(
            "El celular debe tener 9 dígitos en formato local o usar un "
            "código de país válido, por ejemplo +51987654321."
        )
    return normalized


class ContactoService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.contactos = ContactoRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_contacto(
        self,
        *,
        data: ContactoCreate,
        actor: Usuario,
        commit: bool = True,
    ) -> ContactoResponse:
        await self._validar_empresa_activa(data.id_empresa)
        await self._validar_cargo_activo(data.id_cargo)
        await self._validar_tipo_documento_activo(data.id_tipo_documento)
        await self._validar_documento_unico(data.numero_documento)
        celular = normalize_phone(data.celular)

        try:
            if data.es_contacto_principal:
                await self.contactos.unset_contacto_principal(
                    id_empresa=data.id_empresa
                )
            contacto = await self.contactos.create(
                id_empresa=data.id_empresa,
                id_cargo=data.id_cargo,
                id_tipo_documento=data.id_tipo_documento,
                numero_documento=data.numero_documento,
                nombres=data.nombres,
                apellidos=data.apellidos,
                genero=data.genero,
                celular=celular,
                correo=str(data.correo) if data.correo is not None else None,
                es_contacto_principal=data.es_contacto_principal,
            )
            await self.contactos.create_historial_empresa(
                id_contacto=contacto.id_contacto,
                id_empresa=contacto.id_empresa,
                id_usuario_cambio=actor.id_usuario,
                motivo="Registro inicial del contacto",
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="contacto",
                id_entidad=contacto.id_contacto,
                accion="CREAR_CONTACTO",
                valor_nuevo=self._audit_values(contacto),
            )
            if commit:
                await self.db.commit()
            else:
                await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            if data.numero_documento is not None:
                raise DuplicateDocumentError(
                    "El número de documento ya está registrado."
                ) from exc
            raise ContactoPersistenceConflictError(
                "No se pudo crear el contacto por un conflicto de datos."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_contacto(contacto.id_contacto)

    async def actualizar_contacto(
        self, *, id_contacto: int, data: ContactoUpdate, actor: Usuario
    ) -> ContactoResponse:
        contacto = await self.contactos.get_by_id(id_contacto)
        if contacto is None:
            raise ContactoNotFoundError("Contacto no encontrado.")

        values = data.model_dump(exclude_unset=True)
        await self._preparar_actualizacion(contacto, values)
        anterior = {
            field: getattr(contacto, field)
            for field in values
            if hasattr(contacto, field)
        }

        try:
            if values.get("es_contacto_principal") is True:
                await self.contactos.unset_contacto_principal(
                    id_empresa=contacto.id_empresa, exclude_id=contacto.id_contacto
                )
            await self.contactos.update(contacto, values)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="contacto",
                id_entidad=contacto.id_contacto,
                accion="ACTUALIZAR_CONTACTO",
                valor_anterior=anterior,
                valor_nuevo={field: getattr(contacto, field) for field in values},
            )
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            if "numero_documento" in values:
                raise DuplicateDocumentError(
                    "El número de documento ya está registrado."
                ) from exc
            raise ContactoPersistenceConflictError(
                "No se pudo actualizar el contacto por un conflicto de datos."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_contacto(contacto.id_contacto)

    async def obtener_contacto(self, id_contacto: int) -> ContactoResponse:
        detalle = await self.contactos.get_detallado(id_contacto)
        if detalle is None:
            raise ContactoNotFoundError("Contacto no encontrado.")
        return self._to_response(detalle)

    async def listar_contactos(
        self,
        *,
        search: str | None,
        id_empresa: int | None,
        id_cargo: int | None,
        numero_documento: str | None,
        estado: bool | None,
        page: int,
        page_size: int,
    ) -> ContactoPage:
        rows, total = await self.contactos.list_detallado(
            search=search,
            id_empresa=id_empresa,
            id_cargo=id_cargo,
            numero_documento=numero_documento,
            estado=estado,
            page=page,
            page_size=page_size,
        )
        return ContactoPage(
            items=[
                ContactoListItem(**self._to_response(row).model_dump())
                for row in rows
            ],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def listar_para_exportar(
        self,
        *,
        search: str | None,
        id_empresa: int | None,
        id_cargo: int | None,
        numero_documento: str | None,
        estado: bool | None,
    ) -> list[ContactoResponse]:
        rows, _ = await self.contactos.list_detallado(
            search=search,
            id_empresa=id_empresa,
            id_cargo=id_cargo,
            numero_documento=numero_documento,
            estado=estado,
            page=1,
            page_size=None,
        )
        return [self._to_response(row) for row in rows]

    async def cambiar_empresa(
        self,
        *,
        id_contacto: int,
        data: ContactoCambiarEmpresaRequest,
        actor: Usuario,
    ) -> ContactoResponse:
        contacto = await self.contactos.get_by_id_for_update(id_contacto)
        if contacto is None:
            raise ContactoNotFoundError("Contacto no encontrado.")
        if contacto.id_empresa == data.id_empresa:
            raise SameCompanyError("El contacto ya pertenece a la empresa indicada.")
        await self._validar_empresa_activa(data.id_empresa)

        empresa_anterior = contacto.id_empresa
        try:
            momento_cambio = datetime.now(UTC)
            historiales_cerrados = (
                await self.contactos.cerrar_historial_vigente(
                    id_contacto, fecha_fin=momento_cambio
                )
            )
            if historiales_cerrados == 0:
                await self.contactos.create_historial_empresa(
                    id_contacto=id_contacto,
                    id_empresa=empresa_anterior,
                    id_usuario_cambio=actor.id_usuario,
                    motivo="Vigencia anterior reconstruida al cambiar de empresa",
                    fecha_inicio=contacto.creado_en,
                    fecha_fin=momento_cambio,
                )
            await self.contactos.cambiar_empresa(
                contacto, id_empresa=data.id_empresa
            )
            await self.contactos.create_historial_empresa(
                id_contacto=id_contacto,
                id_empresa=data.id_empresa,
                id_usuario_cambio=actor.id_usuario,
                motivo=data.motivo,
                fecha_inicio=momento_cambio,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="contacto",
                id_entidad=id_contacto,
                accion="CAMBIAR_EMPRESA_CONTACTO",
                valor_anterior={"id_empresa": empresa_anterior},
                valor_nuevo={"id_empresa": data.id_empresa},
                motivo=data.motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_contacto(id_contacto)

    async def cambiar_estado(
        self,
        *,
        id_contacto: int,
        estado: bool,
        motivo: str | None,
        actor: Usuario,
    ) -> ContactoResponse:
        contacto = await self.contactos.get_by_id(id_contacto)
        if contacto is None:
            raise ContactoNotFoundError("Contacto no encontrado.")

        estado_anterior = contacto.estado
        accion = "REACTIVAR_CONTACTO" if estado else "INACTIVAR_CONTACTO"
        try:
            await self.contactos.set_estado(contacto, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="contacto",
                id_entidad=id_contacto,
                accion=accion,
                valor_anterior={"estado": estado_anterior},
                valor_nuevo={"estado": estado},
                motivo=motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_contacto(id_contacto)

    async def fusionar_contactos(
        self, *, data: ContactoFusionRequest, actor: Usuario
    ) -> ContactoResponse:
        if data.id_contacto_principal == data.id_contacto_duplicado:
            raise SameContactFusionError(
                "El contacto principal y el duplicado deben ser diferentes."
            )

        principal = await self.contactos.get_by_id_for_update(
            data.id_contacto_principal
        )
        duplicado = await self.contactos.get_by_id_for_update(
            data.id_contacto_duplicado
        )
        if principal is None or duplicado is None:
            raise ContactoNotFoundError("Uno de los contactos no existe.")

        estado_anterior = duplicado.estado
        try:
            await self.contactos.set_estado(duplicado, estado=False)
            await self.contactos.cerrar_historial_vigente(
                duplicado.id_contacto
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="contacto",
                id_entidad=principal.id_contacto,
                accion="FUSIONAR_CONTACTO",
                valor_anterior={
                    "id_contacto_duplicado": duplicado.id_contacto,
                    "estado_duplicado": estado_anterior,
                },
                valor_nuevo={
                    "id_contacto_principal": principal.id_contacto,
                    "id_contacto_duplicado": duplicado.id_contacto,
                    "estado_duplicado": False,
                },
                motivo=data.motivo,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

        return await self.obtener_contacto(principal.id_contacto)

    async def _preparar_actualizacion(
        self, contacto: Contacto, values: dict[str, Any]
    ) -> None:
        if "id_cargo" in values:
            await self._validar_cargo_activo(values["id_cargo"])

        effective_type = values.get(
            "id_tipo_documento", contacto.id_tipo_documento
        )
        effective_number = values.get(
            "numero_documento", contacto.numero_documento
        )
        if (effective_type is None) != (effective_number is None):
            raise InvalidDocumentPairError(
                "id_tipo_documento y numero_documento deben tener ambos un "
                "valor o ser nulos."
            )
        if "id_tipo_documento" in values and effective_type is not None:
            await self._validar_tipo_documento_activo(effective_type)
        if "numero_documento" in values and effective_number is not None:
            await self._validar_documento_unico(
                effective_number, exclude_id=contacto.id_contacto
            )
        if "celular" in values:
            values["celular"] = normalize_phone(values["celular"])
        if "correo" in values and values["correo"] is not None:
            values["correo"] = str(values["correo"])

    async def _validar_empresa_activa(self, id_empresa: int) -> None:
        empresa = await self.contactos.get_empresa(id_empresa)
        if empresa is None:
            raise EmpresaNotFoundError("Empresa no encontrada.")
        if not empresa.estado:
            raise EmpresaInactiveError("La empresa se encuentra inactiva.")

    async def _validar_cargo_activo(self, id_cargo: int | None) -> None:
        if id_cargo is None:
            return
        cargo = await self.contactos.get_cargo(id_cargo)
        if cargo is None:
            raise CargoNotFoundError("Cargo no encontrado.")
        if not cargo.estado:
            raise CargoInactiveError("El cargo se encuentra inactivo.")

    async def _validar_tipo_documento_activo(
        self, id_tipo_documento: int | None
    ) -> None:
        if id_tipo_documento is None:
            return
        tipo_documento = await self.contactos.get_tipo_documento(
            id_tipo_documento
        )
        if tipo_documento is None:
            raise TipoDocumentoNotFoundError("Tipo de documento no encontrado.")
        if not tipo_documento.estado:
            raise TipoDocumentoInactiveError(
                "El tipo de documento se encuentra inactivo."
            )

    async def _validar_documento_unico(
        self, numero_documento: str | None, *, exclude_id: int | None = None
    ) -> None:
        if numero_documento is None:
            return
        if await self.contactos.get_by_documento(
            numero_documento, exclude_id=exclude_id
        ):
            raise DuplicateDocumentError(
                "El número de documento ya está registrado."
            )

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_CONTACTOS)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def _audit_values(contacto: Contacto) -> dict[str, Any]:
        return {
            "id_contacto": contacto.id_contacto,
            "id_empresa": contacto.id_empresa,
            "id_cargo": contacto.id_cargo,
            "id_tipo_documento": contacto.id_tipo_documento,
            "numero_documento": contacto.numero_documento,
            "nombres": contacto.nombres,
            "apellidos": contacto.apellidos,
            "genero": contacto.genero,
            "celular": contacto.celular,
            "correo": contacto.correo,
            "es_contacto_principal": contacto.es_contacto_principal,
            "estado": contacto.estado,
        }

    @staticmethod
    def _to_response(detalle: ContactoDetalle) -> ContactoResponse:
        contacto = detalle.contacto
        return ContactoResponse(
            id_contacto=contacto.id_contacto,
            id_empresa=contacto.id_empresa,
            nombre_empresa=detalle.empresa.nombre_empresa,
            id_cargo=contacto.id_cargo,
            nombre_cargo=(
                detalle.cargo.nombre_cargo if detalle.cargo is not None else None
            ),
            id_tipo_documento=contacto.id_tipo_documento,
            nombre_tipo_documento=(
                detalle.tipo_documento.nombre_documento
                if detalle.tipo_documento is not None
                else None
            ),
            numero_documento=contacto.numero_documento,
            nombres=contacto.nombres,
            apellidos=contacto.apellidos,
            nombre_completo=contacto.nombre_completo,
            genero=contacto.genero,
            celular=contacto.celular,
            correo=contacto.correo,
            es_contacto_principal=contacto.es_contacto_principal,
            estado=contacto.estado,
        )
