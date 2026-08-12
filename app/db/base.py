from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


from app.modules.auditoria import models as auditoria_models  # noqa: E402,F401
from app.modules.usuarios import models as usuarios_models  # noqa: E402,F401
