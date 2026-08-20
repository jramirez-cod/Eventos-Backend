from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.maestros.models import Area, Cargo


class MaestroRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_cargo_by_id(self, id_cargo: int) -> Cargo | None:
        return await self.db.get(Cargo, id_cargo)

    async def get_cargo_by_nombre(
        self, nombre_cargo: str, *, exclude_id: int | None = None
    ) -> Cargo | None:
        stmt = select(Cargo).where(
            func.lower(Cargo.nombre_cargo) == nombre_cargo.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(Cargo.id_cargo != exclude_id)
        return await self.db.scalar(stmt)

    async def list_cargos(
        self,
        *,
        search: str | None,
        estado: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Cargo], int]:
        filters = []
        if search:
            filters.append(Cargo.nombre_cargo.ilike(f"%{search.strip()}%"))
        if estado is not None:
            filters.append(Cargo.estado.is_(estado))

        total = int(
            await self.db.scalar(
                select(func.count()).select_from(Cargo).where(*filters)
            )
            or 0
        )
        stmt = (
            select(Cargo)
            .where(*filters)
            .order_by(Cargo.nombre_cargo, Cargo.id_cargo)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.db.scalars(stmt)).all()), total

    async def create_cargo(self, *, nombre_cargo: str) -> Cargo:
        cargo = Cargo(nombre_cargo=nombre_cargo, estado=True)
        self.db.add(cargo)
        await self.db.flush()
        return cargo

    async def update_cargo(self, cargo: Cargo, *, nombre_cargo: str) -> Cargo:
        cargo.nombre_cargo = nombre_cargo
        await self.db.flush()
        return cargo

    async def set_cargo_estado(self, cargo: Cargo, *, estado: bool) -> Cargo:
        cargo.estado = estado
        await self.db.flush()
        return cargo

    async def get_area_by_id(self, id_area: int) -> Area | None:
        return await self.db.get(Area, id_area)

    async def get_area_by_nombre(
        self, nombre_area: str, *, exclude_id: int | None = None
    ) -> Area | None:
        stmt = select(Area).where(
            func.lower(Area.nombre_area) == nombre_area.lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(Area.id_area != exclude_id)
        return await self.db.scalar(stmt)

    async def list_areas(
        self,
        *,
        search: str | None,
        estado: bool | None,
        page: int,
        page_size: int,
    ) -> tuple[list[Area], int]:
        filters = []
        if search:
            filters.append(Area.nombre_area.ilike(f"%{search.strip()}%"))
        if estado is not None:
            filters.append(Area.estado.is_(estado))

        total = int(
            await self.db.scalar(
                select(func.count()).select_from(Area).where(*filters)
            )
            or 0
        )
        stmt = (
            select(Area)
            .where(*filters)
            .order_by(Area.nombre_area, Area.id_area)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list((await self.db.scalars(stmt)).all()), total

    async def create_area(
        self, *, nombre_area: str, descripcion: str | None
    ) -> Area:
        area = Area(
            nombre_area=nombre_area,
            descripcion=descripcion,
            estado=True,
        )
        self.db.add(area)
        await self.db.flush()
        return area

    async def update_area(
        self,
        area: Area,
        *,
        nombre_area: str,
        descripcion: str | None,
    ) -> Area:
        area.nombre_area = nombre_area
        area.descripcion = descripcion
        await self.db.flush()
        return area

    async def set_area_estado(self, area: Area, *, estado: bool) -> Area:
        area.estado = estado
        await self.db.flush()
        return area
