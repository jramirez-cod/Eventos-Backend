from functools import lru_cache

from pydantic import Field, SecretStr
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
    frontend_base_url: str = "http://localhost:4200"
    cors_allowed_origins: str = (
        "http://localhost:4200,http://127.0.0.1:4200,"
        "http://localhost:8001,http://127.0.0.1:8001"
    )
    cors_allow_localhost_any_port: bool = False

    # Archivos de Eventos
    event_flyer_upload_dir: str = "uploads/eventos"
    event_flyer_max_bytes: int = Field(default=5_242_880, gt=0)

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
    portal_access_token_expire_minutes: int = 60
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

    # Consultas de documentos (Factiliza)
    factiliza_base_url: str = "https://api.factiliza.com/v1"
    factiliza_api_token: SecretStr = SecretStr("")
    factiliza_timeout_seconds: float = Field(default=15.0, gt=0)

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

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip().rstrip("/")
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]

    @property
    def cors_origin_regex(self) -> str | None:
        if not self.cors_allow_localhost_any_port:
            return None
        return r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"


@lru_cache
def get_settings() -> Settings:
    # pydantic BaseSettings reads values from environment; static type checker
    # may require explicit constructor args. Ignore arg-type here.
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
