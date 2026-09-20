# Eventos-Backend

Backend del **Sistema Eventos CODIP**, construido con FastAPI, Pydantic 2,
SQLAlchemy 2 async y PostgreSQL.

> Estado verificado: 8 de septiembre de 2026. Este documento se contrastó con los
> routers, DTO, services, models, bootstrap, OpenAPI y tests presentes en el
> repositorio. Para integrar otro cliente o continuar el desarrollo, use este
> README junto con el código y los tests actuales.

## Fuente de verdad

Cuando exista una diferencia entre documentos, siga este orden:

1. Models, DTO, services y routers dentro de `app/`.
2. Tests automatizados dentro de `test/`.
3. OpenAPI generado por FastAPI en `/openapi.json` y Swagger en `/docs`.
4. Este README.
5. `SistemaEventosCODIP_postgresql.sql`, que conserva un esquema histórico y
   **no coincide por completo** con los models actuales.

No ejecute el SQL histórico encima de una base creada con los models actuales.
Las diferencias conocidas están documentadas al final.

## Estado funcional

| Módulo | Estado actual |
| --- | --- |
| Acceso y Usuarios | Login, primer ingreso con DNI y código, recuperación, gestión e inactivación |
| Grupos y Categorías | Consulta, alta, actualización, estado y asociación N:M |
| Empresas | Consulta, alta, registro con contactos, actualización, clasificación e historial |
| Contactos | CRUD lógico, empresa vigente, principal exclusivo, fusión lógica y exportación |
| Factiliza | Consulta externa de RUC, DNI y carné de extranjería |
| Maestros | Cargos, áreas y beneficios administrables |
| Eventos | Política, múltiples programaciones, días, lugares, responsables, flyer y estados |
| Participantes | Empresas afiliadas, contactos, invitados, beneficios, QR, asistencia y credenciales |
| Portal | Autogestión externa de participantes mediante código y token limitado |
| Comunicaciones | Plantillas globales configurables, historial, preview, RBAC y SMTP |
| Reportes | Dashboard, KPIs, filtros, distribuciones, detalle, series, beneficios, acreditación y Excel |
| Auditoría | Registro transaccional de operaciones críticas |

No existen todavía módulos de pagos, alertas generales, cupos independientes,
asistencia separada ni administración HTTP de roles/permisos.

La explicación completa del envío SMTP, templates, endpoints que lo disparan y
evolución por empresa está en
[`app/modules/comunicaciones/README.md`](app/modules/comunicaciones/README.md).
El contrato de reporting, sus métricas, filtros, privacidad y límites está en
[`README_REPORTES.md`](README_REPORTES.md).

## Arquitectura

El proyecto es un monolito modular. No es una arquitectura de microservicios.

```text
HTTP
  -> Router (contrato y códigos HTTP)
  -> Service (reglas y transacciones)
  -> Repository (persistencia)
  -> SQLAlchemy AsyncSession
  -> PostgreSQL
```

Los DTO Pydantic son contratos HTTP. Los models SQLAlchemy representan tablas
y no se retornan directamente salvo que un DTO los valide mediante
`from_attributes`.

```text
app/
├── api/
│   ├── router.py
│   └── routes/health.py
├── core/
│   ├── config.py
│   └── security.py
├── db/
│   ├── base.py
│   └── session.py
└── modules/
    ├── auditoria/
    ├── categorias/
    ├── comunicaciones/
    ├── contactos/
    ├── empresas/
    ├── eventos/
    ├── factiliza/
    ├── grupos/
    ├── maestros/
    ├── participantes/
    ├── portal/
    ├── reportes/
    └── usuarios/
```

`AsyncSessionLocal` usa `expire_on_commit=False`, `pool_pre_ping=True` y una
sesión por request. Los services controlan `commit` y `rollback` para mantener
atómicas las operaciones que combinan varias tablas y auditoría.

## Instalación

Requisitos: Python 3.12 y PostgreSQL accesible.

```bash
cd Eventos-Backend
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

El `docker-compose.yml` incluido levanta únicamente PostgreSQL:

```bash
docker compose up -d postgres
```

## Configuración

La aplicación lee `.env` con `pydantic-settings`. Nunca versionar secretos,
tokens de terceros ni app passwords reales.

```env
# PostgreSQL
PGHOST=localhost
PGPORT=5432
PGDATABASE=eventos
PGUSER=postgres
PGPASSWORD=...

# Aplicación y frontend
APP_NAME=Sistema Eventos API
APP_VERSION=1.0.0
APP_HOST=0.0.0.0
APP_PORT=8000
APP_DEBUG=false
FRONTEND_BASE_URL=http://localhost:4200
CORS_ALLOWED_ORIGINS=http://localhost:4200,http://127.0.0.1:4200
CORS_ALLOW_LOCALHOST_ANY_PORT=false

# Flyers
EVENT_FLYER_UPLOAD_DIR=uploads/eventos
EVENT_FLYER_MAX_BYTES=5242880

# Reportes
REPORT_EXPORT_SYNC_MAX_ROWS=10000

# JWT y contraseñas
SECRET_KEY=un-secreto-largo-aleatorio
JWT_ALGORITHM=HS256
JWT_ISSUER=eventos-codip-api
ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_CHANGE_TOKEN_EXPIRE_MINUTES=15
INITIAL_PASSWORD_CODE_EXPIRE_MINUTES=10
INITIAL_PASSWORD_CODE_LENGTH=6
TEMPORARY_DNI_LENGTH=8
RECOVERY_TOKEN_EXPIRE_MINUTES=30
PORTAL_ACCESS_TOKEN_EXPIRE_MINUTES=60
PASSWORD_MIN_LENGTH=8
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_NUMBER=true
PASSWORD_REQUIRE_SPECIAL=true
PASSWORD_HASH_ARGON2_TIME_COST=3
PASSWORD_HASH_ARGON2_MEMORY_COST=65536
PASSWORD_HASH_ARGON2_PARALLELISM=4

# Correo
EMAIL_ENABLED=false
EMAIL_PRINT_CODE_TO_CONSOLE=true
EMAIL_SENDER_USER_ID=1
EMAIL_FROM_NAME=Sistema Eventos CODIP
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_STARTTLS=true
SMTP_TIMEOUT_SECONDS=20
SMTP_APP_PASSWORD=...

# Factiliza
FACTILIZA_BASE_URL=https://api.factiliza.com/v1
FACTILIZA_API_TOKEN=...
FACTILIZA_TIMEOUT_SECONDS=15
```

`SECRET_KEY` firma los JWT y participa en hashes HMAC de códigos. Cambiarla
invalida tokens y códigos existentes.

`CORS_ALLOW_LOCALHOST_ANY_PORT=true` admite únicamente `localhost` y
`127.0.0.1` con puerto variable. Úselo solo en desarrollo; producción debe
declarar orígenes exactos.

### Modos de correo

| Configuración | Comportamiento |
| --- | --- |
| `EMAIL_ENABLED=true` | Envía por SMTP usando la configuración global persistida |
| `EMAIL_PRINT_CODE_TO_CONSOLE=true` | Imprime códigos/QR en consola para desarrollo |
| Ambos `true` | SMTP es principal y consola funciona como respaldo de desarrollo |
| Ambos `false` | No se envía ni imprime; no es útil para flujos que requieren entrega |

El app password solo vive en `SMTP_APP_PASSWORD`. El remitente se obtiene de
`usuario.correo` mediante `correo_configuracion_global`; no se guarda la
credencial SMTP en PostgreSQL. Primer ingreso, recuperación, acceso de empresa
y QR usan plantillas versionadas en `correo_plantilla`.

## Base de datos

Los models actuales registran estas tablas:

```text
rol                         tipo_documento
usuario                     usuario_token_recuperacion
modulo                      permiso
rol_permiso_modulo          auditoria

grupo                       categoria
detalle_categoria           empresa
empresa_historial_clasificacion

cargo                       area
beneficio                   contacto
contacto_historial_empresa

lugar                       politica_evento
detalle_politica_evento     evento
programacion_evento         detalle_programacion_evento
responsable_evento

evento_empresa              evento_contacto
asignacion_beneficio        participante_qr
codigo_acceso_principal

correo_configuracion_global correo_plantilla
correo_plantilla_historial  correo_envio
```

Relaciones de negocio principales:

```text
Rol -> RolPermisoModulo -> Modulo + Permiso
Usuario -> Rol + TipoDocumento

Grupo -> DetalleCategoria <- Categoria
Empresa -> DetalleCategoria
Empresa -> EmpresaHistorialClasificacion
Contacto -> Empresa + Cargo + TipoDocumento
Contacto -> ContactoHistorialEmpresa

Evento -> Area + PoliticaEvento
PoliticaEvento -> DetallePoliticaEvento -> Beneficio + Categoria
Evento -> ProgramacionEvento -> Lugar
ProgramacionEvento -> DetalleProgramacionEvento
ProgramacionEvento -> ResponsableEvento -> Usuario

ProgramacionEvento -> EventoEmpresa -> Empresa
EventoEmpresa -> Contacto principal
ProgramacionEvento -> EventoContacto -> Contacto o snapshot de invitado
EventoContacto -> AsignacionBeneficio
EventoContacto -> ParticipanteQr
EventoEmpresa -> CodigoAccesoPrincipal
CorreoConfiguracionGlobal -> Usuario emisor
CorreoPlantilla -> CorreoPlantillaHistorial + CorreoEnvio
```

### Crear tablas en desarrollo

Solo sobre una base vacía de desarrollo o test:

```bash
.venv/bin/python scripts/create_db.py
```

`Base.metadata.create_all()` crea tablas ausentes y el script siembra de forma
idempotente las cuatro plantillas globales de correo. No migra columnas,
constraints ni enums existentes. No sustituye Alembic y no debe usarse para
“actualizar” una base poblada.

## Bootstrap de seguridad

El bootstrap es idempotente y no se ejecuta al iniciar FastAPI. Comprueba que
el esquema requerido exista, crea catálogos base, RBAC y el primer administrador.

Variables opcionales para ejecución no interactiva:

```env
BOOTSTRAP_ADMIN_USERNAME=admin
BOOTSTRAP_ADMIN_EMAIL=admin@codip.pe
BOOTSTRAP_ADMIN_PASSWORD=AdminSeguro1!
BOOTSTRAP_ADMIN_NOMBRES=Administrador
BOOTSTRAP_ADMIN_APELLIDOS=Eventos
BOOTSTRAP_ADMIN_DOCUMENTO=00000000
```

```bash
.venv/bin/python scripts/bootstrap_security.py
```

También admite argumentos no sensibles y solicita la contraseña por terminal:

```bash
.venv/bin/python scripts/bootstrap_security.py \
  --username admin \
  --email admin@codip.pe \
  --nombres Administrador \
  --apellidos Eventos \
  --documento 00000000
```

Datos garantizados:

```text
Roles: ADMINISTRADOR_EVENTOS, PERSONAL_EVENTOS
Tipo de documento: DNI (8 dígitos)
Categoría: Sin categoría
Beneficio: Sin beneficio
Módulos RBAC: USUARIOS, GRUPOS, CATEGORIAS, EMPRESAS, MAESTROS,
              CONTACTOS, EVENTOS, PARTICIPANTES, COMUNICACIONES
Correo: configuración GLOBAL enlazada al administrador y 4 plantillas base
```

Si ya existe un usuario del rol administrador, el script lo reutiliza y no
solicita ni reemplaza su contraseña.

## Ejecutar la API

```bash
.venv/bin/fastapi dev app/main.py --host 0.0.0.0 --port 8000
```

```text
Swagger:  http://localhost:8000/docs
OpenAPI:  http://localhost:8000/openapi.json
Root:     http://localhost:8000/
Health:   http://localhost:8000/api/v1/health
Database: http://localhost:8000/api/v1/health/database
```

Todas las rutas funcionales usan el prefijo `/api/v1`.

## Autenticación y seguridad

Se usan tres tipos de JWT incompatibles entre sí:

| `token_type` | Finalidad |
| --- | --- |
| `access` | Endpoints internos protegidos |
| `password_change` | Solo cambio de contraseña del primer ingreso |
| `portal_access` | Solo portal externo de una afiliación empresarial |

Las contraseñas se almacenan con Argon2. Los códigos de recuperación, primer
ingreso y portal se almacenan como hash; nunca como texto plano.

Cada endpoint interno protegido ejecuta `get_current_user()`: valida firma y
tipo de JWT, vuelve a consultar el usuario en PostgreSQL y exige
`usuario.estado=true`. Por ello, un access token previo deja de funcionar
inmediatamente cuando el usuario es inactivado.

### Autorizar Swagger

Para un usuario con contraseña definitiva:

1. Abrir `/docs` y pulsar **Authorize**.
2. Escribir `nombre_usuario` en `username` y la contraseña en `password`.
3. Dejar `client_id` y `client_secret` vacíos.
4. Swagger llama internamente al endpoint oculto `POST /api/v1/auth/token` y
   conserva el Bearer durante la sesión de la página.

Para curl o frontend, el token de `POST /auth/login` se envía explícitamente:

```http
Authorization: Bearer <access_token>
```

El backend no mantiene una sesión de usuario en memoria. El cliente conserva
el JWT; el backend valida en cada request que el usuario siga activo.

## RBAC

`require_permission(modulo, permiso)` consulta
`rol_permiso_modulo`. No se autorizan operaciones comparando nombres de roles
dentro de los endpoints.

| Módulo | Permisos | Admin | Personal |
| --- | --- | :---: | :---: |
| USUARIOS | `CREAR_USUARIO`, `INACTIVAR_USUARIO`, `ACTUALIZAR_USUARIO` | Sí | No |
| GRUPOS | `CREAR_GRUPO`, `INACTIVAR_GRUPO` | Sí | Sí |
| CATEGORIAS | `CREAR_CATEGORIA`, `INACTIVAR_CATEGORIA` | Sí | Sí |
| EMPRESAS | `CREAR_EMPRESA`, `INACTIVAR_EMPRESA` | Sí | Sí |
| MAESTROS | `CONSULTAR_MAESTROS`, `GESTIONAR_MAESTROS` | Sí | Sí |
| CONTACTOS | todos los permisos del módulo | Sí | Sí, excepto `FUSIONAR_CONTACTO` |
| EVENTOS | ciclo ordinario | Sí | Sí |
| EVENTOS | `REABRIR_EVENTO`, `ELIMINAR_EVENTO`, `REABRIR_PROGRAMACION` | Sí | No |
| PARTICIPANTES | `CONSULTAR_PARTICIPANTE`, `CREAR_PARTICIPANTE`, `AFILIAR_EMPRESA_EVENTO` | Sí | Sí |
| REPORTES | `CONSULTAR_REPORTE_EVENTO` | Sí | Sí |
| REPORTES | `CONSULTAR_DATOS_PERSONALES_REPORTE`, `EXPORTAR_REPORTE_EVENTO` | Sí | No |
| COMUNICACIONES | consulta, gestión, restauración, prueba y configuración global | Sí | No |

Factiliza exige usuario autenticado, pero no un permiso RBAC específico. El
Portal utiliza `portal_access`, no una cuenta interna.

## Inventario completo de endpoints

Las tablas siguientes reflejan los routers registrados en `app/api/router.py`.
El OpenAPI actual contiene 112 plantillas de ruta y 141 operaciones HTTP. El
endpoint OAuth2 `/api/v1/auth/token` está oculto del esquema intencionalmente.

### Root y Health

| Método | Ruta | Seguridad | Uso |
| --- | --- | --- | --- |
| `GET` | `/` | Pública | Información de la aplicación |
| `GET` | `/api/v1/health` | Pública | Disponibilidad HTTP |
| `GET` | `/api/v1/health/database` | Pública | `SELECT 1` sobre PostgreSQL |

### Autenticación

| Método | Ruta | Seguridad | Uso |
| --- | --- | --- | --- |
| `POST` | `/api/v1/auth/login` | Pública | Login JSON normal o primer ingreso |
| `POST` | `/api/v1/auth/token` | Pública, OAuth form, oculto de OpenAPI | Authorize de Swagger |
| `POST` | `/api/v1/auth/cambiar-password-inicial` | `password_change` | Código + nueva contraseña |
| `POST` | `/api/v1/auth/recuperar-password` | Pública | Solicita código sin enumerar cuentas |
| `POST` | `/api/v1/auth/restablecer-password` | Pública | Restablece con correo y código |

### Usuarios

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/usuarios` | `CREAR_USUARIO` |
| `GET` | `/api/v1/usuarios/roles` | `CREAR_USUARIO` |
| `GET` | `/api/v1/usuarios/tipos-documento` | `CREAR_USUARIO` |
| `GET` | `/api/v1/usuarios/{id_usuario}` | `CREAR_USUARIO` |
| `POST` | `/api/v1/usuarios` | `CREAR_USUARIO` |
| `PATCH` | `/api/v1/usuarios/{id_usuario}` | `ACTUALIZAR_USUARIO` |
| `PATCH` | `/api/v1/usuarios/{id_usuario}/inactivar` | `INACTIVAR_USUARIO` |
| `PATCH` | `/api/v1/usuarios/{id_usuario}/activar` | `INACTIVAR_USUARIO` |

### Grupos y categorías

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/grupos` | `CREAR_GRUPO` |
| `GET` | `/api/v1/grupos/{id_grupo}` | `CREAR_GRUPO` |
| `POST` | `/api/v1/grupos` | `CREAR_GRUPO` |
| `PUT` | `/api/v1/grupos/{id_grupo}` | `CREAR_GRUPO` |
| `PATCH` | `/api/v1/grupos/{id_grupo}/inactivar` | `INACTIVAR_GRUPO` |
| `PATCH` | `/api/v1/grupos/{id_grupo}/reactivar` | `INACTIVAR_GRUPO` |
| `GET` | `/api/v1/grupos/{id_grupo}/categorias` | `CREAR_GRUPO` |
| `POST` | `/api/v1/grupos/{id_grupo}/categorias` | `CREAR_GRUPO` |
| `PATCH` | `/api/v1/grupos/{id_grupo}/categorias/{id_categoria}/quitar` | `INACTIVAR_GRUPO` |
| `GET` | `/api/v1/categorias` | `CREAR_CATEGORIA` |
| `GET` | `/api/v1/categorias/{id_categoria}` | `CREAR_CATEGORIA` |
| `POST` | `/api/v1/categorias` | `CREAR_CATEGORIA` |
| `PUT` | `/api/v1/categorias/{id_categoria}` | `CREAR_CATEGORIA` |
| `PATCH` | `/api/v1/categorias/{id_categoria}/inactivar` | `INACTIVAR_CATEGORIA` |
| `PATCH` | `/api/v1/categorias/{id_categoria}/reactivar` | `INACTIVAR_CATEGORIA` |

### Empresas

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/empresas` | `CREAR_EMPRESA` |
| `GET` | `/api/v1/empresas/{id_empresa}` | `CREAR_EMPRESA` |
| `POST` | `/api/v1/empresas` | `CREAR_EMPRESA` |
| `POST` | `/api/v1/empresas/registro-completo` | `CREAR_EMPRESA` + `CREAR_CONTACTO` |
| `PUT` | `/api/v1/empresas/{id_empresa}` | `CREAR_EMPRESA` |
| `PATCH` | `/api/v1/empresas/{id_empresa}/clasificacion` | `CREAR_EMPRESA` |
| `GET` | `/api/v1/empresas/{id_empresa}/historial` | `CREAR_EMPRESA` |
| `PATCH` | `/api/v1/empresas/{id_empresa}/inactivar` | `INACTIVAR_EMPRESA` |
| `PATCH` | `/api/v1/empresas/{id_empresa}/reactivar` | `INACTIVAR_EMPRESA` |
| `GET` | `/api/v1/empresas/consultar-ruc/{ruc}` | `CREAR_EMPRESA`, obsoleto | Compatibilidad; usar Factiliza |

Filtros de listado: `nombre`, `ruc`, `id_grupo`, `id_categoria`, `estado`.

### Contactos

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/contactos` | `CONSULTAR_CONTACTO` |
| `GET` | `/api/v1/contactos/exportar` | `EXPORTAR_CONTACTO` |
| `GET` | `/api/v1/contactos/{id_contacto}` | `CONSULTAR_CONTACTO` |
| `POST` | `/api/v1/contactos` | `CREAR_CONTACTO` |
| `PATCH` | `/api/v1/contactos/{id_contacto}` | `ACTUALIZAR_CONTACTO` |
| `PATCH` | `/api/v1/contactos/{id_contacto}/empresa` | `CAMBIAR_EMPRESA_CONTACTO` |
| `PATCH` | `/api/v1/contactos/{id_contacto}/estado` | `CAMBIAR_ESTADO_CONTACTO` |
| `POST` | `/api/v1/contactos/fusionar` | `FUSIONAR_CONTACTO` |

Filtros: `search`, `id_empresa`, `id_cargo`, `numero_documento`, `estado`,
`page`, `page_size`. La exportación descarga CSV UTF-8 con BOM.

### Factiliza

| Método | Ruta | Seguridad |
| --- | --- | --- |
| `GET` | `/api/v1/factiliza/ruc/{ruc}` | Usuario activo |
| `GET` | `/api/v1/factiliza/dni/{dni}` | Usuario activo |
| `GET` | `/api/v1/factiliza/carnet-extranjeria/{carnet}` | Usuario activo |

El token Factiliza permanece en el backend. Formatos: RUC 11 dígitos, DNI 8
dígitos y carné alfanumérico de 1 a 20 caracteres. `404` significa documento
no encontrado y `503` proveedor/configuración no disponible.

### Comunicaciones

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/comunicaciones/plantillas` | `CONSULTAR_PLANTILLA_CORREO` |
| `GET` | `/api/v1/comunicaciones/plantillas/{codigo}` | `CONSULTAR_PLANTILLA_CORREO` |
| `PUT` | `/api/v1/comunicaciones/plantillas/{codigo}` | `GESTIONAR_PLANTILLA_CORREO` |
| `POST` | `/api/v1/comunicaciones/plantillas/{codigo}/previsualizar` | `CONSULTAR_PLANTILLA_CORREO` |
| `GET` | `/api/v1/comunicaciones/plantillas/{codigo}/historial` | `CONSULTAR_PLANTILLA_CORREO` |
| `POST` | `/api/v1/comunicaciones/plantillas/{codigo}/restaurar/{version}` | `RESTAURAR_PLANTILLA_CORREO` |
| `GET` | `/api/v1/comunicaciones/configuracion-global` | `CONSULTAR_PLANTILLA_CORREO` |
| `PUT` | `/api/v1/comunicaciones/configuracion-global` | `CONFIGURAR_CORREO_GLOBAL` |
| `POST` | `/api/v1/comunicaciones/plantillas/{codigo}/enviar-prueba` | `ENVIAR_CORREO_PRUEBA` |

Los flujos de negocio no usan un endpoint genérico de envío. Auth y
Participantes cargan la plantilla correspondiente desde PostgreSQL. Contratos,
variables y ejemplos están en
[`app/modules/comunicaciones/README.md`](app/modules/comunicaciones/README.md).

### Maestros

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/maestros/cargos` | `CONSULTAR_MAESTROS` |
| `GET` | `/api/v1/maestros/cargos/{id_cargo}` | `CONSULTAR_MAESTROS` |
| `POST` | `/api/v1/maestros/cargos` | `GESTIONAR_MAESTROS` |
| `PUT` | `/api/v1/maestros/cargos/{id_cargo}` | `GESTIONAR_MAESTROS` |
| `PATCH` | `/api/v1/maestros/cargos/{id_cargo}/estado` | `GESTIONAR_MAESTROS` |
| `GET` | `/api/v1/maestros/areas` | `CONSULTAR_MAESTROS` |
| `GET` | `/api/v1/maestros/areas/{id_area}` | `CONSULTAR_MAESTROS` |
| `POST` | `/api/v1/maestros/areas` | `GESTIONAR_MAESTROS` |
| `PUT` | `/api/v1/maestros/areas/{id_area}` | `GESTIONAR_MAESTROS` |
| `PATCH` | `/api/v1/maestros/areas/{id_area}/estado` | `GESTIONAR_MAESTROS` |
| `GET` | `/api/v1/maestros/beneficios` | `CONSULTAR_MAESTROS` |
| `GET` | `/api/v1/maestros/beneficios/{id_beneficio}` | `CONSULTAR_MAESTROS` |
| `POST` | `/api/v1/maestros/beneficios` | `GESTIONAR_MAESTROS` |
| `PUT` | `/api/v1/maestros/beneficios/{id_beneficio}` | `GESTIONAR_MAESTROS` |
| `PATCH` | `/api/v1/maestros/beneficios/{id_beneficio}/estado` | `GESTIONAR_MAESTROS` |

Los listados aceptan `search`, `estado`, `page` y `page_size`.

### Eventos

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/eventos` | `CONSULTAR_EVENTO` |
| `GET` | `/api/v1/eventos/exportar` | `EXPORTAR_EVENTO` |
| `GET` | `/api/v1/eventos/programaciones` | `CONSULTAR_EVENTO` |
| `GET` | `/api/v1/eventos/{id_evento}` | `CONSULTAR_EVENTO` |
| `POST` | `/api/v1/eventos` | `CREAR_EVENTO` |
| `PUT` | `/api/v1/eventos/{id_evento}` | `ACTUALIZAR_EVENTO` |
| `PUT` | `/api/v1/eventos/{id_evento}/politica` | `ACTUALIZAR_EVENTO` |
| `POST` | `/api/v1/eventos/{id_evento}/programaciones` | `ACTUALIZAR_EVENTO` |
| `GET` | `/api/v1/eventos/{id_evento}/programaciones` | `CONSULTAR_EVENTO` |
| `GET` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}` | `CONSULTAR_EVENTO` |
| `PUT` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}` | `ACTUALIZAR_EVENTO` |
| `PATCH` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/finalizar` | `CAMBIAR_ESTADO_PROGRAMACION` |
| `PATCH` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/reabrir` | `REABRIR_PROGRAMACION` |
| `PATCH` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/inactivar` | `CAMBIAR_ESTADO_PROGRAMACION` |
| `GET` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/dias` | `CONSULTAR_EVENTO` |
| `POST` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/dias` | `ACTUALIZAR_EVENTO` |
| `PATCH` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/dias/{id_dia}` | `ACTUALIZAR_EVENTO` |
| `DELETE` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/dias/{id_dia}` | `ACTUALIZAR_EVENTO` |
| `POST` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/responsables` | `ACTUALIZAR_EVENTO` |
| `GET` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/responsables` | `CONSULTAR_EVENTO` |
| `PATCH` | `/api/v1/eventos/{id_evento}/programaciones/{id_programacion}/responsables/{id_responsable}/estado` | `ACTUALIZAR_EVENTO` |
| `PUT` | `/api/v1/eventos/{id_evento}/flyer` | `ACTUALIZAR_EVENTO` |
| `PATCH` | `/api/v1/eventos/{id_evento}/finalizar` | `CAMBIAR_ESTADO_EVENTO` |
| `PATCH` | `/api/v1/eventos/{id_evento}/reabrir` | `REABRIR_EVENTO` |
| `PATCH` | `/api/v1/eventos/{id_evento}/inactivar` | `CAMBIAR_ESTADO_EVENTO` |
| `DELETE` | `/api/v1/eventos/{id_evento}` | `ELIMINAR_EVENTO` |

El listado de eventos filtra por `search`, rango de política, `estado`,
`id_area`, `page` y `page_size`. El listado de programaciones de un evento
añade `modalidad`. El listado transversal acepta fecha, empresa y estado.

### Participantes internos

| Método | Ruta | Permiso |
| --- | --- | --- |
| `POST` | `/api/v1/participantes/programaciones/{id_programacion_evento}/empresas` | `AFILIAR_EMPRESA_EVENTO` |
| `GET` | `/api/v1/participantes/programaciones/{id_programacion_evento}/empresas` | `CONSULTAR_PARTICIPANTE` |
| `DELETE` | `/api/v1/participantes/empresas/{id_evento_empresa}` | `AFILIAR_EMPRESA_EVENTO` |
| `PATCH` | `/api/v1/participantes/empresas/{id_evento_empresa}/contacto-principal` | `AFILIAR_EMPRESA_EVENTO` |
| `POST` | `/api/v1/participantes/empresas/{id_evento_empresa}/reenviar-codigo` | `AFILIAR_EMPRESA_EVENTO` |
| `POST` | `/api/v1/participantes/programaciones/{id_programacion_evento}/empresas/enviar-codigo-masivo` | `AFILIAR_EMPRESA_EVENTO` |
| `POST` | `/api/v1/participantes/programaciones/{id_programacion_evento}/evento-contactos` | `CREAR_PARTICIPANTE` |
| `POST` | `/api/v1/participantes/programaciones/{id_programacion_evento}/evento-contactos/crear-contacto` | `CREAR_PARTICIPANTE` |
| `POST` | `/api/v1/participantes/programaciones/{id_programacion_evento}/empresas/{id_empresa}/invitados` | `CREAR_PARTICIPANTE` |
| `GET` | `/api/v1/participantes/evento-contactos` | `CONSULTAR_PARTICIPANTE` |
| `GET` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}` | `CONSULTAR_PARTICIPANTE` |
| `PATCH` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}/estado` | `CREAR_PARTICIPANTE` |
| `DELETE` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}` | `CREAR_PARTICIPANTE` |
| `PATCH` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}/asistencia` | `CREAR_PARTICIPANTE` |
| `POST` | `/api/v1/participantes/beneficios/asignar` | `CREAR_PARTICIPANTE` |
| `DELETE` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}/beneficio` | `CREAR_PARTICIPANTE` |
| `GET` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}/beneficios-disponibles` | `CONSULTAR_PARTICIPANTE` |
| `POST` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}/qr/enviar` | `CREAR_PARTICIPANTE` |
| `POST` | `/api/v1/participantes/programaciones/{id_programacion_evento}/qr/enviar-masivo` | `CREAR_PARTICIPANTE` |
| `GET` | `/api/v1/participantes/qr/{codigo_seguro}` | `CONSULTAR_PARTICIPANTE` |
| `POST` | `/api/v1/participantes/qr/{codigo_seguro}/imprimir` | `CREAR_PARTICIPANTE` |
| `POST` | `/api/v1/participantes/evento-contactos/{id_evento_contacto}/reimprimir` | `CREAR_PARTICIPANTE` + credenciales de responsable |

El listado acepta `id_programacion_evento`, `id_empresa`, `id_contacto`,
`search`, `page` y `page_size`.

### Reportes

| Método | Ruta | Permiso |
| --- | --- | --- |
| `GET` | `/api/v1/reportes/eventos` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/filtros` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/kpis` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/grupos` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/categorias` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/empresas` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/participantes` | `CONSULTAR_DATOS_PERSONALES_REPORTE` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/programaciones` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/detalle` | `CONSULTAR_DATOS_PERSONALES_REPORTE` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/dashboard` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/series/mensual` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/beneficios` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/acreditacion` | `CONSULTAR_REPORTE_EVENTO` |
| `GET` | `/api/v1/reportes/eventos/{id_evento}/exportar` | `EXPORTAR_REPORTE_EVENTO` |

Los filtros comunes incluyen programación, grupo, categoría, empresa, cargo,
estados, asistencia, beneficio, coordinación, tipo de participante, modalidad,
búsqueda, rango, alcance y clasificación. `VIGENTE/ACTUAL` son los defaults.
El detalle completo, reglas de cobertura, privacidad, series y Excel está en
[`README_REPORTES.md`](README_REPORTES.md).

### Portal externo

| Método | Ruta | Seguridad |
| --- | --- | --- |
| `POST` | `/api/v1/portal/validar-codigo` | Código de acceso |
| `GET` | `/api/v1/portal/contactos` | Bearer `portal_access` |
| `POST` | `/api/v1/portal/participantes` | Bearer `portal_access` |
| `POST` | `/api/v1/portal/invitados` | Bearer `portal_access` |

El portal nunca acepta un `access` interno como sustituto del token de portal.

## Flujos principales y JSON

### 1. Login normal

```http
POST /api/v1/auth/login
Content-Type: application/json
```

```json
{
  "nombre_usuario": "admin",
  "password": "AdminSeguro1!"
}
```

Respuesta:

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

Usuario inexistente y contraseña incorrecta responden el mismo mensaje
genérico. Un usuario inactivo recibe `401`.

### 2. Crear usuario y completar primer ingreso

El administrador consulta primero roles y tipos de documento, y crea la cuenta:

```http
POST /api/v1/usuarios
Authorization: Bearer <access_token_admin>
```

```json
{
  "id_rol": 2,
  "id_tipo_documento": 1,
  "numero_documento": "76543210",
  "nombre_usuario": "DylanCodip",
  "nombres": "Dylan",
  "apellidos": "Codip",
  "correo": "dylan@empresa.com"
}
```

El backend usa `numero_documento` como contraseña temporal, guarda solo su hash
y crea el usuario con `debe_cambiar_password=true`.

Primer login:

```json
{
  "nombre_usuario": "DylanCodip",
  "password": "76543210"
}
```

El backend no entrega acceso normal. Genera un JWT `password_change`, un código
de seis dígitos ligado al `jti` de ese JWT, guarda solo el hash del código y lo
envía al correo del usuario.

```json
{
  "debe_cambiar_password": true,
  "token_type": "password_change",
  "access_token": null,
  "password_change_token": "eyJ...",
  "codigo_verificacion_requerido": true,
  "correo_enmascarado": "d****@empresa.com"
}
```

El frontend conserva temporalmente `password_change_token` y llama:

```http
POST /api/v1/auth/cambiar-password-inicial
Authorization: Bearer <password_change_token>
```

```json
{
  "codigo_verificacion": "482913",
  "nueva_password": "NuevaPassword1!",
  "confirmar_password": "NuevaPassword1!"
}
```

La operación valida usuario activo, código no usado/no expirado, vínculo con el
intento de login y política de contraseña. En una transacción actualiza el hash,
marca el código usado, cambia `debe_cambiar_password=false`, audita y recién
entonces devuelve un JWT `access`.

### 3. Recuperación de contraseña

```http
POST /api/v1/auth/recuperar-password
```

```json
{
  "correo": "dylan@empresa.com"
}
```

Existe o no la cuenta, la respuesta pública es la misma para evitar enumeración:

```json
{
  "message": "Si existe una cuenta asociada, se enviarán las instrucciones de recuperación."
}
```

```http
POST /api/v1/auth/restablecer-password
```

```json
{
  "correo": "dylan@empresa.com",
  "codigo_verificacion": "482913",
  "nueva_password": "OtraPassword1!",
  "confirmar_password": "OtraPassword1!"
}
```

Un código es de un solo uso. El restablecimiento también completa el primer
ingreso si la cuenta todavía tenía `debe_cambiar_password=true`.

### 4. Grupos, categorías y clasificación

Actualmente `GrupoCreateDTO` exige un ID manual positivo:

```json
{
  "id_grupo": 10,
  "nombre_grupo": "Asociado",
  "descripcion": "Empresas asociadas a CODIP"
}
```

Crear categoría:

```json
{
  "nombre_categoria": "A",
  "descripcion": "Categoría A"
}
```

Asociarla a un grupo:

```http
POST /api/v1/grupos/10/categorias
```

```json
{
  "id_categoria": 3
}
```

La categoría es global y `detalle_categoria` representa la asociación N:M. La
misma categoría puede asociarse a varios grupos, pero no repetirse dentro del
mismo grupo. Quitar una asociación es una baja lógica del detalle.

No se puede inactivar grupo o categoría si empresas activas dependen de ellos.

### 5. Empresa e historial de clasificación

```json
{
  "nombre_empresa": "Empresa Demo SAC",
  "ruc": "20552103816",
  "id_detalle_categoria": 7,
  "razon_social": "Empresa Demo S.A.C.",
  "nombre_comercial": "Demo"
}
```

`PUT /empresas/{id}` solo actualiza nombre, razón social y nombre comercial.
No acepta RUC, ID, clasificación ni estado. La clasificación se cambia aparte:

```json
{
  "id_detalle_categoria": 9,
  "motivo": "Cambio de categoría anual"
}
```

El cambio cierra la vigencia anterior y crea una nueva en
`empresa_historial_clasificacion`. `registro-completo` recibe `{empresa,
contactos}` y crea todo atómicamente; la lista de contactos puede estar vacía.

### 6. Contactos

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
  "correo": "juan@empresa.com",
  "es_contacto_principal": true
}
```

Reglas:

- Empresa, cargo y tipo de documento informados deben estar activos.
- Tipo y número de documento se envían juntos o ambos se omiten.
- El número de documento es único globalmente.
- Género admite `M`, `F` y `OTRO`.
- El celular local debe empezar en 9 y tener 9 dígitos; también admite formato
  internacional `+` de 10 a 15 dígitos. Se eliminan espacios.
- Solo puede existir un contacto principal por empresa a nivel de service; al
  marcar uno, los demás se desmarcan.
- La creación abre la primera vigencia en `contacto_historial_empresa`.

Cambio de empresa:

```json
{
  "id_empresa": 25,
  "motivo": "Cambio laboral"
}
```

La operación cierra la vigencia anterior, abre la nueva, actualiza el contacto
y audita en una transacción. La fusión actual es lógica: conserva el principal,
inactiva el duplicado y cierra su historial; no migra relaciones de módulos
futuros ni elimina físicamente.

### 7. Maestros

Cargo:

```json
{ "nombre_cargo": "Gerente Comercial" }
```

Área:

```json
{
  "nombre_area": "Comunidad",
  "descripcion": "Área responsable de comunidad"
}
```

Beneficio:

```json
{
  "nombre": "Entrada doble",
  "condicion": "Válido según política del evento",
  "tipo_calculo": "POR_EVENTO",
  "personas_por_asignacion": 2
}
```

Los nombres se normalizan, los duplicados se comparan sin distinguir
mayúsculas/espacios y el estado se cambia con `{ "estado": false }` o `true`.
Un beneficio usado por un evento `ABIERTO` no puede inactivarse. Tipos:

- `POR_EVENTO`: toda asignación consume cupo aunque no haya asistencia.
- `POR_ANIO`: consume cuando existe asistencia; asignaciones grupales cuentan
  solo cuando asistieron todos sus miembros.
- `SIN_BENEFICIO`: catálogo técnico; no se ofrece como opción seleccionable.

### 8. Crear evento, política y programaciones

Un Evento contiene identidad, área y política. Las fechas y modalidad viven en
la política/programaciones; crear el Evento **no crea una programación**.

```http
POST /api/v1/eventos
```

```json
{
  "nombre_evento": "Nexo Summit 2026",
  "descripcion": "Encuentro empresarial CODIP",
  "id_area": 2,
  "politica": {
    "fecha_inicio": "2026-10-10",
    "fecha_fin": "2026-10-12",
    "detalles": [
      {
        "id_beneficio": 3,
        "id_categoria": 1,
        "entradas_gratuitas": 3
      }
    ]
  }
}
```

Área, beneficios y categorías deben estar activos. La fecha inicial no puede
estar en el pasado y cada categoría aparece una sola vez en la política. Un
nombre de evento repetido se permite y se registra como advertencia de auditoría.

Crear programación híbrida:

```http
POST /api/v1/eventos/{id_evento}/programaciones
```

```json
{
  "modalidad": "HIBRIDO",
  "enlace_general": "https://meet.example/nexo",
  "lugar": {
    "pais": "Perú",
    "provincia": "Lima",
    "distrito": "Miraflores",
    "direccion": "Av. Principal 123"
  },
  "dias": [
    {
      "fecha": "2026-10-10",
      "hora_inicio": "09:00:00",
      "hora_fin": "18:00:00",
      "enlace": null
    }
  ]
}
```

Un evento puede tener varias programaciones independientes. Reglas:

- Estados de evento y programación: `ABIERTO`, `FINALIZADO`, `INACTIVO`.
- Modalidades: `PRESENCIAL`, `VIRTUAL`, `HIBRIDO`.
- Presencial e híbrido requieren lugar; virtual prohíbe lugar físico.
- Cada programación debe nacer con al menos un día.
- No se repite una fecha dentro de la misma programación.
- `hora_fin`, si existe, debe ser posterior a `hora_inicio`.
- No puede eliminarse el último día.
- Solo evento y programación abiertos admiten edición y gestión de participantes.
- Reabrir exige motivo y permiso administrativo.
- El flyer usa `multipart/form-data`, campo `flyer`, JPG/JPEG/PNG y el límite
  configurado. Su descarga autenticada existe pero está oculta de OpenAPI.
- `DELETE /eventos/{id}` es físico y se bloquea si existen contactos del evento.

Responsable de programación:

```json
{ "id_usuario": 4 }
```

La ruta de estado del responsable recibe `estado=true|false` como query param,
no como JSON.

### 9. Participantes internos

Las empresas se afilian al **evento**. Los participantes, asistencia,
beneficios y QR mantienen contexto por programación.

1. Afiliar empresa activa:

```json
{ "id_empresa": 10 }
```

La afiliación es única por `(evento, empresa)`. La ruta conserva
`id_programacion_evento` para identificar el evento y mantener compatibilidad
con el frontend. Si la empresa tiene un
contacto principal, se asigna automáticamente. Desafiliar usa HTTP `DELETE`
pero realiza baja lógica: inactiva la afiliación, participantes, QR y códigos.
Una afiliación previa puede reactivarse sin duplicar el registro.

2. Asignar o cambiar contacto principal:

```json
{ "id_contacto": 25 }
```

Debe ser un contacto activo de esa empresa. Cambiarlo invalida el código de
portal anterior.

3. Agregar contactos registrados en lote:

```json
{ "ids_contacto": [25, 26] }
```

Todos deben estar activos, pertenecer a empresas afiliadas y no participar ya
en esa programación. El lote es atómico y cada alta genera QR.

4. Crear contacto e inscribirlo en una sola operación:

```json
{
  "contacto": {
    "id_empresa": 10,
    "id_cargo": 3,
    "id_tipo_documento": 1,
    "numero_documento": "71234567",
    "nombres": "Maria",
    "apellidos": "Lopez",
    "genero": "F",
    "celular": "987654321",
    "correo": "maria@empresa.com",
    "es_contacto_principal": false
  }
}
```

5. Invitado sin registro maestro:

```json
{
  "nombres": "Invitado",
  "apellidos": "Temporal",
  "numero_documento": null,
  "correo": "invitado@empresa.com",
  "celular": "987654321"
}
```

Se guarda un snapshot dentro de `evento_contacto`; no crea `contacto`. Límite
actual: 20 invitados sin registrar por empresa y programación. Solo estos
invitados pueden eliminarse físicamente; un contacto registrado se desactiva.

6. Asignar beneficio:

```json
{
  "ids_evento_contacto": [101, 102],
  "id_beneficio": 3
}
```

La cantidad debe coincidir exactamente con `personas_por_asignacion`; todos
deben pertenecer a la misma empresa y programación. El beneficio debe aplicar
a la categoría según la política y tener cupo. Cada participante solo puede
tener una asignación. Sin beneficio asignado queda
`requiere_coordinacion=true`.

7. QR, asistencia y credencial:

- El QR se genera al inscribir y puede enviarse individual o masivamente.
- Escanear consulta datos; imprimir marca asistencia, hora e impresión.
- La primera impresión solo se permite una vez.
- Reimpresión requiere `id_responsable_evento` activo de esa programación y su
  contraseña; la auditoría atribuye la acción a ese responsable.

```json
{
  "id_responsable_evento": 8,
  "password": "PasswordResponsable1!"
}
```

Finalizar o inactivar la programación bloquea todas las escrituras de
participantes, aunque el evento siga abierto.

### 10. Código de empresa y Portal

El operador envía o reenvía un código desde Participantes. Requisitos: empresa
afiliada, contacto principal con correo y programación con días. El código:

- es aleatorio hexadecimal de 8 caracteres;
- se guarda únicamente como HMAC;
- invalida códigos previos de la afiliación;
- expira a las 23:59:59 de `America/Lima` del día anterior al primer día
  programado, evitando que un código emitido ese mismo día nazca vencido;
- llega por correo con enlace `${FRONTEND_BASE_URL}/portal-invitados?codigo=...`.

El contacto principal valida:

```http
POST /api/v1/portal/validar-codigo
```

```json
{ "codigo": "A1B2C3D4" }
```

La respuesta entrega un `portal_token` limitado a la afiliación. El frontend
lo usa como Bearer en `/portal/contactos`, `/portal/participantes` y
`/portal/invitados`.

Selección de contactos y beneficios:

```json
{
  "selecciones": [
    { "id_contacto": 25, "id_beneficio": 3 },
    { "id_contacto": 26, "id_beneficio": 3 }
  ]
}
```

El portal solo lista contactos activos de la empresa, informa cuáles ya fueron
agregados y calcula beneficios disponibles. En cada request vuelve a validar
que evento y programación sigan abiertos. No utiliza permisos internos ni
permite operar otra empresa.

## Auditoría

Los services escriben en `auditoria` dentro de la misma transacción que la
operación crítica. Se registran actor, módulo, entidad, ID, acción, valores
anterior/nuevo y motivo cuando corresponde.

No se auditan contraseñas, hashes de contraseña, códigos planos, JWT, app
passwords ni tokens Factiliza. Los flujos externos del Portal pueden auditar
con `id_usuario=null` porque no representan un usuario interno.

## Códigos HTTP

| Código | Significado habitual |
| --- | --- |
| `200` | Operación o consulta correcta |
| `201` | Recurso creado |
| `204` | Eliminación/desafiliación sin body |
| `400` | Regla o transición inválida |
| `401` | Credenciales/JWT inválidos o usuario interno inactivo |
| `403` | Sin permiso, código de portal inválido o contraseña de responsable incorrecta |
| `404` | Entidad o documento externo no encontrado |
| `409` | Duplicado, estado no editable, dependencia o cupo agotado |
| `413` | Flyer supera el tamaño permitido |
| `422` | DTO, path o query con formato inválido |
| `503` | PostgreSQL, SMTP o Factiliza no disponible |

El frontend debe mostrar `detail` y no inferir una única estructura para todos
los errores: FastAPI devuelve string, lista de validaciones o detalles `422`
según el origen.

## Política de borrado

La norma general es conservar historia mediante estado. No hay DELETE físico
para usuarios, grupos, categorías, empresas, contactos ni maestros.

Excepciones implementadas:

- Evento: borrado físico solo sin `evento_contacto` dependientes.
- Día: borrado físico, conservando al menos un día por programación.
- Invitado sin registrar: borrado físico; contactos maestros se desactivan.
- Asignación de beneficio: se elimina para permitir reasignación.
- Desafiliación de empresa usa `DELETE` HTTP, pero persiste la relación inactiva.

Antes de diseñar otro borrado físico, inspeccione las FK reales con la
herramienta de solo lectura:

```bash
.venv/bin/python scripts/check_delete_dependencies.py \
  --table grupo \
  --id 10 \
  --include-empty
```

Códigos de salida: `0` puede borrarse, `1` tabla/registro inválido y `2` hay
dependencias. El script no ejecuta `DELETE` ni crea objetos en PostgreSQL.

## Tests

La colección actual contiene **376 tests**. Las pruebas de integración usan la
misma aplicación ASGI y PostgreSQL, pero crean un esquema temporal
`test_usuarios_<uuid>` por prueba y lo eliminan con `DROP SCHEMA ... CASCADE`.
La cuenta configurada necesita permisos para crear y eliminar schemas. Nunca
apunte los tests a producción.

Última verificación de esta revisión: **376 tests aprobados** contra un
PostgreSQL local aislado, `376 passed in 548.82s`. También se comprobó el import
de la aplicación, OpenAPI con 112 rutas/141 operaciones y la ejecución
idempotente de `create_db.py` y `bootstrap_security.py`.

```bash
# Colección sin ejecutar
.venv/bin/python -m pytest --collect-only -q

# Por módulo
.venv/bin/python -m pytest test/modules/usuarios -q
.venv/bin/python -m pytest test/modules/grupos test/modules/categorias -q
.venv/bin/python -m pytest test/modules/empresas -q
.venv/bin/python -m pytest test/modules/contactos -q
.venv/bin/python -m pytest test/modules/factiliza -q
.venv/bin/python -m pytest test/modules/maestros -q
.venv/bin/python -m pytest test/modules/eventos -q
.venv/bin/python -m pytest test/modules/participantes -q
.venv/bin/python -m pytest test/modules/comunicaciones -q
.venv/bin/python -m pytest test/modules/reportes -q
.venv/bin/python -m pytest test/scripts -q

# Regresión completa
.venv/bin/python -m pytest -q
```

Cobertura relevante:

- Usuarios: RBAC, JWT, inactivación inmediata, DNI temporal, códigos ligados a
  intento, expiración, un solo uso, política, SMTP, consola y auditoría.
- Catálogos/empresas/contactos: duplicados, estados, dependencias, historiales,
  atomicidad, normalización, filtros, exportación y contacto principal único.
- Maestros: cargos, áreas y beneficios; uso en eventos abiertos y tipos de cupo.
- Eventos: política, fechas, modalidades, múltiples programaciones, días,
  responsables, flyer, estados, búsqueda, exportación y rollback.
- Participantes/Portal: afiliación y desafiliación, lotes atómicos, invitados,
  códigos, portal, beneficios por evento/año, QR, asistencia, impresión,
  reimpresión y bloqueo de programaciones cerradas.
- Factiliza: mapeo, formatos, proveedor no disponible y ausencia de token.
- Comunicaciones: RBAC, CRUD versionado, historial, restauración, preview,
  seguridad HTML/Jinja, remitente global, envío de prueba y metadatos sin secretos.
- Reportes: filtros padre-hijo, agregaciones, clasificación actual/histórica,
  empresas vacías, PII, dashboard, series, beneficios, acreditación, Excel,
  consistencia, query count, performance y ausencia de secretos.
- Scripts: inspección de dependencias de borrado.

## Verificaciones rápidas

```bash
# Importar aplicación y listar tablas registradas
.venv/bin/python -c "import app.main; from app.db.base import Base; print(sorted(Base.metadata.tables))"

# Comprobar rutas desde OpenAPI sin levantar servidor
.venv/bin/python -c "from app.main import app; print('\n'.join(sorted(app.openapi()['paths'])))"

# Comprobar sintaxis/imports
.venv/bin/python -m compileall -q app scripts
```

## Incompatibilidades y límites conocidos

### SQL histórico

`SistemaEventosCODIP_postgresql.sql` no es un instalador compatible con el
runtime actual. Entre otras diferencias:

- usa nombres camelCase que PostgreSQL convierte a minúsculas (`idUsuario` ->
  `idusuario`), mientras los models esperan snake_case (`id_usuario`);
- `permiso` histórico no tiene `codigo` y varias columnas cambian de nombre;
- no incluye auditoría ni historiales actuales;
- `beneficio` no incluye `tipo_calculo` ni `personas_por_asignacion`;
- `contacto` no incluye género y obliga cargo/documento;
- Evento y Programación usan booleanos y estructura distinta a los enums y
  múltiples programaciones actuales;
- no representa flyer, horarios, contacto principal, invitado snapshot,
  códigos de portal ni reglas/constraints actuales.

La solución correcta es una migración revisada o recrear una **base vacía de
desarrollo** con `scripts/create_db.py`; no añadir casts o aliases improvisados.

Para bases creadas con la primera versión del módulo Eventos existe una
migración explícita e idempotente. Copia `evento.fecha_inicio/fecha_fin` a una
`politica_evento`, agrega las relaciones actuales, conserva las columnas
históricas como opcionales y convierte el estado booleano de las programaciones
al enum vigente:

```bash
# Si la base contiene exactamente una área, se detecta automáticamente
.venv/bin/python scripts/migrate_eventos_schema.py

# Si contiene varias áreas, se debe elegir conscientemente la asignada a los
# eventos legados
.venv/bin/python scripts/migrate_eventos_schema.py --default-area-id 1
```

El script no se ejecuta durante el arranque ni desde `create_db.py`. Antes de
modificar datos toma un bloqueo transaccional, valida la forma del esquema y
hace rollback completo ante cualquier incompatibilidad.

### Decisiones actuales que una IA no debe asumir distintas

- `POST /grupos` recibe `id_grupo` manual y el service persiste ese valor; el
  flujo HTTP actual no delega su generación a PostgreSQL.
- Los GET de Grupos, Categorías y Empresas reutilizan permisos de creación; no
  existen permisos de consulta separados para esos módulos.
- No existe endpoint CRUD para roles, permisos ni auditorías.
- Un Evento y sus Programaciones tienen estados independientes.
- Fechas operativas pertenecen a política/días; no al body raíz del Evento.
- Participantes se asocian a `id_programacion_evento`, no directamente a
  `id_evento`.
- No existe una tabla/model `Participante`; el registro vigente es
  `evento_contacto`.
- Reportes es de solo lectura salvo auditoría de exportación y no tiene models
  ni tablas propias.
- La asistencia reportada es por participante-programación; no por día. En
  programación híbrida no se infiere el canal individual.
- La fusión de contactos no migra relaciones; inactiva el duplicado.
- `create_all()` no actualiza esquemas ya existentes.
- No hay un framework general de migraciones configurado; la migración puntual
  de Eventos se ejecuta mediante `scripts/migrate_eventos_schema.py`.

La auditoría de cobertura CRUD complementaria está en `CRUD_COVERAGE.md`.
