from dataclasses import dataclass
from pathlib import Path


CODIGO_GLOBAL = "GLOBAL"
PRIMER_INGRESO = "PRIMER_INGRESO"
RECUPERACION_PASSWORD = "RECUPERACION_PASSWORD"
QR_PARTICIPANTE = "QR_PARTICIPANTE"
ACCESO_EMPRESA = "ACCESO_EMPRESA"

TEMPLATE_DIRECTORY = Path(__file__).resolve().parent / "templates"


@dataclass(frozen=True, slots=True)
class PlantillaBase:
    codigo: str
    nombre: str
    asunto: str
    archivo_html: str
    cuerpo_texto: str
    variables_permitidas: tuple[str, ...]

    @property
    def cuerpo_html(self) -> str:
        return (TEMPLATE_DIRECTORY / self.archivo_html).read_text(encoding="utf-8")


PLANTILLAS_BASE: tuple[PlantillaBase, ...] = (
    PlantillaBase(
        codigo=PRIMER_INGRESO,
        nombre="Primer ingreso",
        asunto="Código de verificación para configurar tu acceso | Sistema Eventos CODIP",
        archivo_html="initial_password_code.html",
        cuerpo_texto=(
            "Hola, {{ recipient_name }}.\n\nTu código para configurar la contraseña "
            "del Sistema Eventos CODIP es: {{ code }}\n\nEl código vence en "
            "{{ expires_minutes }} minutos. Si no solicitaste esta operación, "
            "comunícate con el administrador del sistema."
        ),
        variables_permitidas=("recipient_name", "code", "expires_minutes"),
    ),
    PlantillaBase(
        codigo=RECUPERACION_PASSWORD,
        nombre="Recuperación de contraseña",
        asunto="Código de verificación para recuperar tu contraseña | Sistema Eventos CODIP",
        archivo_html="password_recovery_code.html",
        cuerpo_texto=(
            "Hola, {{ recipient_name }}.\n\nTu código para recuperar la contraseña "
            "del Sistema Eventos CODIP es: {{ code }}\n\nEl código vence en "
            "{{ expires_minutes }} minutos. Si no solicitaste esta operación, "
            "comunícate con el administrador del sistema."
        ),
        variables_permitidas=("recipient_name", "code", "expires_minutes"),
    ),
    PlantillaBase(
        codigo=QR_PARTICIPANTE,
        nombre="QR de participante",
        asunto="Tu código de ingreso al evento | Sistema Eventos CODIP",
        archivo_html="participante_qr.html",
        cuerpo_texto=(
            "Hola, {{ recipient_name }}.\n\nAdjuntamos tu código QR de ingreso al "
            "evento. Preséntalo impreso o desde tu celular en la entrada."
        ),
        variables_permitidas=("recipient_name",),
    ),
    PlantillaBase(
        codigo=ACCESO_EMPRESA,
        nombre="Acceso de empresa",
        asunto="Código de acceso para gestionar participantes | Sistema Eventos CODIP",
        archivo_html="codigo_acceso_principal.html",
        cuerpo_texto=(
            "Hola, {{ recipient_name }}.\n\nTe compartimos el código de acceso para "
            "gestionar participantes de {{ nombre_empresa }} en {{ nombre_evento }} "
            "({{ fecha_evento }}): {{ codigo }}\n\n"
            "Vence el {{ expira_en }}. Si recibiste varios correos, usa el más "
            "reciente: al generar un código nuevo el anterior deja de servir.\n\n"
            "Ingresa aquí: {{ portal_url }}"
        ),
        variables_permitidas=(
            "recipient_name",
            "nombre_empresa",
            "nombre_evento",
            "fecha_evento",
            "codigo",
            "expira_en",
            "portal_url",
        ),
    ),
)

PLANTILLAS_POR_CODIGO = {item.codigo: item for item in PLANTILLAS_BASE}

