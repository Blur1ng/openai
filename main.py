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


from api.broker.task import add_prompt
import redis
from rq import Queue, Worker


redis_conn = redis.Redis(host='redis', port=6379)
q = Queue('to_aimodel', connection=redis_conn)

queues = ['to_aimodel']

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
    job1 = q.enqueue(add_prompt, architecture_data)

    worker = Worker(queues, connection=redis_conn)
    print("Воркер запущен...")
    worker.work()



if __name__ == "__main__":
    print(send_task())
