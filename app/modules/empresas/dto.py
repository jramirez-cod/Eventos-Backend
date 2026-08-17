from pydantic import BaseModel, ConfigDict


class EmpresaDependienteDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id_empresa: int
    nombre_empresa: str
    ruc: str
