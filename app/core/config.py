from functools import lru_cache

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
    return Settings()


settings = get_settings()