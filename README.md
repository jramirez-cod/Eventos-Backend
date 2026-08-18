# Eventos-Backend

Backend FastAPI del **Sistema Eventos CODIP**.

La arquitectura del proyecto es un monolito modular sencillo:

```text
Router
  -> Service
  -> Repository
  -> SQLAlchemy
  -> PostgreSQL
```

## Instalación

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

## Variables de entorno principales

La aplicación lee variables desde `.env` mediante `pydantic-settings`.

```env
PGHOST=localhost
PGPORT=5432
PGDATABASE=eventos
PGUSER=postgres
PGPASSWORD=...

APP_NAME=Sistema Eventos API
APP_VERSION=1.0.0
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=false

SECRET_KEY=coloca-un-secreto-largo-y-seguro
JWT_ALGORITHM=HS256
JWT_ISSUER=eventos-codip-api
ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES=15
INITIAL_PASSWORD_CODE_EXPIRE_MINUTES=10
INITIAL_PASSWORD_CODE_LENGTH=6
TEMPORARY_DNI_LENGTH=8
RECOVERY_TOKEN_EXPIRE_MINUTES=30

PASSWORD_MIN_LENGTH=8
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_NUMBER=true
PASSWORD_REQUIRE_SPECIAL=true

EMAIL_ENABLED=false
EMAIL_PRINT_CODE_TO_CONSOLE=false
EMAIL_SENDER_USER_ID=1
EMAIL_FROM_NAME=Sistema Eventos CODIP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_APP_PASSWORD=...
```

`SECRET_KEY` es obligatorio para login, JWT, cambio de contraseña y recuperación. No debe subirse al repositorio.

`EMAIL_ENABLED` controla si se intenta un envío SMTP real (usando `SMTP_*` y el correo del usuario `EMAIL_SENDER_USER_ID` como remitente) tanto para el código de primer ingreso (HU-USR-002) como para el de recuperación de contraseña (HU-USR-003). `EMAIL_PRINT_CODE_TO_CONSOLE` es un flag independiente (no `APP_DEBUG`) que además imprime el código en la consola del servidor — útil en desarrollo cuando no hay SMTP configurado, o como respaldo si el envío real falla:

```env
EMAIL_PRINT_CODE_TO_CONSOLE=true
```

Con ese flag activo, un login con contraseña temporal o una solicitud de recuperación mostrará algo similar a:

```text
[DEV AUTH] Código de primer ingreso para a****@codip.pe: 482913
[DEV AUTH] Código de recuperación de contraseña para a****@codip.pe: 482913
```

Con `EMAIL_PRINT_CODE_TO_CONSOLE=false` (valor predeterminado y el requerido en producción), el código nunca se imprime. Tampoco se imprimen contraseñas, JWT ni hashes.

## Ejecutar FastAPI

```bash
.venv/bin/fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

Swagger queda disponible en:

```text
http://localhost:8000/docs
```

Healthcheck:

```text
GET /api/v1/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "api": "available"
}
```

## Módulo Acceso y Usuarios

Se implementaron estas historias:

```text
HU-USR-001 Iniciar sesión
HU-USR-002 Cambiar contraseña en primer ingreso
HU-USR-003 Recuperar contraseña
HU-USR-004 Crear usuario interno
HU-USR-005 Inactivar usuario
```

Archivos principales:

```text
app/core/security.py
app/modules/usuarios/models.py
app/modules/usuarios/dto.py
app/modules/usuarios/repository.py
app/modules/usuarios/auth_service.py
app/modules/usuarios/usuario_service.py
app/modules/usuarios/dependencies.py
app/modules/usuarios/auth_router.py
app/modules/usuarios/router.py
app/modules/auditoria/models.py
app/modules/auditoria/repository.py
app/modules/comunicaciones/email_service.py
app/modules/comunicaciones/templates/initial_password_code.html
app/modules/comunicaciones/templates/password_recovery_code.html
scripts/bootstrap_security.py
```

### Modelos SQLAlchemy

Los modelos representan tablas de PostgreSQL, no contratos HTTP.

`app/modules/usuarios/models.py`:

```text
Rol
TipoDocumento
Usuario
UsuarioTokenRecuperacion
Modulo
Permiso
RolPermisoModulo
```

Campos relevantes de `Usuario`:

```text
id_usuario
id_rol
id_tipo_documento
numero_documento
nombre_usuario
password_hash
nombres
apellidos
correo
estado
debe_cambiar_password
```

Campos relevantes de `TipoDocumento`:

```text
id_tipo_documento
nombre_documento
longitud
estado
```

Campos relevantes de `UsuarioTokenRecuperacion`:

```text
id_usuario_token
id_usuario
token_hash
expira_en
utilizado_en
creado_en
```

`app/modules/auditoria/models.py`:

```text
Auditoria
```

Audita creación de usuario, inactivación, cambio inicial y restablecimiento de contraseña. No guarda contraseñas, hashes ni tokens en texto plano.

### DTOs Pydantic

Los DTOs viven en `app/modules/usuarios/dto.py` y representan contratos HTTP.

```text
LoginRequestDTO
LoginResponseDTO
CambioPasswordInicialRequestDTO
RecuperarPasswordRequestDTO
RecuperarPasswordResponseDTO
RestablecerPasswordRequestDTO
UsuarioCreateDTO
UsuarioResponseDTO
TipoDocumentoResponseDTO
InactivarUsuarioDTO
MessageResponseDTO
```

No se expone:

```text
password_hash
token_hash
```

### Seguridad

`app/core/security.py` centraliza:

```text
hash_password()
verify_password()
validate_password_policy()
validate_document_number()
create_access_token()
decode_access_token()
create_password_change_token()
decode_password_change_token()
generate_initial_verification_code()
hash_initial_verification_code()
hash_recovery_code()
hash_recovery_token()
```

Los JWT diferencian tipos con el claim:

```text
token_type=access
token_type=password_change
```

Un token `password_change` no sirve para endpoints protegidos normales.

Un `access_token` incluye estos claims (además de `sub`, `iss`, `iat`, `exp`, `token_type`):

```text
id_usuario
id_rol
nombre_usuario
nombres
apellidos
correo
nombre_rol
```

`correo` y `nombre_rol` se agregaron para que el frontend pueda hidratar la sesión (dashboard, sidebar) sin depender de un endpoint adicional. Se resuelven con `usuario.rol.nombre_rol`, por lo que `UsuarioRepository.get_by_username()`/`get_by_email()` cargan la relación `rol` con `joinedload`.

Cada endpoint protegido usa `get_current_user()`, que valida en base de datos que el usuario todavía exista y siga activo. Si un usuario fue inactivado después de iniciar sesión, su JWT anterior queda rechazado.

## Bootstrap de seguridad inicial

HU-USR-004 requiere un usuario con permiso, por eso existe:

```text
scripts/bootstrap_security.py
```

El script es idempotente y prepara:

```text
roles básicos
tipo de documento DNI (longitud 8)
módulo USUARIOS
permisos CREAR_USUARIO e INACTIVAR_USUARIO
relaciones rol-permiso-módulo
primer Administrador de Eventos
```

Ejemplo:

```bash
SECRET_KEY='coloca-un-secreto-largo-y-seguro' \
BOOTSTRAP_ADMIN_USERNAME='admin' \
BOOTSTRAP_ADMIN_EMAIL='admin@codip.pe' \
BOOTSTRAP_ADMIN_PASSWORD='AdminSeguro1!' \
BOOTSTRAP_ADMIN_NOMBRES='Administrador' \
BOOTSTRAP_ADMIN_APELLIDOS='Eventos' \
BOOTSTRAP_ADMIN_DOCUMENTO='00000000' \
.venv/bin/python scripts/bootstrap_security.py
```

También se puede pasar parte de la información por argumentos:

```bash
.venv/bin/python scripts/bootstrap_security.py \
  --username admin \
  --email admin@codip.pe \
  --nombres Administrador \
  --apellidos Eventos
```

En ese caso la contraseña se toma de `BOOTSTRAP_ADMIN_PASSWORD` o se solicita por entrada segura.

Importante: el script no crea tablas ni modifica el esquema. Si faltan tablas requeridas, se detiene con un error claro.

## Probar endpoints desde Swagger

Abrir:

```text
http://localhost:8000/docs
```

### 1. Login normal

Endpoint:

```text
POST /api/v1/auth/login
```

JSON:

```json
{
  "nombre_usuario": "admin",
  "password": "AdminSeguro1!"
}
```

Respuesta satisfactoria cuando el usuario ya tiene contraseña definitiva:

```json
{
  "debe_cambiar_password": false,
  "token_type": "access",
  "access_token": "eyJ...",
  "password_change_token": null
}
```

En Swagger, copiar `access_token`, presionar **Authorize** y pegar:

```text
Bearer eyJ...
```

Swagger también permite autenticarse directamente desde el botón **Authorize**. Ese botón usa internamente:

```text
POST /api/v1/auth/token
```

Ese endpoint recibe formulario OAuth2 (`username` y `password`) y devuelve un Bearer token estándar para que Swagger lo conserve mientras la página esté abierta.

En **Authorize** llenar:

```text
username: admin
password: AdminSeguro1!
client_id: dejar vacío
client_secret: dejar vacío
```

Luego presionar **Authorize** y **Close**. Desde ese momento Swagger enviará automáticamente el header `Authorization: Bearer ...` en endpoints protegidos.

### 2. Login con contraseña temporal

Endpoint:

```text
POST /api/v1/auth/login
```

JSON:

```json
{
  "nombre_usuario": "mlopez",
  "password": "74859632"
}
```

Respuesta esperada si `debe_cambiar_password=true`:

```json
{
  "debe_cambiar_password": true,
  "token_type": "password_change",
  "access_token": null,
  "password_change_token": "eyJ...",
  "codigo_verificacion_requerido": true,
  "correo_enmascarado": "m*****@codip.pe"
}
```

El backend genera un código de seis dígitos y prepara su envío al correo registrado. En PostgreSQL guarda solamente el hash del código. El token recibido solo sirve para completar el cambio inicial.

### 3. Cambiar contraseña inicial

Endpoint:

```text
POST /api/v1/auth/cambiar-password-inicial
```

En el candado del propio endpoint, seleccionar `PasswordChangeBearer` y pegar únicamente:

```text
eyJ...password_change_token...
```

JSON:

```json
{
  "codigo_verificacion": "482913",
  "nueva_password": "NuevaPassword1!",
  "confirmar_password": "NuevaPassword1!"
}
```

Respuesta satisfactoria:

```json
{
  "debe_cambiar_password": false,
  "token_type": "access",
  "access_token": "eyJ...",
  "password_change_token": null,
  "codigo_verificacion_requerido": false,
  "correo_enmascarado": null
}
```

### 4. Solicitar recuperación de contraseña

Endpoint:

```text
POST /api/v1/auth/recuperar-password
```

JSON:

```json
{
  "correo": "mlopez@codip.pe"
}
```

Respuesta satisfactoria, exista o no exista el correo (mensaje idéntico en ambos casos, para no revelar qué correos tienen cuenta):

```json
{
  "message": "Si existe una cuenta asociada, se enviarán las instrucciones de recuperación."
}
```

Sigue la misma lógica que HU-USR-002: si el correo tiene una cuenta activa, se genera un código de 6 dígitos (`security.generate_initial_verification_code()`), se guarda su hash anclado al correo (`security.hash_recovery_code()`, no a un JWT, porque en este flujo el usuario todavía no probó ninguna credencial) y se envía por correo con `notify_password_recovery_code()` (plantilla `password_recovery_code.html`). Si el correo no existe o está inactivo, la función retorna sin generar ni enviar nada — confirmable revisando que no aparezcan filas nuevas en `usuario_token_recuperacion`.

Si el envío de correo falla (por ejemplo, SMTP no disponible) y no hay respaldo de consola habilitado, responde `503`.

### 5. Restablecer contraseña

Endpoint:

```text
POST /api/v1/auth/restablecer-password
```

JSON:

```json
{
  "correo": "mlopez@codip.pe",
  "codigo_verificacion": "482913",
  "nueva_password": "PasswordRecuperada1!",
  "confirmar_password": "PasswordRecuperada1!"
}
```

Respuesta satisfactoria:

```json
{
  "debe_cambiar_password": false,
  "token_type": "access",
  "access_token": "eyJ...",
  "password_change_token": null
}
```

No requiere header `Authorization`: el `correo` identifica al usuario y el `codigo_verificacion` se valida contra el hash guardado para ese correo. El código queda marcado como utilizado y no puede reutilizarse; expira según `RECOVERY_TOKEN_EXPIRE_MINUTES`.

### 6. Crear usuario interno

Endpoint:

```text
POST /api/v1/usuarios
```

Requiere `access_token` de un usuario con permiso:

```text
USUARIOS / CREAR_USUARIO
```

En Swagger, presionar **Authorize** y pegar:

```text
Bearer eyJ...access_token...
```

JSON:

```json
{
  "id_rol": 2,
  "id_tipo_documento": 1,
  "numero_documento": "74859632",
  "nombre_usuario": "mlopez",
  "nombres": "María",
  "apellidos": "López",
  "correo": "mlopez@codip.pe"
}
```

Respuesta satisfactoria:

```json
{
  "id_usuario": 15,
  "nombre_usuario": "mlopez",
  "nombres": "María",
  "apellidos": "López",
  "correo": "mlopez@codip.pe",
  "id_rol": 2,
  "nombre_rol": "Operador",
  "id_tipo_documento": 1,
  "nombre_documento": "DNI",
  "numero_documento": "74859632",
  "estado": true,
  "debe_cambiar_password": true
}
```

`numero_documento` se usa como contraseña temporal (se guarda como hash en `password_hash`) y además queda persistido/visible como dato propio del usuario. Su longitud esperada depende del `TipoDocumento` seleccionado (por defecto, DNI de ocho dígitos).

Errores comunes:

```text
401 Not authenticated
```

Ocurre cuando no se envió el header `Authorization`.

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/usuarios' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -H 'Authorization: Bearer eyJ...access_token...' \
  -d '{
    "id_rol": 2,
    "id_tipo_documento": 1,
    "numero_documento": "74859632",
    "nombre_usuario": "adminEvento",
    "nombres": "Admin",
    "apellidos": "Evento",
    "correo": "adminEvento@codip.pe"
  }'
```

También fallará si `numero_documento` no contiene exactamente la longitud esperada por el tipo de documento seleccionado. La política fuerte se aplica a la nueva contraseña definitiva.

### 7. Inactivar usuario

Endpoint:

```text
PATCH /api/v1/usuarios/{id_usuario}/inactivar
```

Requiere `access_token` de un usuario con permiso:

```text
USUARIOS / INACTIVAR_USUARIO
```

JSON:

```json
{
  "motivo": "Baja administrativa"
}
```

Respuesta satisfactoria:

```json
{
  "id_usuario": 15,
  "nombre_usuario": "mlopez",
  "nombres": "María",
  "apellidos": "López",
  "correo": "mlopez@codip.pe",
  "id_rol": 2,
  "estado": false,
  "debe_cambiar_password": true
}
```

No se elimina el usuario. Solo cambia `estado=false` y se registra auditoría.

## Errores comunes de base de datos

Si aparece un error similar a:

```text
sqlalchemy.exc.ProgrammingError: UndefinedColumn
```

verifica que FastAPI esté conectado a la misma base creada con `SistemaEventosCODIP_postgresql.sql` y reinicia el servidor después de cambiar modelos o `.env`.

```bash
# detener el servidor actual con Ctrl+C y volver a levantar
.venv/bin/fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

## Códigos HTTP esperados

```text
200 operación correcta
201 usuario creado
400 regla inválida, por ejemplo contraseñas distintas o política incumplida
401 autenticación inválida, token inválido o usuario inactivo
403 usuario autenticado sin permiso
404 recurso administrativo no encontrado
409 username o correo duplicado
422 error de validación del JSON
```

## Tests implementados

Los tests están organizados por historia de usuario:

```text
test/modules/usuarios/test_hu_usr_001_login.py
test/modules/usuarios/test_hu_usr_002_password_inicial.py
test/modules/usuarios/test_hu_usr_003_recuperacion.py
test/modules/usuarios/test_hu_usr_004_crear_usuario.py
test/modules/usuarios/test_hu_usr_005_inactivar_usuario.py
test/modules/usuarios/test_flujo_primer_ingreso_dni.py
```

Fixture principal:

```text
test/modules/usuarios/conftest.py
```

Los tests usan PostgreSQL con un esquema temporal por ejecución:

```text
test_usuarios_<uuid>
```

Al finalizar, el esquema se elimina con `DROP SCHEMA ... CASCADE`. No se usa la BD principal para datos destructivos.

### Cobertura por HU

HU-USR-001:

```text
login correcto
password incorrecto
usuario inexistente
usuario inactivo
usuario con password temporal
usuario con password definitiva
respuesta genérica para credenciales inválidas
```

HU-USR-002:

```text
token de cambio válido
token inválido
access token usado incorrectamente como password_change
passwords distintas
password no cumple política
usuario inactivo
cambio correcto
debe_cambiar_password pasa a false
auditoría generada
```

HU-USR-003:

```text
solicitud con correo existente crea código hasheado
solicitud con correo inexistente devuelve misma respuesta (sin crear código)
código válido actualiza contraseña y audita
código expirado o usado es rechazado
código inválido es rechazado
correo sin cuenta asociada es rechazado
código no reutilizable
confirmación y política de contraseña validadas
```

HU-USR-004:

```text
administrador con permiso puede crear
usuario sin permiso recibe 403
username duplicado
correo duplicado
rol inexistente
tipo de documento inexistente
número de documento con longitud inválida para el tipo de documento
número de documento duplicado
creación correcta
debe_cambiar_password=true
password derivado del número de documento y almacenado como hash
auditoría (incluye número de documento, ya no es un dato secreto)
```

HU-USR-005:

```text
usuario autorizado puede inactivar
sin permiso recibe 403
usuario inexistente
usuario queda estado=false
no se elimina
auditoría generada
JWT anterior deja de funcionar después de la inactivación
```

### Ejecutar tests

```bash
.venv/bin/python -m pytest test/modules/usuarios -q
```

Resultado esperado con PostgreSQL disponible:

```text
42 passed
```
