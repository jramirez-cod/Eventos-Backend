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
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
CORS_ALLOW_LOCALHOST_ANY_PORT=false

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

`CORS_ALLOWED_ORIGINS` contiene los orígenes exactos permitidos, separados por
comas. Si el servidor de desarrollo del frontend utiliza un puerto dinámico,
puede activarse localmente:

```env
CORS_ALLOW_LOCALHOST_ANY_PORT=true
```

Ese flag solo acepta `localhost` y `127.0.0.1` con cualquier puerto. Debe
permanecer en `false` en producción, donde se deben declarar los dominios
exactos en `CORS_ALLOWED_ORIGINS`.

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

## Bootstrap de seguridad inicial y modelo de roles/permisos (RBAC)

`scripts/bootstrap_security.py` es el **único** lugar donde se define el
modelado de negocio de acceso: roles, módulos, permisos y qué rol recibe cada
permiso. Es idempotente (se puede correr las veces que sea, no duplica nada)
y **no crea tablas ni modifica el esquema** — si faltan tablas requeridas se
detiene con un error claro. Para el esquema, ver
[Reinicio completo desde cero](#reinicio-completo-desde-cero) más abajo.

### Roles

Solo existen dos roles reales en el sistema:

```text
ADMINISTRADOR_EVENTOS
PERSONAL_EVENTOS
```

`PERSONAL_EVENTOS` tiene el mismo acceso operativo que el administrador en
todos los módulos, **excepto** estas facultades, exclusivas del administrador:

```text
CREAR_USUARIO            (crear cuentas internas)
REABRIR_EVENTO            (reabrir un evento ya finalizado)
ELIMINAR_EVENTO           (borrado físico de un evento)
REABRIR_PROGRAMACION      (reabrir una programación ya finalizada)
```

Ninguna otra acción del sistema es exclusiva del administrador — todo lo demás
(desactivar, crear, editar, afiliar, eliminar invitados, reenviar códigos,
etc.) lo puede hacer también `PERSONAL_EVENTOS`.

### Matriz completa de módulos y permisos

| Módulo | Permisos | Administrador | Personal de Eventos |
| --- | --- | --- | --- |
| `usuarios` | `CREAR_USUARIO` | ✅ | ❌ |
| | `ACTUALIZAR_USUARIO` | ✅ | ❌ |
| | `INACTIVAR_USUARIO` | ✅ | ❌ |
| `GRUPOS` | `CREAR_GRUPO`, `INACTIVAR_GRUPO` | ✅ | ✅ |
| `CATEGORIAS` | `CREAR_CATEGORIA`, `INACTIVAR_CATEGORIA` | ✅ | ✅ |
| `EMPRESAS` | `CREAR_EMPRESA`, `INACTIVAR_EMPRESA` | ✅ | ✅ |
| `MAESTROS` | `CONSULTAR_MAESTROS`, `GESTIONAR_MAESTROS` | ✅ | ✅ |
| `CONTACTOS` | `CREAR_CONTACTO` | ✅ | ✅ |
| | `CONSULTAR_CONTACTO` | ✅ | ✅ |
| | `ACTUALIZAR_CONTACTO` | ✅ | ✅ |
| | `CAMBIAR_EMPRESA_CONTACTO` | ✅ | ✅ |
| | `CAMBIAR_ESTADO_CONTACTO` | ✅ | ✅ |
| | `EXPORTAR_CONTACTO` | ✅ | ✅ |
| | `FUSIONAR_CONTACTO` | ✅ | ❌ (impacto en historial, reservado) |
| `EVENTOS` | `CONSULTAR_EVENTO` | ✅ | ✅ |
| | `CREAR_EVENTO` | ✅ | ✅ |
| | `ACTUALIZAR_EVENTO` | ✅ | ✅ |
| | `CAMBIAR_ESTADO_EVENTO` (finalizar/inactivar) | ✅ | ✅ |
| | `EXPORTAR_EVENTO` | ✅ | ✅ |
| | `CAMBIAR_ESTADO_PROGRAMACION` (finalizar/inactivar) | ✅ | ✅ |
| | `REABRIR_EVENTO` | ✅ | ❌ |
| | `ELIMINAR_EVENTO` | ✅ | ❌ |
| | `REABRIR_PROGRAMACION` | ✅ | ❌ |
| `PARTICIPANTES` | `CONSULTAR_PARTICIPANTE` | ✅ | ✅ |
| | `CREAR_PARTICIPANTE` (agregar/eliminar invitados, cambiar estado, asignar beneficio, etc.) | ✅ | ✅ |
| | `AFILIAR_EMPRESA_EVENTO` (afiliar empresa, contacto principal, enviar/reenviar código) | ✅ | ✅ |

`MAESTROS/GESTIONAR_MAESTROS` cubre cargos, áreas y beneficios (crear,
editar, cambiar estado — incluida la validación de "beneficio en uso").
`PARTICIPANTES/CREAR_PARTICIPANTE` es un permiso amplio: cubre también el
`DELETE` de invitados sin registrar, ya que es la misma operación de gestión
de invitados que el resto del CRUD de participantes.

### Datos de catálogo que siembra el script

```text
TipoDocumento "DNI" (longitud 8)
Categoría "Sin categoría"     — id 1, primera en los selectores de categoría
Beneficio "Sin beneficio"     — id 1, primera en el listado de beneficios
1 usuario Administrador
```

`"Sin categoría"` y `"Sin beneficio"` existen para que los selectores de
categoría/beneficio siempre tengan una opción neutra disponible incluso en
una base recién creada, sin depender de que alguien cree manualmente la
primera fila.

### Ejecutar el bootstrap

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

En ese caso la contraseña se toma de `BOOTSTRAP_ADMIN_PASSWORD` o se solicita
por entrada segura. Si ya existe un usuario con ese `id_rol` de administrador,
el script no crea uno nuevo — reutiliza el existente y solo asegura que roles,
módulos, permisos y catálogos base estén al día.

### Reinicio completo desde cero

Para dejar la base exactamente como en una instalación nueva (borra
absolutamente todo: eventos, empresas, contactos, participantes, auditoría,
usuarios creados manualmente, todo):

```bash
# 1. Borrar todas las tablas del esquema actual
#    (usar una sesión psql o un cliente conectado a la BD de PGDATABASE)
psql -h $PGHOST -p $PGPORT -U $PGUSER -d $PGDATABASE \
  -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 2. Recrear las tablas a partir de los modelos SQLAlchemy actuales
.venv/bin/python scripts/create_db.py

# 3. Sembrar roles, permisos, catálogos base y el usuario administrador
BOOTSTRAP_ADMIN_USERNAME='admin' \
BOOTSTRAP_ADMIN_EMAIL='admin@codip.pe' \
BOOTSTRAP_ADMIN_PASSWORD='AdminSeguro1!' \
BOOTSTRAP_ADMIN_DOCUMENTO='00000000' \
.venv/bin/python scripts/bootstrap_security.py
```

Después del paso 3 la base solo contiene lo listado en
[Datos de catálogo que siembra el script](#datos-de-catálogo-que-siembra-el-script)
— ningún evento, empresa, contacto ni participante de prueba. `create_db.py`
es hoy la única fuente de verdad del esquema (no existe ya un `.sql` estático
en el repositorio); `Base.metadata.create_all()` crea tablas faltantes, pero
no reemplaza un sistema de migraciones ni corrige tablas ya existentes con
columnas distintas — por eso el paso 1 (borrar todo el esquema) es necesario
para partir de cero de verdad, no solo para vaciar filas.

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

## Módulos de Catálogos y Empresas

El backend también contiene módulos independientes para:

```text
Grupos
Categorías
Empresas
```

Sus routers siguen la misma arquitectura `Router -> Service -> Repository` y
están registrados actualmente en `app/api/router.py`.

Rutas principales:

```text
GET    /api/v1/grupos
GET    /api/v1/grupos/{id_grupo}
POST   /api/v1/grupos
PUT    /api/v1/grupos/{id_grupo}
PATCH  /api/v1/grupos/{id_grupo}/inactivar
PATCH  /api/v1/grupos/{id_grupo}/reactivar
GET    /api/v1/grupos/{id_grupo}/categorias
POST   /api/v1/grupos/{id_grupo}/categorias
PATCH  /api/v1/grupos/{id_grupo}/categorias/{id_categoria}/quitar

GET    /api/v1/categorias
GET    /api/v1/categorias/{id_categoria}
POST   /api/v1/categorias
PUT    /api/v1/categorias/{id_categoria}
PATCH  /api/v1/categorias/{id_categoria}/inactivar
PATCH  /api/v1/categorias/{id_categoria}/reactivar

GET    /api/v1/empresas
GET    /api/v1/empresas/{id_empresa}
POST   /api/v1/empresas
POST   /api/v1/empresas/registro-completo
PUT    /api/v1/empresas/{id_empresa}
GET    /api/v1/empresas/consultar-ruc/{ruc}
PATCH  /api/v1/empresas/{id_empresa}/inactivar
PATCH  /api/v1/empresas/{id_empresa}/reactivar
PATCH  /api/v1/empresas/{id_empresa}/clasificacion
GET    /api/v1/empresas/{id_empresa}/historial
```

El bootstrap actual registra los módulos y permisos de Grupos, Categorías y
Empresas. Todos estos endpoints requieren un JWT `access` y el permiso RBAC
correspondiente.

`POST /api/v1/empresas/registro-completo` registra una empresa con cero o más
contactos en una sola transacción. El endpoint requiere `CREAR_EMPRESA` y
`CREAR_CONTACTO`. La empresa se crea primero dentro de la transacción y el
backend asigna su `id_empresa` a cada contacto; el cliente no debe enviarlo.
Si cualquier contacto falla, se revierten también los contactos anteriores,
el historial, la auditoría y la empresa.

```json
{
  "empresa": {
    "nombre_empresa": "Agrolight Perú",
    "ruc": "20552103816",
    "id_detalle_categoria": 8,
    "razon_social": "AGROLIGHT PERU S.A.C.",
    "nombre_comercial": "Agrolight"
  },
  "contactos": [
    {
      "id_cargo": 3,
      "id_tipo_documento": 1,
      "numero_documento": "76543210",
      "nombres": "Ana",
      "apellidos": "Torres",
      "genero": "F",
      "celular": "987654321",
      "correo": "ana@agrolight.pe",
      "es_contacto_principal": true
    }
  ]
}
```

Los endpoints de actualización reciben únicamente campos generales.

`PUT /api/v1/grupos/10`:

```json
{
  "nombre_grupo": "Asociados estratégicos",
  "descripcion": "Empresas asociadas a CODIP"
}
```

`PUT /api/v1/categorias/3`:

```json
{
  "nombre_categoria": "Categoría A",
  "descripcion": "Categoría principal"
}
```

`PUT /api/v1/empresas/25`:

```json
{
  "nombre_empresa": "Agrolight Perú",
  "razon_social": "AGROLIGHT PERU S.A.C.",
  "nombre_comercial": "Agrolight"
}
```

Los DTO de actualización rechazan propiedades adicionales. ID y estado no se
modifican por PUT; en Empresa tampoco se aceptan RUC ni clasificación. El estado
y la clasificación conservan sus endpoints específicos. Cada actualización se
ejecuta junto con su auditoría dentro de una transacción.

## Integración Factiliza

La consulta al proveedor externo Factiliza está aislada en un módulo sin
modelos SQLAlchemy ni tablas propias:

```text
app/modules/factiliza/
├── __init__.py
├── client.py
├── dto.py
├── service.py
└── router.py
```

El backend conserva el token del proveedor y expone contratos propios al
frontend. Las consultas no persisten la respuesta en PostgreSQL y requieren un
JWT `access` de un usuario interno activo.

Variables de entorno:

```env
FACTILIZA_BASE_URL=https://api.factiliza.com/v1
FACTILIZA_API_TOKEN=token-entregado-por-factiliza
FACTILIZA_TIMEOUT_SECONDS=15
```

Nunca envíes `FACTILIZA_API_TOKEN` desde Swagger o el frontend. El backend lo
agrega al header `Authorization: Bearer` de la petición al proveedor.

### Consultar RUC

```http
GET /api/v1/factiliza/ruc/{ruc}
Authorization: Bearer <access_token_del_sistema>
```

```bash
curl -X GET \
  'http://127.0.0.1:8000/api/v1/factiliza/ruc/20552103816' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <access_token_del_sistema>'
```

El RUC debe tener exactamente 11 dígitos. La respuesta incluye razón social,
estado, condición, dirección y ubigeo devueltos por Factiliza.

### Consultar DNI

```http
GET /api/v1/factiliza/dni/{dni}
Authorization: Bearer <access_token_del_sistema>
```

```bash
curl -X GET \
  'http://127.0.0.1:8000/api/v1/factiliza/dni/27427864' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <access_token_del_sistema>'
```

El DNI debe tener exactamente 8 dígitos. La respuesta incluye nombres,
apellidos y los datos de ubicación disponibles.

### Consultar carné de extranjería

```http
GET /api/v1/factiliza/carnet-extranjeria/{carnet}
Authorization: Bearer <access_token_del_sistema>
```

```bash
curl -X GET \
  'http://127.0.0.1:8000/api/v1/factiliza/carnet-extranjeria/001077238' \
  -H 'accept: application/json' \
  -H 'Authorization: Bearer <access_token_del_sistema>'
```

Se aceptan entre 1 y 20 caracteres alfanuméricos. El valor se normaliza a
mayúsculas antes de consultar al proveedor.

Respuestas HTTP comunes:

```text
200 consulta satisfactoria
401 access token del Sistema Eventos ausente o inválido
404 documento no encontrado por Factiliza
422 formato del documento inválido
503 proveedor no disponible, token del proveedor inválido o respuesta inesperada
```

La ruta anterior:

```text
GET /api/v1/empresas/consultar-ruc/{ruc}
```

continúa disponible temporalmente para compatibilidad, aparece como obsoleta
en OpenAPI y delega el consumo HTTP al nuevo cliente. Las integraciones nuevas
deben usar `/api/v1/factiliza/ruc/{ruc}`.

Tests del módulo, sin consumir la API real:

```bash
.venv/bin/python -m pytest test/modules/factiliza -q
```

## Módulo Maestros

Maestros administra los catálogos de Cargos y Áreas mediante la arquitectura
existente:

```text
Router
  -> Service
  -> Repository
  -> SQLAlchemy async
  -> PostgreSQL
```

Archivos principales:

```text
app/modules/maestros/models.py
app/modules/maestros/dto.py
app/modules/maestros/repository.py
app/modules/maestros/service.py
app/modules/maestros/router.py
```

### Modelos de Maestros

`Cargo` es el catálogo utilizado para asignar una función laboral a un
Contacto. Las pantallas de alta o edición deben consultar solamente cargos
activos; inactivar uno no modifica los contactos que ya lo tienen asociado.

`Area` representa la unidad responsable dentro de CODIP, por ejemplo Comercial,
Comunidad o Relaciones Institucionales. El esquema la contempla como referencia
de Eventos, de modo que sus registros también deben conservarse históricamente.

`Cargo` contiene:

```text
id_cargo
nombre_cargo
estado
```

`Area` utiliza el atributo Python `nombre_area`, mapeado a la columna
PostgreSQL `nombre`:

```text
id_area
nombre_area
descripcion
estado
```

Los models existentes no fueron modificados. Los DTOs HTTP son independientes:

```text
CargoCreate
CargoUpdate
CargoEstadoUpdate
CargoResponse
CargoListResponse

AreaCreate
AreaUpdate
AreaEstadoUpdate
AreaResponse
AreaListResponse
```

### Endpoints de Cargos

```text
GET    /api/v1/maestros/cargos
GET    /api/v1/maestros/cargos/{id_cargo}
POST   /api/v1/maestros/cargos
PUT    /api/v1/maestros/cargos/{id_cargo}
PATCH  /api/v1/maestros/cargos/{id_cargo}/estado
```

El listado admite:

```text
search
estado
page
page_size
```

Para llenar el selector de Contactos usando únicamente cargos disponibles:

```text
GET /api/v1/maestros/cargos?estado=true&page=1&page_size=100
```

Crear un cargo desde Swagger:

```json
{
  "nombre_cargo": "Gerente Comercial"
}
```

Respuesta `201 Created`:

```json
{
  "id_cargo": 3,
  "nombre_cargo": "Gerente Comercial",
  "estado": true
}
```

Actualizar el nombre:

```text
PUT /api/v1/maestros/cargos/3
```

```json
{
  "nombre_cargo": "Director Comercial"
}
```

Inactivar o reactivar:

```text
PATCH /api/v1/maestros/cargos/3/estado
```

```json
{
  "estado": false
}
```

La inactivación es lógica. No elimina el cargo ni modifica los contactos que
ya lo utilizan; únicamente deja de aparecer al consultar `estado=true`.

### Endpoints de Áreas

```text
GET    /api/v1/maestros/areas
GET    /api/v1/maestros/areas/{id_area}
POST   /api/v1/maestros/areas
PUT    /api/v1/maestros/areas/{id_area}
PATCH  /api/v1/maestros/areas/{id_area}/estado
```

El listado soporta los mismos parámetros de búsqueda, estado y paginación que
Cargos.

Crear un área desde Swagger:

```json
{
  "nombre_area": "Relaciones Institucionales",
  "descripcion": "Atención y coordinación con instituciones"
}
```

Respuesta `201 Created`:

```json
{
  "id_area": 2,
  "nombre_area": "Relaciones Institucionales",
  "descripcion": "Atención y coordinación con instituciones",
  "estado": true
}
```

Actualizar:

```text
PUT /api/v1/maestros/areas/2
```

```json
{
  "nombre_area": "Comunidad",
  "descripcion": "Relación con la comunidad"
}
```

Cambiar estado:

```text
PATCH /api/v1/maestros/areas/2/estado
```

```json
{
  "estado": false
}
```

No se expone `DELETE` para Cargos ni Áreas. Ambos son catálogos históricos con
relaciones presentes o futuras; se administran mediante `estado=false/true`.

### Reglas de Maestros

```text
Los nombres son obligatorios y no pueden quedar vacíos.
Se eliminan espacios externos y se compactan espacios repetidos.
Los duplicados se comparan ignorando mayúsculas y minúsculas.
Cargos y Áreas se crean activos por defecto.
PUT modifica datos descriptivos, no el estado.
PATCH /estado permite inactivar y reactivar sin DELETE.
Solicitar el estado actual nuevamente es una operación idempotente.
Los listados sin filtro pueden incluir activos e inactivos.
Las escrituras y la auditoría se confirman en una misma transacción.
```

Los listados tienen esta estructura:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 0
}
```

### Auditoría de Maestros

```text
CREAR_CARGO
ACTUALIZAR_CARGO
INACTIVAR_CARGO
REACTIVAR_CARGO

CREAR_AREA
ACTUALIZAR_AREA
INACTIVAR_AREA
REACTIVAR_AREA
```

Cada registro conserva usuario, módulo, entidad, identificador y valores
anterior/nuevo cuando corresponde.

### RBAC y registro del router de Maestros

El router requiere el módulo `MAESTROS` y estos permisos:

```text
CONSULTAR_MAESTROS
GESTIONAR_MAESTROS
```

Los `GET` usan `CONSULTAR_MAESTROS`; altas, actualizaciones y cambios de estado
usan `GESTIONAR_MAESTROS`. El router está registrado en `app/api/router.py` y el
bootstrap crea el módulo y permisos de forma idempotente.

Distribución actual:

```text
Administrador de Eventos: CONSULTAR_MAESTROS + GESTIONAR_MAESTROS
Personal de Eventos:       CONSULTAR_MAESTROS
```

Después de actualizar el backend debe ejecutarse una vez:

```bash
.venv/bin/python scripts/bootstrap_security.py
```

Puede ejecutarse nuevamente sin duplicar módulos, permisos ni relaciones. Tras
reiniciar FastAPI, Swagger muestra la sección **Maestros**.

### Errores esperados de Maestros

```text
400 nombre compuesto únicamente por espacios
401 JWT ausente, inválido o de un usuario inactivo
403 usuario autenticado sin permiso
404 Cargo o Área inexistente
409 nombre duplicado
422 estructura o tipos del JSON inválidos
```

## Módulo Contactos

El módulo Contactos prepara las siguientes historias:

```text
HU-CON-001 Registrar contacto
HU-CON-002 Normalizar celular
HU-CON-003 Seleccionar cargo desde catálogo
HU-CON-004 Cambiar empresa con historial
HU-CON-005 Inactivar y reactivar contacto
HU-CON-006 Fusionar contactos duplicados
HU-CON-007 Buscar y exportar contactos
```

Archivos principales:

```text
app/modules/contactos/models.py
app/modules/contactos/dto.py
app/modules/contactos/repository.py
app/modules/contactos/service.py
app/modules/contactos/router.py
app/modules/maestros/models.py
```

### Modelos utilizados

`Contacto` representa la información vigente del contacto. El nombre completo
no se persiste desde el DTO: se obtiene mediante `Contacto.nombre_completo`.

```text
id_contacto
id_empresa
id_cargo
id_tipo_documento
numero_documento
apellidos
nombres
genero
celular
correo
es_contacto_principal
estado
creado_en
```

`ContactoHistorialEmpresa` conserva las vigencias empresariales:

```text
id_historial
id_contacto
id_empresa
id_usuario_cambio
fecha_inicio
fecha_fin
motivo
```

Los catálogos `Cargo` y `Area` se encuentran en
`app/modules/maestros/models.py`. Contactos valida `Cargo`, pero no crea cargos
como texto libre.

### DTOs

Los contratos HTTP están separados de SQLAlchemy:

```text
ContactoCreate
ContactoUpdate
ContactoEstadoUpdate
ContactoCambiarEmpresaRequest
ContactoFusionRequest
ContactoResponse
ContactoListItem
ContactoPage
```

El update general no acepta `id_empresa`. El cambio de empresa solo puede
realizarse mediante la operación específica que registra historial.

### Reglas principales

```text
La empresa debe existir y estar activa.
El cargo, cuando se informa, debe existir y estar activo.
Tipo y número de documento se envían juntos o ambos se omiten.
El número de documento es único cuando existe.
Nombres, apellidos y género son obligatorios.
El contacto se crea activo y genera su primera vigencia empresarial.
No se eliminan físicamente contactos ni historiales.
Todas las escrituras críticas se auditan en la misma transacción.
```

La función reutilizable `normalize_phone()` elimina espacios antes de guardar:

```text
987 654 321     -> 987654321
987   654 321   -> 987654321
+51 987 654 321 -> +51987654321
```

El formato local debe empezar con `9` y tener nueve dígitos. También se admite
formato internacional con `+` y código de país.

### Permisos RBAC de Contactos

El router utiliza el módulo `CONTACTOS` y estos permisos:

```text
CREAR_CONTACTO
CONSULTAR_CONTACTO
ACTUALIZAR_CONTACTO
CAMBIAR_EMPRESA_CONTACTO
CAMBIAR_ESTADO_CONTACTO
FUSIONAR_CONTACTO
EXPORTAR_CONTACTO
```

Estos permisos se crean de forma idempotente mediante
`scripts/bootstrap_security.py`. `ADMINISTRADOR_EVENTOS` recibe los siete;
`PERSONAL_EVENTOS` recibe todos excepto `FUSIONAR_CONTACTO`.

### Habilitación de Contactos

El router está registrado en `app/api/router.py` y aparece automáticamente en
Swagger bajo la sección **Contactos**. El bootstrap debe ejecutarse al menos una
vez en cada base para crear el módulo, los permisos y sus asignaciones RBAC:

```bash
.venv/bin/python scripts/bootstrap_security.py
```

### Probar Contactos desde Swagger

Primero iniciar sesión mediante el botón **Authorize** usando un usuario con
los permisos anteriores. Swagger conservará el Bearer token mientras la página
permanezca abierta.

#### 1. Registrar contacto

```text
POST /api/v1/contactos
```

JSON satisfactorio:

```json
{
  "id_empresa": 10,
  "id_cargo": 3,
  "id_tipo_documento": 1,
  "numero_documento": "76543210",
  "nombres": "Juan Carlos",
  "apellidos": "Perez Ramos",
  "genero": "M",
  "celular": "987 654 321",
  "correo": "juan.perez@empresa.com",
  "es_contacto_principal": false
}
```

Respuesta `201 Created`:

```json
{
  "id_contacto": 1,
  "id_empresa": 10,
  "nombre_empresa": "Empresa CODIP",
  "id_cargo": 3,
  "nombre_cargo": "Gerente General",
  "id_tipo_documento": 1,
  "nombre_tipo_documento": "DNI",
  "numero_documento": "76543210",
  "nombres": "Juan Carlos",
  "apellidos": "Perez Ramos",
  "nombre_completo": "Perez Ramos Juan Carlos",
  "genero": "M",
  "celular": "987654321",
  "correo": "juan.perez@empresa.com",
  "es_contacto_principal": false,
  "estado": true
}
```

`id_empresa`, `id_cargo` e `id_tipo_documento` deben existir realmente en la
base conectada. El alta crea también la primera fila de historial empresarial.

#### 2. Buscar y filtrar contactos

```text
GET /api/v1/contactos?search=76543210&page=1&page_size=20
GET /api/v1/contactos?id_empresa=10
GET /api/v1/contactos?id_cargo=3
GET /api/v1/contactos?estado=false
```

La respuesta contiene:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 0
}
```

`search` consulta nombres, apellidos, documento, correo y celular. Los joins de
empresa, cargo y tipo de documento se resuelven en la consulta para evitar N+1.

#### 3. Consultar o actualizar un contacto

```text
GET   /api/v1/contactos/{id_contacto}
PATCH /api/v1/contactos/{id_contacto}
```

Ejemplo de actualización:

```json
{
  "id_cargo": 4,
  "nombres": "Juan Carlos Alberto",
  "celular": "+51 987 654 321",
  "correo": "juan.actualizado@empresa.com"
}
```

Solo se actualizan los campos enviados. No se puede cambiar la empresa desde
este JSON.

#### 4. Cambiar empresa con historial

```text
PATCH /api/v1/contactos/{id_contacto}/empresa
```

```json
{
  "id_empresa": 25,
  "motivo": "Cambio laboral"
}
```

La operación bloquea el contacto durante la transacción, cierra la vigencia
anterior, abre una nueva, actualiza `contacto.id_empresa` y registra auditoría.
Si el contacto no tenía historial, reconstruye la vigencia inicial usando
`contacto.creado_en`.

#### 5. Inactivar o reactivar

```text
PATCH /api/v1/contactos/{id_contacto}/estado
```

Inactivar:

```json
{
  "estado": false,
  "motivo": "Baja administrativa"
}
```

Reactivar:

```json
{
  "estado": true,
  "motivo": "Reincorporación"
}
```

El registro y su historial permanecen en PostgreSQL.

#### 6. Fusionar duplicados

```text
POST /api/v1/contactos/fusionar
```

```json
{
  "id_contacto_principal": 10,
  "id_contacto_duplicado": 22,
  "motivo": "Duplicidad detectada"
}
```

El principal se conserva. El duplicado no se elimina: queda inactivo, se cierra
su vigencia empresarial y se registra `FUSIONAR_CONTACTO` en auditoría.

Actualmente no se migran relaciones de Eventos o Participantes porque esos
módulos todavía no existen. El model tampoco tiene un campo permanente como
`fusionado_en`; por ello esa parte deberá ampliarse cuando existan las futuras
relaciones.

#### 7. Exportar CSV

```text
GET /api/v1/contactos/exportar
```

Admite los mismos filtros principales del listado y descarga
`contactos.csv` codificado en UTF-8.

### Errores esperados de Contactos

```text
400 empresa/cargo inactivo, celular inválido o documento incompleto
401 JWT ausente, inválido o perteneciente a un usuario inactivo
403 usuario autenticado sin el permiso requerido
404 contacto, empresa, cargo o tipo de documento inexistente
409 documento duplicado, misma empresa o conflicto de persistencia
422 JSON o tipos inválidos
```

### Registro de tablas para desarrollo

`scripts/create_db.py` importa por side effect:

```text
app.modules.maestros.models
app.modules.contactos.models
```

Por ello una instalación local limpia puede registrar también:

```text
cargo
area
contacto
contacto_historial_empresa
```

Comando, solo para una BD local de desarrollo o test:

```bash
python3 scripts/create_db.py
```

`create_all()` crea tablas faltantes, pero no reemplaza un sistema de
migraciones ni corrige tablas existentes.

### Incompatibilidad conocida del historial

Existe una diferencia que no debe ignorarse:

```text
SistemaEventosCODIP_postgresql.sql  -> contacto_empresa_historial
app/modules/contactos/models.py     -> contacto_historial_empresa
```

También cambian los nombres de sus columnas:

```text
SQL:   id_contacto_empresa_historial, vigente_desde, vigente_hasta, id_usuario
Model: id_historial, fecha_inicio, fecha_fin, id_usuario_cambio
```

El repository implementado respeta el model existente, según la restricción de
no modificar models ni esquema. Antes de usar HU-CON-004 sobre una BD creada
únicamente con el SQL histórico, el equipo debe decidir cuál representación es
la oficial y resolverla mediante una migración controlada. Ejecutar
`create_db.py` sin esa decisión puede crear una segunda tabla de historial con
semántica equivalente.

## Errores comunes de base de datos

Si aparece un error similar a:

```text
sqlalchemy.exc.ProgrammingError: UndefinedColumn
```

verifica que la base apuntada por `.env` tenga el esquema al día con los modelos actuales (ver [Reinicio completo desde cero](#reinicio-completo-desde-cero)) y reinicia el servidor después de cambiar modelos o `.env`.

```bash
# detener el servidor actual con Ctrl+C y volver a levantar
.venv/bin/fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

## Códigos HTTP esperados

```text
200 operación correcta
201 recurso creado
400 regla de negocio inválida o dato incompatible
401 autenticación inválida, token inválido o usuario inactivo
403 usuario autenticado sin permiso
404 recurso solicitado no encontrado
409 dato duplicado, misma asociación o dependencia activa
422 error de validación del JSON
```

## Módulo Eventos

Implementa `HU-EVE-001` a `HU-EVE-007` con la arquitectura
Router → Service → Repository → SQLAlchemy → PostgreSQL.

### Modelos y estados

```text
Evento 1:1 ProgramacionEvento 1:N DetalleProgramacionEvento
ProgramacionEvento N:1 Lugar (opcional)
```

El evento usa los estados `ABIERTO`, `FINALIZADO` e `INACTIVO`. La modalidad
es obligatoria y admite `PRESENCIAL`, `VIRTUAL` o `HIBRIDO`. Lugar y enlace son
opcionales. El rango genera automáticamente un registro por día y PostgreSQL
impide duplicar una fecha dentro de la misma programación.

### Endpoints de Eventos

```text
POST   /api/v1/eventos
GET    /api/v1/eventos
GET    /api/v1/eventos/exportar
GET    /api/v1/eventos/{id_evento}
PUT    /api/v1/eventos/{id_evento}
DELETE /api/v1/eventos/{id_evento}
GET    /api/v1/eventos/{id_evento}/programacion
PUT    /api/v1/eventos/{id_evento}/programacion
GET    /api/v1/eventos/{id_evento}/dias
PATCH  /api/v1/eventos/{id_evento}/dias/{id_dia}
PUT    /api/v1/eventos/{id_evento}/flyer
PATCH  /api/v1/eventos/{id_evento}/finalizar
PATCH  /api/v1/eventos/{id_evento}/reabrir
PATCH  /api/v1/eventos/{id_evento}/inactivar
```

Ejemplo satisfactorio para `POST /api/v1/eventos`:

```json
{
  "nombre_evento": "Nexo Summit 2026",
  "descripcion": "Encuentro empresarial CODIP",
  "fecha_inicio": "2026-10-10",
  "fecha_fin": "2026-10-12",
  "aforo": 250,
  "modalidad": "HIBRIDO",
  "enlace_general": "https://meet.example/nexo",
  "lugar": {
    "pais": "Perú",
    "provincia": "Lima",
    "distrito": "Miraflores",
    "direccion": "Av. Principal 123"
  },
  "hora_inicio": "09:00:00",
  "hora_fin": "18:00:00"
}
```

La creación deja el evento `ABIERTO`, crea una única programación y genera los
días 10, 11 y 12 dentro de la misma transacción. Un nombre repetido se permite.

El listado acepta `search`, `fecha_desde`, `fecha_hasta`, `estado`, `modalidad`,
`page` y `page_size`. Las fechas se filtran por solapamiento. La exportación
acepta los mismos filtros y descarga `eventos.xlsx`.

El flyer se envía como `multipart/form-data`, campo `flyer`, y admite JPG, JPEG
o PNG. Configuración:

```text
EVENT_FLYER_UPLOAD_DIR=uploads/eventos
EVENT_FLYER_MAX_BYTES=5242880
```

### Permisos de Eventos

```text
CONSULTAR_EVENTO
CREAR_EVENTO
ACTUALIZAR_EVENTO
CAMBIAR_ESTADO_EVENTO
REABRIR_EVENTO
ELIMINAR_EVENTO
EXPORTAR_EVENTO
```

Administrador recibe todos. Personal recibe consulta, creación, actualización,
cambio de estado y exportación; no puede reabrir ni eliminar.

### Compatibilidad del esquema

La base de desarrollo verificada no tenía tablas de Eventos y `create_db.py`
creó el modelo nuevo correctamente. `SistemaEventosCODIP_postgresql.sql`
conserva una definición antigua e incompatible (estado booleano, política/área
obligatorias y detalle sin horarios). No debe usarse para reemplazar estas
tablas sin una migración revisada por el equipo.

La eliminación física funciona cuando no hay participantes. El repository
comprueba primero la tabla actual `participante` y conserva compatibilidad de
lectura con una eventual tabla legada `evento_contacto`; si encuentra
dependencias bloquea con `409`.
El periodo autorizado de corrección sigue pendiente porque las HU no definen
una duración.

## Módulo Participantes

Se implementaron:

```text
HU-PAR-001 Añadir invitados manualmente
HU-PAR-002 Crear contacto desde el evento
HU-PAR-003 Registrar empresa sin contacto
HU-PAR-004 Evitar participante duplicado
```

El dominio separa la afiliación empresarial de la persona invitada:

```text
Evento -> EventoEmpresa -> Participante -> Contacto
```

`EventoEmpresa` puede existir sin participantes. `Participante` no duplica
nombres, documento ni datos de contacto; referencia al `Contacto` real.

### Modelos y constraints

```text
EventoEmpresa
- id_evento_empresa
- id_evento
- id_empresa
- estado
- creado_en
- creado_por

Participante
- id_participante
- id_evento_empresa
- id_evento
- id_contacto
- confirmacion: SIN_RESPUESTA | SI | NO
- estado
- creado_en
- creado_por
```

PostgreSQL protege estas reglas incluso ante requests concurrentes:

```text
UNIQUE(evento_empresa.id_evento, evento_empresa.id_empresa)
UNIQUE(participante.id_evento, participante.id_contacto)
FK compuesta participante(id_evento_empresa, id_evento)
  -> evento_empresa(id_evento_empresa, id_evento)
```

La FK compuesta evita asociar accidentalmente un participante a una afiliación
que pertenece a otro evento.

### Endpoints de Participantes

| Método | Ruta | Uso |
| --- | --- | --- |
| `POST` | `/api/v1/participantes/eventos/{id_evento}/empresas` | Afiliar empresa activa |
| `GET` | `/api/v1/participantes/eventos/{id_evento}/empresas` | Listar empresas afiliadas |
| `POST` | `/api/v1/participantes/eventos/{id_evento}` | Añadir uno o varios contactos |
| `POST` | `/api/v1/participantes/eventos/{id_evento}/crear-contacto` | Crear contacto e inscribirlo |
| `GET` | `/api/v1/participantes` | Listar y filtrar participantes |
| `GET` | `/api/v1/participantes/{id_participante}` | Consultar detalle |

No se implementan todavía confirmación pública, QR, asistencia, cupos,
desafiliación ni eliminación de participantes.

### Probar Participantes en Swagger

1. Iniciar sesión desde `POST /api/v1/auth/login` y autorizar Swagger.
2. Crear o elegir un Evento `ABIERTO`.
3. Afiliar una empresa activa:

```json
{
  "id_empresa": 25
}
```

La respuesta incluye `id_evento_empresa`; ese identificador se utiliza en los
siguientes requests. La empresa queda afiliada aunque aún tenga cero invitados.

4. Añadir contactos activos de esa misma empresa:

```json
{
  "id_evento_empresa": 8,
  "ids_contacto": [15]
}
```

Respuesta conceptual:

```json
{
  "created": 1,
  "participantes": [
    {
      "id_participante": 100,
      "id_evento_empresa": 8,
      "id_evento": 5,
      "nombre_evento": "Nexo Summit",
      "id_empresa": 25,
      "nombre_empresa": "Empresa X",
      "id_contacto": 15,
      "nombre_completo": "Perez Ramos Juan",
      "numero_documento": "76543210",
      "correo": "juan@empresa.com",
      "celular": "987654321",
      "confirmacion": "SIN_RESPUESTA",
      "estado": true,
      "creado_en": "2026-08-23T10:00:00-05:00",
      "creado_por": 1
    }
  ]
}
```

5. Para crear el contacto desde el propio evento:

```json
{
  "id_evento_empresa": 8,
  "contacto": {
    "id_empresa": 25,
    "id_cargo": 3,
    "id_tipo_documento": 1,
    "numero_documento": "76543210",
    "nombres": "Juan",
    "apellidos": "Perez Ramos",
    "genero": "M",
    "celular": "987 654 321",
    "correo": "juan@empresa.com",
    "es_contacto_principal": false
  }
}
```

Esta operación reutiliza `ContactoService`: valida empresa, cargo, tipo de
documento, documento único y celular; crea también la primera vigencia en
`contacto_historial_empresa`. Contacto, historial, participante y auditorías se
confirman en una sola transacción. Si falla la inscripción, todo hace rollback.

6. Consultar con filtros:

```http
GET /api/v1/participantes?id_evento=5&id_empresa=25&confirmacion=SIN_RESPUESTA&search=Perez&page=1&page_size=20
```

### Reglas, permisos y errores

Todas las altas requieren Evento `ABIERTO`, empresa activa y afiliación
explícita. Los contactos deben existir, estar activos y pertenecer actualmente
a la empresa afiliada. Un lote es atómico: si un contacto falla, no se crea
ninguno del lote.

```text
CONSULTAR_PARTICIPANTE
CREAR_PARTICIPANTE
AFILIAR_EMPRESA_EVENTO
```

El bootstrap asigna los tres permisos a `ADMINISTRADOR_EVENTOS` y
`PERSONAL_EVENTOS`.

```text
401 token ausente, inválido o usuario inactivo
403 usuario autenticado sin permiso
404 evento, empresa, afiliación, contacto o participante inexistente
409 evento no abierto, entidad inactiva, empresa incorrecta o duplicidad
422 request estructuralmente inválido
```

Auditorías generadas:

```text
AFILIAR_EMPRESA_EVENTO
AGREGAR_PARTICIPANTE_EVENTO
CREAR_CONTACTO_DESDE_EVENTO
```

### Compatibilidad con el SQL canónico

`SistemaEventosCODIP_postgresql.sql` conserva un diseño anterior e
incompatible: `EVENTO_EMPRESA` referencia `idProgramacionEvento` y
`EVENTO_CONTACTO` mezcla confirmación con asistencia, hora de ingreso y
credencial. La base configurada no contenía esas tablas al implementar estas
HU. Se crearon `evento_empresa` y `participante` con el modelo normalizado
descrito arriba, referenciado directamente a `evento`.

No debe ejecutarse la definición legada de esas tablas encima del esquema
actual. Si el SQL canónico continuará como instalador oficial, el equipo debe
actualizarlo mediante una migración revisada; la asistencia y QR siguen fuera
de Participantes.

## Tests implementados

Los tests están organizados por historia de usuario:

```text
test/modules/usuarios/test_hu_usr_001_login.py
test/modules/usuarios/test_hu_usr_002_password_inicial.py
test/modules/usuarios/test_hu_usr_003_recuperacion.py
test/modules/usuarios/test_hu_usr_004_crear_usuario.py
test/modules/usuarios/test_hu_usr_005_inactivar_usuario.py
test/modules/usuarios/test_flujo_primer_ingreso_dni.py
test/modules/grupos/
test/modules/categorias/
test/modules/empresas/
test/modules/contactos/
test/modules/maestros/test_cargos.py
test/modules/maestros/test_areas.py
test/modules/eventos/
test/modules/participantes/
```

Fixture principal:

```text
test/modules/usuarios/conftest.py
test/modules/contactos/conftest.py
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
.venv/bin/python -m pytest test/modules/grupos test/modules/categorias -q
.venv/bin/python -m pytest test/modules/empresas -q
.venv/bin/python -m pytest test/modules/contactos -q
.venv/bin/python -m pytest test/modules/maestros -v
.venv/bin/python -m pytest test/modules/eventos -q
.venv/bin/python -m pytest test/modules/participantes -q
.venv/bin/python -m pytest -q
```

Estado de la colección actual:

```text
43 tests de Usuarios
53 tests de Grupos, Categorías y Empresas
33 tests de Contactos
20 tests de Maestros
20 tests de Factiliza
3 tests del verificador de dependencias de borrado
44 tests de Eventos
22 tests de Participantes
238 tests totales aprobados
```

Los tests de Maestros cubren:

```text
crear Cargo y Área correctamente
normalización de nombres y descripciones
nombre obligatorio y rechazo de valores vacíos
duplicados ignorando mayúsculas y espacios
consulta por identificador
404 para recursos inexistentes
listados paginados
búsqueda por nombre
filtro estado=true
actualización y auditoría de valores anterior/nuevo
rechazo de nombres duplicados al actualizar
inactivación sin eliminación física
catálogos inactivos excluidos del filtro de activos
reactivación e idempotencia de estado
403 para usuarios sin permiso
```

Resultado real de la ejecución del módulo:

```text
20 passed
```

Resultado real de la regresión completa:

```text
238 passed in 192.91s
```

Los tests de Participantes cubren:

```text
empresa afiliada al evento sin contactos
duplicidad de afiliación
evento finalizado o inactivo
empresa y contacto inactivos
contacto perteneciente a otra empresa
alta de uno y varios participantes
confirmación inicial SIN_RESPUESTA
atomicidad de altas múltiples
creación de Contacto e historial desde Evento
rollback forzado sin datos parciales
auditoría y permisos RBAC
listado, búsqueda, filtros, paginación y consulta por ID
constraint PostgreSQL UNIQUE(id_evento, id_contacto)
```

Resultado real del módulo Participantes:

```text
22 passed in 23.81s
```

Los tests de Contactos cubren:

```text
alta correcta y auditoría
empresa inexistente o inactiva
documento duplicado
cargo inexistente o inactivo
normalización y rechazo de celulares
cambio de empresa e historial vigente único
reconstrucción de vigencia inicial faltante
inactivación y reactivación
actualización parcial
fusión sin eliminación física
búsqueda y filtros
paginación y exportación CSV
registro de metadata en create_db.py
401 sin autenticación y 403 sin permiso
```

Resultado real del módulo Contactos:

```text
33 passed
```

La colección puede verificarse sin conectarse a PostgreSQL:

```bash
.venv/bin/python -m pytest --collect-only -q
```

Las pruebas de integración crean un esquema PostgreSQL temporal por caso y lo
eliminan al finalizar. La conexión configurada debe permitir `CREATE SCHEMA` y
`DROP SCHEMA`; nunca se deben ejecutar estas pruebas apuntando a una BD de
producción.

## Auditoría de cobertura CRUD y borrado

La matriz actual de operaciones por recurso, las diferencias entre la base
real y el SQL canónico, y la política recomendada de baja lógica están en:

```text
CRUD_COVERAGE.md
```

Antes de diseñar un DELETE físico puede ejecutarse el verificador de solo
lectura:

```bash
.venv/bin/python scripts/check_delete_dependencies.py \
  --table grupo \
  --id 10 \
  --include-empty
```

El script no elimina ni modifica datos. Inspecciona las claves foráneas reales
de PostgreSQL y devuelve las tablas/columnas que bloquean el borrado. Un
resultado `can_delete=true` no reemplaza las reglas de negocio ni la revisión
del historial de auditoría.
