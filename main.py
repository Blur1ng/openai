from fastapi import FastAPI
from api.openai_endpoints import ai_model
from api.prompt_endpoints import prompt_router
import uvicorn
from api.core.db_con import engine, Base

app = FastAPI()

app.include_router(ai_model)
app.include_router(prompt_router)

@app.on_event("startup")
async def on_startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

