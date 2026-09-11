# Módulo Comunicaciones

Este documento explica la configuración, edición, versionado y envío de correos
del **Sistema Eventos CODIP**.

## Alcance actual

Comunicaciones administra un remitente global y cuatro plantillas globales:

| Código estable | Objetivo | Lo dispara |
| --- | --- | --- |
| `PRIMER_INGRESO` | Verificar el primer acceso antes de cambiar la contraseña temporal | Login de un usuario con `debe_cambiar_password=true` |
| `RECUPERACION_PASSWORD` | Restablecer una contraseña olvidada | Solicitud pública de recuperación |
| `QR_PARTICIPANTE` | Entregar la credencial QR de ingreso | Operación individual o masiva de Participantes |
| `ACCESO_EMPRESA` | Permitir al contacto principal gestionar participantes | Reenvío individual o masivo del código de empresa |

Las plantillas son globales. Todavía no existen variantes por empresa, evento,
idioma ni marca.

## Arquitectura

```text
Endpoint administrativo
  -> router.py
  -> ComunicacionService
  -> ComunicacionRepository
  -> SQLAlchemy async
  -> PostgreSQL

Auth / Participantes
  -> CorreoDeliveryService
  -> plantilla activa en PostgreSQL
  -> render Jinja controlado
  -> SMTPEmailSender
  -> servidor SMTP
```

Archivos:

```text
app/modules/comunicaciones/
├── __init__.py
├── dto.py
├── email_service.py
├── models.py
├── repository.py
├── router.py
├── seed.py
├── service.py
├── template_catalog.py
├── template_renderer.py
└── templates/
    ├── codigo_acceso_principal.html
    ├── initial_password_code.html
    ├── participante_qr.html
    └── password_recovery_code.html
```

`email_service.py` conserva los DTO internos y wrappers anteriores para
compatibilidad. Los flujos normales de Auth y Participantes usan
`CorreoDeliveryService`, que consulta PostgreSQL.

## Modelo de datos

### `correo_configuracion_global`

Existe una sola fila lógica con `codigo=GLOBAL`.

Campos principales:

- `id_usuario_emisor`: FK hacia `usuario`;
- `nombre_remitente`: nombre visible del From;
- `reply_to`: respuesta opcional;
- `estado`: habilita o bloquea la configuración;
- `actualizado_por`, `creado_en`, `actualizado_en`.

El correo SMTP se obtiene en tiempo de ejecución desde
`usuario.correo`. El usuario debe existir, estar activo y tener correo.

### `correo_plantilla`

Guarda la versión vigente:

- código técnico inmutable;
- nombre descriptivo;
- asunto editable;
- cuerpo HTML editable;
- cuerpo de texto editable;
- variables permitidas;
- versión actual;
- estado activo/inactivo;
- usuario y fechas de actualización.

No se usa el asunto como llave porque puede cambiar. El frontend siempre debe
identificar una plantilla por su `codigo`.

### `correo_plantilla_historial`

Guarda una instantánea completa por versión. Cada edición o restauración crea
una versión nueva; nunca se reescribe una versión anterior.

Restaurar la versión 1 cuando la actual es 4 produce la versión 5 con el
contenido de la versión 1. Esto conserva una línea de tiempo auditable.

### `correo_envio`

Registra metadatos operativos:

- plantilla y versión utilizada;
- usuario emisor;
- destinatario;
- asunto renderizado;
- entidad de origen opcional;
- estado `ENVIADO` o `FALLIDO`;
- error sanitizado y fechas.

No guarda cuerpos renderizados, contraseñas, códigos, tokens ni hashes.

## Secreto SMTP

El app password no se guarda en PostgreSQL ni se expone por API. Permanece en
el entorno:

```env
EMAIL_ENABLED=true
EMAIL_PRINT_CODE_TO_CONSOLE=false
EMAIL_SENDER_USER_ID=1
EMAIL_FROM_NAME=Sistema Eventos CODIP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_TIMEOUT_SECONDS=20
SMTP_APP_PASSWORD=app-password-del-entorno
```

`EMAIL_SENDER_USER_ID` se utiliza como preferencia al crear por primera vez la
configuración global. Después, la FK guardada en PostgreSQL es la fuente de
verdad del remitente. Si el ID configurado no existe durante el bootstrap, se
utiliza el administrador encontrado o creado.

## Instalación

En una base vacía de desarrollo/test:

```bash
.venv/bin/python scripts/create_db.py
```

Esto:

1. registra los models de Comunicaciones;
2. crea las cuatro tablas con `Base.metadata.create_all()`;
3. inserta las cuatro plantillas y su versión 1;
4. no sobrescribe plantillas existentes al volver a ejecutarse.

Luego:

```bash
.venv/bin/python scripts/bootstrap_security.py
```

El bootstrap crea de forma idempotente:

- módulo RBAC `COMUNICACIONES`;
- cinco permisos administrativos;
- relaciones de permisos para `ADMINISTRADOR_EVENTOS`;
- configuración `GLOBAL` enlazada al usuario emisor.

No se otorgan estos permisos a `PERSONAL_EVENTOS`.

En una BD poblada, `create_all()` solo crea tablas ausentes. No modifica
columnas existentes ni sustituye una herramienta formal de migraciones.

## Permisos

| Permiso | Uso |
| --- | --- |
| `CONSULTAR_PLANTILLA_CORREO` | Listar, leer, previsualizar e historial |
| `GESTIONAR_PLANTILLA_CORREO` | Editar contenido, asunto y estado |
| `RESTAURAR_PLANTILLA_CORREO` | Restaurar una versión histórica |
| `ENVIAR_CORREO_PRUEBA` | Enviar una prueba a un destinatario controlado |
| `CONFIGURAR_CORREO_GLOBAL` | Cambiar remitente, Reply-To y estado global |

Todos los endpoints validan JWT, existencia/estado actual del usuario y RBAC.

## Endpoints administrativos

Base: `/api/v1/comunicaciones`.

| Método | Ruta | Descripción |
| --- | --- | --- |
| `GET` | `/plantillas` | Lista las cuatro plantillas |
| `GET` | `/plantillas/{codigo}` | Devuelve contenido y versión vigente |
| `PUT` | `/plantillas/{codigo}` | Crea una versión nueva |
| `POST` | `/plantillas/{codigo}/previsualizar` | Renderiza sin persistir |
| `GET` | `/plantillas/{codigo}/historial` | Lista versiones |
| `POST` | `/plantillas/{codigo}/restaurar/{version}` | Restaura como versión nueva |
| `GET` | `/configuracion-global` | Consulta remitente global |
| `PUT` | `/configuracion-global` | Actualiza remitente global |
| `POST` | `/plantillas/{codigo}/enviar-prueba` | Envía prueba por SMTP |

No existe un endpoint genérico para enviar un correo arbitrario. Los envíos
reales siguen naciendo de Auth o Participantes, donde se aplican las reglas de
negocio y se generan códigos/tokens.

## Uso desde Swagger

1. Ejecute login en `/api/v1/auth/login`.
2. Pulse **Authorize** y registre el access token.
3. Ejecute `GET /api/v1/comunicaciones/plantillas`.
4. Use el `codigo` de la plantilla que desea administrar.
5. Lea primero el detalle para obtener `version_actual`.
6. Previsualice antes de guardar.
7. Envíe una prueba únicamente después de revisar el resultado.

### Consultar una plantilla

```http
GET /api/v1/comunicaciones/plantillas/PRIMER_INGRESO
Authorization: Bearer <access_token>
```

Respuesta resumida:

```json
{
  "id_plantilla": 1,
  "codigo": "PRIMER_INGRESO",
  "nombre": "Primer ingreso",
  "asunto": "Código de verificación para configurar tu acceso | Sistema Eventos CODIP",
  "cuerpo_html": "<html>...</html>",
  "cuerpo_texto": "Hola, {{ recipient_name }}...",
  "variables_permitidas": ["recipient_name", "code", "expires_minutes"],
  "version_actual": 1,
  "estado": true
}
```

### Previsualizar

```http
POST /api/v1/comunicaciones/plantillas/PRIMER_INGRESO/previsualizar
```

```json
{
  "contexto": {
    "recipient_name": "Dylan Codip",
    "code": "482913",
    "expires_minutes": 10
  }
}
```

Puede incluir `asunto`, `cuerpo_html` y `cuerpo_texto` para previsualizar un
borrador que todavía no fue guardado.

### Actualizar

```http
PUT /api/v1/comunicaciones/plantillas/PRIMER_INGRESO
```

```json
{
  "asunto": "Configura tu acceso, {{ recipient_name }}",
  "cuerpo_html": "<html><body><p>Tu código es <strong>{{ code }}</strong>.</p><p>Vence en {{ expires_minutes }} minutos.</p></body></html>",
  "cuerpo_texto": "Tu código es {{ code }}. Vence en {{ expires_minutes }} minutos.",
  "estado": true,
  "version_esperada": 1,
  "motivo": "Actualización de identidad corporativa"
}
```

`version_esperada` implementa control optimista. Si otra persona guardó antes,
el API devuelve `409` y el frontend debe recargar; no debe reenviar el cambio a
ciegas.

### Restaurar

```http
POST /api/v1/comunicaciones/plantillas/PRIMER_INGRESO/restaurar/1
```

```json
{
  "version_esperada": 4,
  "motivo": "Restaurar diseño aprobado"
}
```

### Configurar remitente

```http
PUT /api/v1/comunicaciones/configuracion-global
```

```json
{
  "id_usuario_emisor": 1,
  "nombre_remitente": "Sistema Eventos CODIP",
  "reply_to": "soporte@codip.pe",
  "estado": true
}
```

La respuesta expone el correo del usuario emisor, nunca el app password.

### Enviar prueba

```http
POST /api/v1/comunicaciones/plantillas/PRIMER_INGRESO/enviar-prueba
```

```json
{
  "destinatario": "qa@codip.pe",
  "contexto": {
    "recipient_name": "Equipo QA",
    "code": "000000",
    "expires_minutes": 10
  }
}
```

Requiere `EMAIL_ENABLED=true` y SMTP válido. Un fallo del proveedor responde
`502`; configuración inválida responde `400`.

## Variables permitidas

Los nombres deben escribirse exactamente como aparecen:

### `PRIMER_INGRESO`

```text
{{ recipient_name }}
{{ code }}
{{ expires_minutes }}
```

### `RECUPERACION_PASSWORD`

```text
{{ recipient_name }}
{{ code }}
{{ expires_minutes }}
```

### `QR_PARTICIPANTE`

```text
{{ recipient_name }}
```

La imagen se inserta como recurso MIME con CID fijo `qr_image`:

```html
<img src="cid:qr_image" alt="Código QR">
```

El frontend no envía la imagen ni el código seguro al editar la plantilla.

### `ACCESO_EMPRESA`

```text
{{ recipient_name }}
{{ nombre_empresa }}
{{ codigo }}
{{ portal_url }}
```

## Reglas de seguridad de plantillas

- Jinja usa `SandboxedEnvironment`, `StrictUndefined` y autoescape.
- Solo se admiten expresiones `{{ variable }}`.
- Se rechazan bloques `{% ... %}` e includes/imports.
- Se rechazan variables fuera de la allowlist de la plantilla.
- Se rechazan `script`, `iframe`, formularios, objetos y recursos activos.
- Se rechazan atributos `on*`, URL `javascript:` y CSS `expression()`.
- El asunto no puede contener CR/LF para impedir inyección de cabeceras.
- Un contexto incompleto o con variables desconocidas no se renderiza.
- El API nunca devuelve ni actualiza `SMTP_APP_PASSWORD`.

El editor del frontend debe tratar `cuerpo_html` como contenido no confiable.
Para la vista previa en navegador use un iframe aislado/sandboxed; no inserte el
HTML directamente en la aplicación mediante bypasses de sanitización.

## Flujos automáticos

### Primer ingreso

```text
POST /api/v1/auth/login con usuario + DNI temporal
  -> Auth valida credenciales y debe_cambiar_password
  -> genera JWT password_change + código de un uso
  -> guarda solamente hash y expiración
  -> CorreoDeliveryService carga PRIMER_INGRESO
  -> resuelve el usuario emisor global
  -> renderiza y envía al usuario.correo
  -> frontend solicita código y nueva contraseña
```

### Recuperación

```text
POST /api/v1/auth/recuperar-password
  -> respuesta genérica exista o no la cuenta
  -> para usuario activo genera código y hash
  -> carga RECUPERACION_PASSWORD
  -> envía al usuario.correo
```

### Acceso de empresa

```text
Participantes genera código y HMAC
  -> carga ACCESO_EMPRESA
  -> envía al correo del contacto principal
  -> incluye nombre_empresa y portal_url
```

### QR

```text
Participantes obtiene/genera codigo_seguro
  -> carga QR_PARTICIPANTE
  -> genera PNG QR en memoria
  -> adjunta imagen inline como cid:qr_image
  -> envía al correo del contacto/invitado
```

Comunicaciones entrega datos; no genera ni valida códigos de seguridad.

## Consola de desarrollo

Con:

```env
EMAIL_ENABLED=false
EMAIL_PRINT_CODE_TO_CONSOLE=true
```

los códigos se muestran en consola sin contactar SMTP. Nunca habilite esta
opción en producción porque expone credenciales de un solo uso en logs.

## Errores esperados

| Código | Caso |
| --- | --- |
| `400` | HTML/variables inválidas, emisor inválido o SMTP deshabilitado para prueba |
| `401` | Sin token o token inválido |
| `403` | Usuario sin permiso |
| `404` | Plantilla, versión o configuración inexistente |
| `409` | `version_esperada` obsoleta |
| `422` | DTO estructuralmente inválido |
| `502` | El proveedor SMTP no pudo entregar el correo de prueba |

## Tests

```bash
.venv/bin/python -m pytest test/modules/comunicaciones -q
.venv/bin/python -m pytest test/modules/usuarios -q
.venv/bin/python -m pytest test/modules/participantes -q
.venv/bin/python -m pytest -q
```

La cobertura específica incluye:

- registro de las cuatro plantillas;
- autenticación y RBAC;
- lectura y detalle;
- edición y auditoría;
- control optimista;
- historial y restauración;
- preview sin persistencia;
- allowlist Jinja y rechazo de HTML activo;
- configuración global;
- envío de prueba y registro sin secretos;
- idempotencia de `create_db.py` y bootstrap.

## Extensión futura

Para agregar un quinto tipo de correo:

1. agregue un código estable en `template_catalog.py`;
2. declare su allowlist y plantilla inicial;
3. agregue un método semántico en `CorreoDeliveryService`;
4. invoque ese método desde el service dueño de la regla de negocio;
5. agregue tests de render, entrega y datos sensibles;
6. ejecute `create_db.py` o un proceso de migración/seed controlado.

No agregue endpoints que acepten destinatario, asunto y HTML arbitrarios para
envío masivo. Las campañas, colas, reintentos y variantes por empresa requieren
un alcance propio y controles adicionales.
