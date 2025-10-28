from fastapi import FastAPI
from api.openai_endpoints import openai
import uvicorn
from api.core.db_con import engine, Base
from pathlib import Path

app = FastAPI()

#app.include_router(openai)
#
#@app.on_event("startup")
#async def on_startup():
#    async with engine.begin() as conn:
#        await conn.run_sync(Base.metadata.create_all)
#        
#if __name__ == "__main__":
#    uvicorn.run(app, host="0.0.0.0", port=8000)


import sys
import os

sys.path.insert(0, '/app') 

import redis
from rq import Queue
from pathlib import Path

from api.broker.task import add_prompt

redis_conn = redis.Redis(host='redis', port=6379)
q = Queue('to_aimodel', connection=redis_conn)

def send_task():
    with Path("api/prompts/code.txt").open("r") as code_file:
        with Path("api/prompts/architecture.txt").open("r") as architecture_file:
            architecture_data = {
                "id": 666,
                "ai_model": "chatgpt",
                "prompt_name": "test",
                "prompt": f"{architecture_file.read()}",
                "request": f"{code_file.read()}",
                "model": "gpt-4o-mini"
            }
            # Pass the function object directly, NOT as a string
            job = q.enqueue(add_prompt, architecture_data)
            print(f"Задача поставлена в очередь: {job.id}")
            return job.id

if __name__ == "__main__":
    job_id = send_task()
    print(f"Job ID: {job_id}")