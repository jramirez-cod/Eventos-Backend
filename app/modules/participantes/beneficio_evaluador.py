from dataclasses import dataclass
from typing import Protocol

from app.modules.maestros.models import TipoCalculoBeneficio


@dataclass(frozen=True, slots=True)
class AsignacionUso:
    id_asignacion_beneficio: int
    codigo_grupo: str | None
    asistencia_evento: bool


class EvaluadorBeneficio(Protocol):
    def contar_usados(self, filas: list[AsignacionUso]) -> int: ...


class EvaluadorPorEvento:
    """El cupo se resetea en cada ocurrencia: toda asignación cuenta, asista o no."""

    def contar_usados(self, filas: list[AsignacionUso]) -> int:
        return len(filas)


class EvaluadorPorAnio:
    """El cupo es un pool compartido dentro del rango de la política.

    Solo cuenta si la persona asistió de verdad. Las asignaciones agrupadas
    (codigo_grupo, p.ej. "entrada doble") cuentan todo o nada: solo se
    descuentan si TODOS los integrantes del grupo asistieron.
    """

    def contar_usados(self, filas: list[AsignacionUso]) -> int:
        grupos: dict[str, list[AsignacionUso]] = {}
        contadas = 0
        for fila in filas:
            if fila.codigo_grupo is None:
                if fila.asistencia_evento:
                    contadas += 1
                continue
            grupos.setdefault(fila.codigo_grupo, []).append(fila)
        for miembros in grupos.values():
            if all(miembro.asistencia_evento for miembro in miembros):
                contadas += len(miembros)
        return contadas


class EvaluadorSinBeneficio:
    """Valor de catálogo explícito: siempre disponible, nunca consume cupo."""

    def contar_usados(self, filas: list[AsignacionUso]) -> int:
        return 0


EVALUADORES: dict[TipoCalculoBeneficio, EvaluadorBeneficio] = {
    TipoCalculoBeneficio.POR_EVENTO: EvaluadorPorEvento(),
    TipoCalculoBeneficio.POR_ANIO: EvaluadorPorAnio(),
    TipoCalculoBeneficio.SIN_BENEFICIO: EvaluadorSinBeneficio(),
}


def calcular_cupo_restante(
    *,
    tipo_calculo: TipoCalculoBeneficio,
    entradas_gratuitas: int,
    personas_por_asignacion: int,
    filas_existentes: list[AsignacionUso],
) -> int | None:
    """`entradas_gratuitas` es la cantidad de cupos/asignaciones configuradas
    en la política (p.ej. "3" para un beneficio de entrada doble significa 3
    parejas). El cupo real en entradas individuales es ese valor multiplicado
    por `personas_por_asignacion`.
    """
    if tipo_calculo == TipoCalculoBeneficio.SIN_BENEFICIO:
        return None
    evaluador = EVALUADORES[tipo_calculo]
    usados = evaluador.contar_usados(filas_existentes)
    total_entradas = entradas_gratuitas * personas_por_asignacion
    return total_entradas - usados


def hay_cupo_disponible(
    *,
    tipo_calculo: TipoCalculoBeneficio,
    entradas_gratuitas: int,
    personas_por_asignacion: int,
    filas_existentes: list[AsignacionUso],
    cantidad_solicitada: int,
) -> bool:
    if tipo_calculo == TipoCalculoBeneficio.SIN_BENEFICIO:
        return True
    restante = calcular_cupo_restante(
        tipo_calculo=tipo_calculo,
        entradas_gratuitas=entradas_gratuitas,
        personas_por_asignacion=personas_por_asignacion,
        filas_existentes=filas_existentes,
    )
    assert restante is not None
    return restante >= cantidad_solicitada
