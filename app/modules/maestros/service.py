import math

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.auditoria.repository import AuditoriaRepository
from app.modules.maestros.dto import (
    AreaCreate,
    AreaListResponse,
    AreaResponse,
    AreaUpdate,
    BeneficioCreate,
    BeneficioListResponse,
    BeneficioResponse,
    BeneficioUpdate,
    CargoCreate,
    CargoListResponse,
    CargoResponse,
    CargoUpdate,
)
from app.modules.maestros.models import Area, Beneficio, Cargo
from app.modules.maestros.repository import MaestroRepository
from app.modules.usuarios.models import Usuario
from app.modules.usuarios.repository import UsuarioRepository


MODULO_MAESTROS = "MAESTROS"


class MaestroServiceError(Exception):
    pass


class CargoNotFoundError(MaestroServiceError):
    pass


class AreaNotFoundError(MaestroServiceError):
    pass


class DuplicateCargoNameError(MaestroServiceError):
    pass


class DuplicateAreaNameError(MaestroServiceError):
    pass


class InvalidMaestroNameError(MaestroServiceError):
    pass


class BeneficioNotFoundError(MaestroServiceError):
    pass


class DuplicateBeneficioNameError(MaestroServiceError):
    pass


class BeneficioEnUsoError(MaestroServiceError):
    def __init__(self, *, nombres_eventos: list[str]) -> None:
        self.nombres_eventos = nombres_eventos
        super().__init__(
            "El beneficio está en la política de eventos abiertos: "
            + ", ".join(nombres_eventos)
        )


class MaestroService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.maestros = MaestroRepository(db)
        self.usuarios = UsuarioRepository(db)
        self.auditoria = AuditoriaRepository(db)

    async def crear_cargo(
        self, *, data: CargoCreate, actor: Usuario
    ) -> Cargo:
        nombre = self._normalize_name(data.nombre_cargo, entidad="cargo")
        if await self.maestros.get_cargo_by_nombre(nombre):
            raise DuplicateCargoNameError("El nombre del cargo ya existe.")

        try:
            cargo = await self.maestros.create_cargo(nombre_cargo=nombre)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="cargo",
                id_entidad=cargo.id_cargo,
                accion="CREAR_CARGO",
                valor_nuevo=self._cargo_values(cargo),
            )
            await self.db.commit()
            await self.db.refresh(cargo)
            return cargo
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateCargoNameError(
                "El nombre del cargo ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def obtener_cargo(self, id_cargo: int) -> Cargo:
        cargo = await self.maestros.get_cargo_by_id(id_cargo)
        if cargo is None:
            raise CargoNotFoundError("Cargo no encontrado.")
        return cargo

    async def listar_cargos(
        self,
        *,
        search: str | None,
        estado: bool | None,
        page: int,
        page_size: int,
    ) -> CargoListResponse:
        cargos, total = await self.maestros.list_cargos(
            search=search,
            estado=estado,
            page=page,
            page_size=page_size,
        )
        return CargoListResponse(
            items=[CargoResponse.model_validate(cargo) for cargo in cargos],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def actualizar_cargo(
        self, *, id_cargo: int, data: CargoUpdate, actor: Usuario
    ) -> Cargo:
        cargo = await self.obtener_cargo(id_cargo)
        nombre = self._normalize_name(data.nombre_cargo, entidad="cargo")
        if await self.maestros.get_cargo_by_nombre(
            nombre, exclude_id=id_cargo
        ):
            raise DuplicateCargoNameError("El nombre del cargo ya existe.")

        anterior = self._cargo_values(cargo)
        try:
            await self.maestros.update_cargo(cargo, nombre_cargo=nombre)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="cargo",
                id_entidad=cargo.id_cargo,
                accion="ACTUALIZAR_CARGO",
                valor_anterior=anterior,
                valor_nuevo=self._cargo_values(cargo),
            )
            await self.db.commit()
            await self.db.refresh(cargo)
            return cargo
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateCargoNameError(
                "El nombre del cargo ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def cambiar_estado_cargo(
        self, *, id_cargo: int, estado: bool, actor: Usuario
    ) -> Cargo:
        cargo = await self.obtener_cargo(id_cargo)
        anterior = self._cargo_values(cargo)
        accion = "REACTIVAR_CARGO" if estado else "INACTIVAR_CARGO"
        try:
            await self.maestros.set_cargo_estado(cargo, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="cargo",
                id_entidad=cargo.id_cargo,
                accion=accion,
                valor_anterior=anterior,
                valor_nuevo=self._cargo_values(cargo),
            )
            await self.db.commit()
            await self.db.refresh(cargo)
            return cargo
        except Exception:
            await self.db.rollback()
            raise

    async def crear_area(self, *, data: AreaCreate, actor: Usuario) -> Area:
        nombre = self._normalize_name(data.nombre_area, entidad="área")
        descripcion = self._normalize_description(data.descripcion)
        if await self.maestros.get_area_by_nombre(nombre):
            raise DuplicateAreaNameError("El nombre del área ya existe.")

        try:
            area = await self.maestros.create_area(
                nombre_area=nombre,
                descripcion=descripcion,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="area",
                id_entidad=area.id_area,
                accion="CREAR_AREA",
                valor_nuevo=self._area_values(area),
            )
            await self.db.commit()
            await self.db.refresh(area)
            return area
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateAreaNameError(
                "El nombre del área ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def obtener_area(self, id_area: int) -> Area:
        area = await self.maestros.get_area_by_id(id_area)
        if area is None:
            raise AreaNotFoundError("Área no encontrada.")
        return area

    async def listar_areas(
        self,
        *,
        search: str | None,
        estado: bool | None,
        page: int,
        page_size: int,
    ) -> AreaListResponse:
        areas, total = await self.maestros.list_areas(
            search=search,
            estado=estado,
            page=page,
            page_size=page_size,
        )
        return AreaListResponse(
            items=[AreaResponse.model_validate(area) for area in areas],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def actualizar_area(
        self, *, id_area: int, data: AreaUpdate, actor: Usuario
    ) -> Area:
        area = await self.obtener_area(id_area)
        nombre = self._normalize_name(data.nombre_area, entidad="área")
        descripcion = self._normalize_description(data.descripcion)
        if await self.maestros.get_area_by_nombre(
            nombre, exclude_id=id_area
        ):
            raise DuplicateAreaNameError("El nombre del área ya existe.")

        anterior = self._area_values(area)
        try:
            await self.maestros.update_area(
                area,
                nombre_area=nombre,
                descripcion=descripcion,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="area",
                id_entidad=area.id_area,
                accion="ACTUALIZAR_AREA",
                valor_anterior=anterior,
                valor_nuevo=self._area_values(area),
            )
            await self.db.commit()
            await self.db.refresh(area)
            return area
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateAreaNameError(
                "El nombre del área ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def cambiar_estado_area(
        self, *, id_area: int, estado: bool, actor: Usuario
    ) -> Area:
        area = await self.obtener_area(id_area)
        anterior = self._area_values(area)
        accion = "REACTIVAR_AREA" if estado else "INACTIVAR_AREA"
        try:
            await self.maestros.set_area_estado(area, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="area",
                id_entidad=area.id_area,
                accion=accion,
                valor_anterior=anterior,
                valor_nuevo=self._area_values(area),
            )
            await self.db.commit()
            await self.db.refresh(area)
            return area
        except Exception:
            await self.db.rollback()
            raise

    async def crear_beneficio(
        self, *, data: BeneficioCreate, actor: Usuario
    ) -> Beneficio:
        nombre = self._normalize_name(data.nombre, entidad="beneficio")
        condicion = self._normalize_description(data.condicion)
        if await self.maestros.get_beneficio_by_nombre(nombre):
            raise DuplicateBeneficioNameError("El nombre del beneficio ya existe.")

        try:
            beneficio = await self.maestros.create_beneficio(
                nombre=nombre,
                condicion=condicion,
                tipo_calculo=data.tipo_calculo,
                personas_por_asignacion=data.personas_por_asignacion,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="beneficio",
                id_entidad=beneficio.id_beneficio,
                accion="CREAR_BENEFICIO",
                valor_nuevo=self._beneficio_values(beneficio),
            )
            await self.db.commit()
            await self.db.refresh(beneficio)
            return beneficio
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateBeneficioNameError(
                "El nombre del beneficio ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def obtener_beneficio(self, id_beneficio: int) -> Beneficio:
        beneficio = await self.maestros.get_beneficio_by_id(id_beneficio)
        if beneficio is None:
            raise BeneficioNotFoundError("Beneficio no encontrado.")
        return beneficio

    async def listar_beneficios(
        self,
        *,
        search: str | None,
        estado: bool | None,
        page: int,
        page_size: int,
    ) -> BeneficioListResponse:
        beneficios, total = await self.maestros.list_beneficios(
            search=search,
            estado=estado,
            page=page,
            page_size=page_size,
        )
        return BeneficioListResponse(
            items=[
                BeneficioResponse.model_validate(beneficio)
                for beneficio in beneficios
            ],
            total=total,
            page=page,
            page_size=page_size,
            pages=math.ceil(total / page_size) if total else 0,
        )

    async def actualizar_beneficio(
        self, *, id_beneficio: int, data: BeneficioUpdate, actor: Usuario
    ) -> Beneficio:
        beneficio = await self.obtener_beneficio(id_beneficio)
        nombre = self._normalize_name(data.nombre, entidad="beneficio")
        condicion = self._normalize_description(data.condicion)
        if await self.maestros.get_beneficio_by_nombre(
            nombre, exclude_id=id_beneficio
        ):
            raise DuplicateBeneficioNameError("El nombre del beneficio ya existe.")

        anterior = self._beneficio_values(beneficio)
        try:
            await self.maestros.update_beneficio(
                beneficio,
                nombre=nombre,
                condicion=condicion,
                tipo_calculo=data.tipo_calculo,
                personas_por_asignacion=data.personas_por_asignacion,
            )
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="beneficio",
                id_entidad=beneficio.id_beneficio,
                accion="ACTUALIZAR_BENEFICIO",
                valor_anterior=anterior,
                valor_nuevo=self._beneficio_values(beneficio),
            )
            await self.db.commit()
            await self.db.refresh(beneficio)
            return beneficio
        except IntegrityError as exc:
            await self.db.rollback()
            raise DuplicateBeneficioNameError(
                "El nombre del beneficio ya existe."
            ) from exc
        except Exception:
            await self.db.rollback()
            raise

    async def cambiar_estado_beneficio(
        self, *, id_beneficio: int, estado: bool, actor: Usuario
    ) -> Beneficio:
        beneficio = await self.obtener_beneficio(id_beneficio)

        if not estado:
            eventos = await self.maestros.list_eventos_abiertos_usando_beneficio(
                id_beneficio
            )
            if eventos:
                raise BeneficioEnUsoError(
                    nombres_eventos=[evento.nombre_evento for evento in eventos]
                )

        anterior = self._beneficio_values(beneficio)
        accion = "REACTIVAR_BENEFICIO" if estado else "INACTIVAR_BENEFICIO"
        try:
            await self.maestros.set_beneficio_estado(beneficio, estado=estado)
            await self.auditoria.create(
                id_usuario=actor.id_usuario,
                id_modulo=await self._id_modulo(),
                entidad="beneficio",
                id_entidad=beneficio.id_beneficio,
                accion=accion,
                valor_anterior=anterior,
                valor_nuevo=self._beneficio_values(beneficio),
            )
            await self.db.commit()
            await self.db.refresh(beneficio)
            return beneficio
        except Exception:
            await self.db.rollback()
            raise

    async def _id_modulo(self) -> int | None:
        modulo = await self.usuarios.get_module_by_name(MODULO_MAESTROS)
        return modulo.id_modulo if modulo else None

    @staticmethod
    def _normalize_name(value: str, *, entidad: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise InvalidMaestroNameError(
                f"El nombre del {entidad} es obligatorio."
            )
        return normalized

    @staticmethod
    def _normalize_description(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @staticmethod
    def _cargo_values(cargo: Cargo) -> dict[str, object]:
        return {
            "id_cargo": cargo.id_cargo,
            "nombre_cargo": cargo.nombre_cargo,
            "estado": cargo.estado,
        }

    @staticmethod
    def _area_values(area: Area) -> dict[str, object]:
        return {
            "id_area": area.id_area,
            "nombre_area": area.nombre_area,
            "descripcion": area.descripcion,
            "estado": area.estado,
        }

    @staticmethod
    def _beneficio_values(beneficio: Beneficio) -> dict[str, object]:
        return {
            "id_beneficio": beneficio.id_beneficio,
            "nombre": beneficio.nombre,
            "condicion": beneficio.condicion,
            "tipo_calculo": beneficio.tipo_calculo.value,
            "personas_por_asignacion": beneficio.personas_por_asignacion,
            "estado": beneficio.estado,
        }
