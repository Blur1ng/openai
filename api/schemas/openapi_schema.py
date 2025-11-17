from pydantic import BaseModel, ConfigDict

class prompt_form(BaseModel):
    id: int | None = None
    ai_model: str
    prompt_name: str
    prompt: str
    request: str
    model: str

    model_config = ConfigDict(from_attributes=True)

class request_form(BaseModel):
    id: int | None = None
    ai_model: str
    request: str
    model: str
    callback_url: str | None = None

    model_config = ConfigDict(from_attributes=True)