from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.comunicaciones.models import (
    CorreoConfiguracionGlobal,
    CorreoEnvio,
    CorreoPlantilla,
    CorreoPlantillaHistorial,
)
from app.modules.comunicaciones.template_catalog import CODIGO_GLOBAL
from app.modules.usuarios.models import Usuario


class ComunicacionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_plantillas(self) -> list[CorreoPlantilla]:
        result = await self.db.scalars(
            select(CorreoPlantilla).order_by(
                CorreoPlantilla.nombre, CorreoPlantilla.id_plantilla
            )
        )
        return list(result.all())

    async def get_plantilla_by_codigo(self, codigo: str) -> CorreoPlantilla | None:
        return await self.db.scalar(
            select(CorreoPlantilla).where(CorreoPlantilla.codigo == codigo)
        )

    async def update_plantilla(
        self,
        plantilla: CorreoPlantilla,
        *,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str,
        estado: bool,
        version: int,
        actualizado_por: int,
    ) -> CorreoPlantilla:
        plantilla.asunto = asunto
        plantilla.cuerpo_html = cuerpo_html
        plantilla.cuerpo_texto = cuerpo_texto
        plantilla.estado = estado
        plantilla.version_actual = version
        plantilla.actualizado_por = actualizado_por
        await self.db.flush()
        return plantilla

    async def create_historial(
        self,
        *,
        plantilla: CorreoPlantilla,
        version: int,
        asunto: str,
        cuerpo_html: str,
        cuerpo_texto: str,
        motivo: str,
        creado_por: int,
    ) -> CorreoPlantillaHistorial:
        historial = CorreoPlantillaHistorial(
            id_plantilla=plantilla.id_plantilla,
            version=version,
            asunto=asunto,
            cuerpo_html=cuerpo_html,
            cuerpo_texto=cuerpo_texto,
            motivo=motivo,
            creado_por=creado_por,
        )
        self.db.add(historial)
        await self.db.flush()
        return historial

    async def list_historial(
        self, id_plantilla: int
    ) -> list[CorreoPlantillaHistorial]:
        result = await self.db.scalars(
            select(CorreoPlantillaHistorial)
            .where(CorreoPlantillaHistorial.id_plantilla == id_plantilla)
            .order_by(CorreoPlantillaHistorial.version.desc())
        )
        return list(result.all())

    async def get_historial_version(
        self, *, id_plantilla: int, version: int
    ) -> CorreoPlantillaHistorial | None:
        return await self.db.scalar(
            select(CorreoPlantillaHistorial).where(
                CorreoPlantillaHistorial.id_plantilla == id_plantilla,
                CorreoPlantillaHistorial.version == version,
            )
        )

    async def get_configuracion_global(self) -> CorreoConfiguracionGlobal | None:
        return await self.db.scalar(
            select(CorreoConfiguracionGlobal).where(
                CorreoConfiguracionGlobal.codigo == CODIGO_GLOBAL
            )
        )

    async def upsert_configuracion_global(
        self,
        *,
        id_usuario_emisor: int,
        nombre_remitente: str,
        reply_to: str | None,
        estado: bool,
        actualizado_por: int,
    ) -> CorreoConfiguracionGlobal:
        configuracion = await self.get_configuracion_global()
        if configuracion is None:
            configuracion = CorreoConfiguracionGlobal(
                codigo=CODIGO_GLOBAL,
                id_usuario_emisor=id_usuario_emisor,
                nombre_remitente=nombre_remitente,
                reply_to=reply_to,
                estado=estado,
                actualizado_por=actualizado_por,
            )
            self.db.add(configuracion)
        else:
            configuracion.id_usuario_emisor = id_usuario_emisor
            configuracion.nombre_remitente = nombre_remitente
            configuracion.reply_to = reply_to
            configuracion.estado = estado
            configuracion.actualizado_por = actualizado_por
        await self.db.flush()
        return configuracion

    async def get_usuario(self, id_usuario: int) -> Usuario | None:
        return await self.db.get(Usuario, id_usuario)

    async def create_envio(
        self,
        *,
        plantilla: CorreoPlantilla | None,
        id_usuario_emisor: int | None,
        destinatario: str,
        asunto: str,
        entidad_origen: str | None,
        entidad_id: int | str | None,
        estado: str,
        error_detalle: str | None = None,
    ) -> CorreoEnvio:
        envio = CorreoEnvio(
            id_plantilla=plantilla.id_plantilla if plantilla else None,
            version_plantilla=plantilla.version_actual if plantilla else None,
            id_usuario_emisor=id_usuario_emisor,
            destinatario=destinatario,
            asunto=asunto,
            entidad_origen=entidad_origen,
            entidad_id=str(entidad_id) if entidad_id is not None else None,
            estado=estado,
            intentos=1,
            error_detalle=error_detalle,
            enviado_en=datetime.now(UTC) if estado == "ENVIADO" else None,
        )
        self.db.add(envio)
        await self.db.flush()
        return envio
