from pydantic import BaseModel, ConfigDict

class prompt_form(BaseModel):
    id: int | None = None
    prompt_name: str
    prompt: str
    request: str
    model: str

    model_config = ConfigDict(from_attributes=True)
