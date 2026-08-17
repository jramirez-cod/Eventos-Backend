from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """
    Configuracion general de la aplicacion.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # PostgreSQL
    pghost: str = "localhost"
    pgport: int = 5432
    pgdatabase: str
    pguser: str
    pgpassword: str

    # Aplicación
    app_name: str = "Sistema Eventos API"
    app_version: str = "1.0.0"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = False

    # Seguridad
    secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "eventos-codip-api"
    access_token_expire_minutes: int = 60
    password_change_token_expire_minutes: int = 15
    initial_password_code_expire_minutes: int = 10
    initial_password_code_length: int = 6
    temporary_dni_length: int = 8
    recovery_token_expire_minutes: int = 30
    password_min_length: int = 8
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_number: bool = True
    password_require_special: bool = True
    password_hash_argon2_time_cost: int = 3
    password_hash_argon2_memory_cost: int = 65536
    password_hash_argon2_parallelism: int = 4

    # Correo SMTP
    email_enabled: bool = False
    email_print_code_to_console: bool = False
    email_sender_user_id: int = 1
    email_from_name: str = "Sistema Eventos CODIP"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_starttls: bool = True
    smtp_timeout_seconds: int = 20
    smtp_app_password: SecretStr = SecretStr("")

    @property
    def database_url(self) -> URL:
        """
        Construye la URL sin concatenar manualmente la contraseña.
        URL.create protege correctamente contraseñas que contengan
        caracteres especiales como @, :, / o #.
        """
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.pguser,
            password=self.pgpassword,
            host=self.pghost,
            port=self.pgport,
            database=self.pgdatabase,
        )


@lru_cache
def get_settings() -> Settings:
    # pydantic BaseSettings reads values from environment; static type checker
    # may require explicit constructor args. Ignore arg-type here.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
