"""
Script rápido para crear un usuario administrador
Uso: python scripts/crear_admin_rapido.py
"""
import asyncio
import sys
from pathlib import Path

# Fix para Windows: usar SelectorEventLoop en lugar de ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from app.core.security import hash_password
from app.db.session import AsyncSessionLocal
from app.modules.usuarios.models import Rol, Modulo, Permiso, RolPermisoModulo, TipoDocumento, Usuario


async def crear_admin():
    async with AsyncSessionLocal() as session:
        # 1. Crear o obtener rol admin
        rol = await session.scalar(
            select(Rol).where(Rol.nombre_rol == "ADMINISTRADOR_EVENTOS")
        )
        if not rol:
            rol = Rol(
                nombre_rol="ADMINISTRADOR_EVENTOS",
                descripcion="Administrador del Sistema",
                estado=True
            )
            session.add(rol)
            await session.commit()
            await session.refresh(rol)
            print(f"✅ Rol creado: id={rol.id_rol}")
        else:
            print(f"ℹ️  Rol ya existe: id={rol.id_rol}")

        # 1.5 Crear o obtener tipo de documento DNI
        tipo_documento = await session.scalar(
            select(TipoDocumento).where(TipoDocumento.nombre_documento == "DNI")
        )
        if not tipo_documento:
            tipo_documento = TipoDocumento(
                nombre_documento="DNI",
                longitud=8,
                estado=True
            )
            session.add(tipo_documento)
            await session.commit()
            await session.refresh(tipo_documento)
            print(f"✅ Tipo de documento creado: id={tipo_documento.id_tipo_documento}")
        else:
            print(f"ℹ️  Tipo de documento ya existe: id={tipo_documento.id_tipo_documento}")

        # 2. Crear o obtener módulo usuarios
        modulo = await session.scalar(
            select(Modulo).where(Modulo.nombre_modulo == "USUARIOS")
        )
        if not modulo:
            modulo = Modulo(
                nombre_modulo="USUARIOS",
                descripcion="Gestión de Usuarios",
                estado=True
            )
            session.add(modulo)
            await session.commit()
            await session.refresh(modulo)
            print(f"✅ Módulo creado: id={modulo.id_modulo}")
        else:
            print(f"ℹ️  Módulo ya existe: id={modulo.id_modulo}")

        # 3. Crear permisos
        permisos_data = [
            ("CREAR_USUARIO", "Crear Usuario"),
            ("INACTIVAR_USUARIO", "Inactivar Usuario")
        ]
        
        for codigo, nombre in permisos_data:
            permiso = await session.scalar(
                select(Permiso).where(Permiso.codigo == codigo)
            )
            if not permiso:
                permiso = Permiso(
                    codigo=codigo,
                    nombre_permiso=nombre,
                    descripcion=f"Permite {nombre.lower()}",
                    estado=True
                )
                session.add(permiso)
                await session.commit()
                await session.refresh(permiso)
                print(f"✅ Permiso creado: {codigo}")
                
                # Asignar permiso al rol
                relacion = RolPermisoModulo(
                    id_rol=rol.id_rol,
                    id_modulo=modulo.id_modulo,
                    id_permiso=permiso.id_permiso
                )
                session.add(relacion)
                await session.commit()
            else:
                print(f"ℹ️  Permiso ya existe: {codigo}")

        # 4. Crear usuario admin
        usuario = await session.scalar(
            select(Usuario).where(Usuario.nombre_usuario == "admin")
        )
        
        if not usuario:
            # Password: Admin123!
            password = "Admin123!"
            numero_documento = "00000000"

            usuario = Usuario(
                id_rol=rol.id_rol,
                id_tipo_documento=tipo_documento.id_tipo_documento,
                numero_documento=numero_documento,
                nombre_usuario="admin",
                password_hash=hash_password(password),
                nombres="Administrador",
                apellidos="CODIP",
                correo="codipcorporativo@gmail.com",
                estado=True,
                debe_cambiar_password=False
            )
            session.add(usuario)
            await session.commit()
            await session.refresh(usuario)

            print("\n" + "="*50)
            print("✅ USUARIO ADMINISTRADOR CREADO")
            print("="*50)
            print(f"Usuario: admin")
            print(f"Password: {password}")
            print(f"Documento: DNI {numero_documento}")
            print(f"Correo: codipcorporativo@gmail.com")
            print(f"ID: {usuario.id_usuario}")
            print("="*50)
        else:
            print(f"\n⚠️  Usuario 'admin' ya existe (id={usuario.id_usuario})")


if __name__ == "__main__":
    print("🚀 Creando usuario administrador...\n")
    asyncio.run(crear_admin())
    print("\n✅ Proceso completado!")
