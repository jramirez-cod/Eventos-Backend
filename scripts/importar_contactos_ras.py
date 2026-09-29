"""Importa contactos desde el Excel "RAS 29.09" y agrega participantes.

Lee scripts/data/import_ras_2909.json: 719 registros ya depurados a mano
junto al usuario (grupos EXPOSITOR/INVITADO/CODIP/AUSPICIADOR excluidos,
empresas ya emparejadas contra la base real, duplicados internos del
Excel fusionados).

Para cada registro:
- Si ya existe un contacto con el mismo nombre + apellido en esa empresa,
  se reutiliza (no se duplica).
- Si no existe, se crea: genero="OTRO" (el Excel no trae ese dato, decision
  explicita del usuario), alias = "Nombres Apellidos", correo/celular en
  NULL si faltan o tienen formato invalido.

Despues, para los marcados "confirmado_si" (columna Confirmacion = "Si"),
afilia su empresa a la programacion indicada (si no lo estaba ya) y los
agrega como participantes de esa programacion.

Seguro de correr mas de una vez: contactos, afiliaciones y participantes
que ya existen se detectan y se omiten en vez de duplicarse.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import re
import sys

from pydantic import ValidationError
from sqlalchemy import func, select

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db.session import AsyncSessionLocal  # noqa: E402
from app.modules.contactos.dto import ContactoCreate  # noqa: E402
from app.modules.contactos.models import Contacto  # noqa: E402
from app.modules.contactos.service import (  # noqa: E402
    ContactoService,
    ContactoServiceError,
)
from app.modules.eventos.models import ProgramacionEvento  # noqa: E402
from app.modules.participantes.dto import EventoContactoCreateMultiple  # noqa: E402
from app.modules.participantes.models import EventoContacto  # noqa: E402
from app.modules.participantes.service import (  # noqa: E402
    DuplicateEventoContactoError,
    DuplicateEventoEmpresaError,
    ParticipanteService,
    ParticipanteServiceError,
)
from app.modules.usuarios.models import Rol, Usuario  # noqa: E402

DATA_PATH = ROOT / "scripts" / "data" / "import_ras_2909.json"
CELULAR_RE = re.compile(r"9\d{8}|\+[1-9]\d{9,14}")
CORREO_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


async def resolver_actor(session) -> Usuario:
    stmt = (
        select(Usuario)
        .join(Rol, Rol.id_rol == Usuario.id_rol)
        .where(Usuario.estado.is_(True), Rol.nombre_rol.ilike("%admin%"))
        .order_by(Usuario.id_usuario)
        .limit(1)
    )
    actor = await session.scalar(stmt)
    if actor is None:
        actor = await session.scalar(
            select(Usuario)
            .where(Usuario.estado.is_(True))
            .order_by(Usuario.id_usuario)
            .limit(1)
        )
    if actor is None:
        raise RuntimeError("No hay ningun usuario activo en la base.")
    return actor


async def buscar_contacto_existente(
    session, *, id_empresa: int, nombres: str, apellidos: str
) -> Contacto | None:
    stmt = select(Contacto).where(
        Contacto.id_empresa == id_empresa,
        func.upper(Contacto.nombres) == nombres.upper(),
        func.upper(Contacto.apellidos) == apellidos.upper(),
    )
    return await session.scalar(stmt)


async def importar_contactos(
    session, registros: list[dict], actor: Usuario
) -> tuple[dict[tuple[int, str, str], int], dict[str, int]]:
    mapa_contactos: dict[tuple[int, str, str], int] = {}
    stats = {"creados": 0, "ya_existian": 0, "errores": 0}

    for r in registros:
        id_empresa = r["id_empresa"]
        nombres = r["nombres"]
        apellidos = r["apellidos"]
        clave = (id_empresa, nombres.upper(), apellidos.upper())

        existente = await buscar_contacto_existente(
            session, id_empresa=id_empresa, nombres=nombres, apellidos=apellidos
        )
        if existente is not None:
            mapa_contactos[clave] = existente.id_contacto
            stats["ya_existian"] += 1
            continue

        correo = r.get("correo")
        if correo and not CORREO_RE.match(correo):
            print(f"  [correo invalido, se guarda NULL] {nombres} {apellidos}: '{correo}'")
            correo = None

        celular = r.get("celular")
        if celular and not CELULAR_RE.fullmatch(celular):
            print(f"  [celular invalido, se guarda NULL] {nombres} {apellidos}: '{celular}'")
            celular = None

        try:
            data = ContactoCreate(
                id_empresa=id_empresa,
                nombres=nombres,
                apellidos=apellidos,
                genero="OTRO",
                celular=celular,
                correo=correo,
                alias=r["alias"],
            )
        except ValidationError as exc:
            print(f"  [ERROR validacion] {nombres} {apellidos} (empresa {id_empresa}): {exc}")
            stats["errores"] += 1
            continue

        try:
            creado = await ContactoService(session).crear_contacto(
                data=data, actor=actor
            )
        except ContactoServiceError as exc:
            print(f"  [ERROR al crear] {nombres} {apellidos} (empresa {id_empresa}): {exc}")
            stats["errores"] += 1
            continue

        mapa_contactos[clave] = creado.id_contacto
        stats["creados"] += 1

    return mapa_contactos, stats


async def agregar_participantes(
    session,
    *,
    id_programacion_evento: int,
    confirmados: list[dict],
    mapa_contactos: dict[tuple[int, str, str], int],
    actor: Usuario,
) -> dict[str, int]:
    stats = {
        "empresas_afiliadas": 0,
        "empresas_ya_afiliadas": 0,
        "participantes_agregados": 0,
        "participantes_ya_existian": 0,
        "sin_contacto": 0,
    }

    participante_service = ParticipanteService(session)

    empresas = sorted({r["id_empresa"] for r in confirmados})
    for id_empresa in empresas:
        try:
            await participante_service.afiliar_empresa_evento(
                id_programacion_evento=id_programacion_evento,
                id_empresa=id_empresa,
                actor=actor,
            )
            stats["empresas_afiliadas"] += 1
        except DuplicateEventoEmpresaError:
            stats["empresas_ya_afiliadas"] += 1
        except ParticipanteServiceError as exc:
            print(f"  [ERROR al afiliar empresa {id_empresa}] {exc}")

    ya_agregados = set(
        await session.scalars(
            select(EventoContacto.id_contacto).where(
                EventoContacto.id_programacion_evento == id_programacion_evento
            )
        )
    )

    ids_nuevos: list[int] = []
    for r in confirmados:
        clave = (r["id_empresa"], r["nombres"].upper(), r["apellidos"].upper())
        id_contacto = mapa_contactos.get(clave)
        if id_contacto is None:
            print(f"  [sin contacto resuelto] {r['nombres']} {r['apellidos']}")
            stats["sin_contacto"] += 1
            continue
        if id_contacto in ya_agregados:
            stats["participantes_ya_existian"] += 1
            continue
        ids_nuevos.append(id_contacto)

    if ids_nuevos:
        try:
            resultado = await participante_service.agregar_evento_contactos(
                id_programacion_evento=id_programacion_evento,
                data=EventoContactoCreateMultiple(ids_contacto=ids_nuevos),
                actor=actor,
            )
            stats["participantes_agregados"] = resultado.created
        except DuplicateEventoContactoError as exc:
            print(f"  [ERROR duplicado al agregar participantes] {exc}")
        except ParticipanteServiceError as exc:
            print(f"  [ERROR al agregar participantes] {exc}")

    return stats


async def main(id_programacion_evento: int, data_path: Path) -> None:
    with open(data_path, encoding="utf-8") as f:
        registros = json.load(f)

    async with AsyncSessionLocal() as session:
        programacion = await session.get(ProgramacionEvento, id_programacion_evento)
        if programacion is None:
            raise RuntimeError(
                f"No existe la programacion {id_programacion_evento}."
            )

        actor = await resolver_actor(session)
        print(f"Actor para auditoria: {actor.nombre_usuario} (id={actor.id_usuario})\n")

        print("=== Importando contactos ===")
        mapa_contactos, stats_contactos = await importar_contactos(
            session, registros, actor
        )
        print(f"\nContactos creados: {stats_contactos['creados']}")
        print(f"Contactos ya existentes (reutilizados): {stats_contactos['ya_existian']}")
        print(f"Errores: {stats_contactos['errores']}")

        confirmados = [r for r in registros if r["confirmado_si"]]
        print(f"\n=== Agregando {len(confirmados)} participantes confirmados a la programacion {id_programacion_evento} ===")
        stats_part = await agregar_participantes(
            session,
            id_programacion_evento=id_programacion_evento,
            confirmados=confirmados,
            mapa_contactos=mapa_contactos,
            actor=actor,
        )
        print(f"\nEmpresas afiliadas de nuevo: {stats_part['empresas_afiliadas']}")
        print(f"Empresas ya afiliadas: {stats_part['empresas_ya_afiliadas']}")
        print(f"Participantes agregados: {stats_part['participantes_agregados']}")
        print(f"Participantes que ya existian: {stats_part['participantes_ya_existian']}")
        print(f"Sin contacto resuelto (revisar): {stats_part['sin_contacto']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--programacion",
        type=int,
        default=6,
        help="id_programacion_evento destino (default: 6, San Isidro 29/09).",
    )
    parser.add_argument(
        "--data",
        type=str,
        default=str(DATA_PATH),
        help="Ruta al JSON con los registros a importar (default: scripts/data/import_ras_2909.json).",
    )
    args = parser.parse_args()
    asyncio.run(main(args.programacion, Path(args.data)))
