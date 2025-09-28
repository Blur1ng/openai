from fastapi import FastAPI
from api.openai_endpoints import openai
import uvicorn

app = FastAPI()

app.include_router(openai)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
