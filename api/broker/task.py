import logging
from fastapi                    import HTTPException
from api.core.db_con            import RequestData, JobResult, async_session
from openai_.openai_client      import ChatGPTClient
from openai_.deepseek_client    import DeepSeekClient
from openai_.sonnet_client      import SonnetClient
from api.core.security          import SECRET_KEY_OPENAI, SECRET_KEY_DEEPSEEK, SECRET_KEY_SONNET
from pathlib                    import Path
from api.schemas.openapi_schema import request_form
from sqlalchemy.ext.asyncio     import AsyncSession
from sqlalchemy                 import select, create_engine
from sqlalchemy.orm             import sessionmaker, Session
from datetime                   import datetime
import asyncio

import redis
from rq import Queue

# Создаём синхронный engine для воркеров
from api.core.security import POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_PORT
SYNC_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@pg:{POSTGRES_PORT}/{POSTGRES_DB}"
sync_engine = create_engine(SYNC_DATABASE_URL)
SyncSessionLocal = sessionmaker(bind=sync_engine)

def add_prompt_task(data: dict):
    """Синхронная версия для RQ воркеров"""
    prompt_data: request_form  = data["prompt_data"]
    prompt: str = data["prompt"]
    prompt_name: str = data.get("prompt_name", "result")
    job_id: str = data.get("job_id")
    
    # Используем синхронную сессию для воркера
    db = SyncSessionLocal()
    
    try:
        # Обновляем статус на 'started'
        job_record = db.query(JobResult).filter(JobResult.job_id == job_id).first()
        if job_record:
            job_record.status = 'started'
            db.commit()
        else:
            logging.warning(f"Job {job_id} not found in database")
    except Exception as e:
        logging.warning(f"Could not update job status to started: {e}")
        db.rollback()
    

    ai_model = prompt_data.ai_model
        
    if ai_model == "chatgpt":
        chatgpt_client = ChatGPTClient(
            api_key=SECRET_KEY_OPENAI,
            model_name=prompt_data.model,
            embeddings_model_name="text-embedding-3-small",
            system_prompt=prompt,
            mathematical_percent=10
        )

        # Проверяем размер запроса
        request_tokens = len(chatgpt_client.tokenize_text(prompt_data.request))
        system_tokens = len(chatgpt_client.tokenize_text(prompt)) if prompt else 0
        total_input_tokens = request_tokens + system_tokens

        logging.info(f"Request tokens: {request_tokens}, System tokens: {system_tokens}, Total: {total_input_tokens}, Max: {chatgpt_client.max_tokens}")

        # Если запрос помещается целиком
        if total_input_tokens <= chatgpt_client.max_tokens:
            result = chatgpt_client.send_full_request_with_usage(prompt_data.request)
            texts = result["text"]
            total_usage = result["usage"]
            logging.info(f"Sent as single request. Tokens used: {total_usage['total_tokens']}")
        # Если не помещается - разбиваем на чанки
        else:
            logging.warning(f"Request too large ({total_input_tokens} tokens), splitting into chunks")

            # Размер чанка = 80% от доступного места (оставляем место на ответ)
            chunk_size = int(chatgpt_client.max_tokens * 0.8) - system_tokens
            chunks = chatgpt_client.split_text_into_chunks(prompt_data.request, chunk_size=chunk_size)

            all_texts = []
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

            for idx, chunk in enumerate(chunks, 1):
                logging.info(f"Processing chunk {idx}/{len(chunks)}")

                chunk_message = f"[Часть {idx} из {len(chunks)}]\n\n{chunk}"

                result = chatgpt_client.send_message_with_usage(chunk_message)
                all_texts.append(result["text"])

                for key in total_usage:
                    total_usage[key] += result["usage"].get(key, 0)

            texts = '\n\n'.join(all_texts)  
            logging.info(f"Completed processing {len(chunks)} chunks. Total tokens: {total_usage['total_tokens']}")

    elif ai_model == "deepseek":
        client = DeepSeekClient(
            api_key=SECRET_KEY_DEEPSEEK,
            model_name=prompt_data.model,
            system_prompt=prompt,
            mathematical_percent=10
        )
        
        request_tokens = len(client.tokenize_text(prompt_data.request))
        system_tokens = len(client.tokenize_text(prompt)) if prompt else 0
        total_input_tokens = request_tokens + system_tokens
        
        logging.info(f"DeepSeek request tokens: {request_tokens}, System tokens: {system_tokens}, Total: {total_input_tokens}, Max: {client.max_tokens}")
        
        # Если запрос помещается целиком
        if total_input_tokens <= client.max_tokens:
            result = client.send_full_request_with_usage(prompt_data.request)
            texts = result["text"]
            total_usage = result["usage"]
            logging.info(f"DeepSeek sent as single request. Tokens used: {total_usage['total_tokens']}")
        
        # Если не помещается - разбиваем на чанки
        else:
            logging.warning(f"DeepSeek request too large ({total_input_tokens} tokens), splitting into chunks")
            
            # Размер чанка = 80% от доступного места (оставляем место на ответ)
            chunk_size = int(client.max_tokens * 0.8) - system_tokens
            chunks = client.split_text_into_chunks(prompt_data.request, chunk_size=chunk_size)
            
            all_texts = []
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            
            for idx, chunk in enumerate(chunks, 1):
                logging.info(f"Processing DeepSeek chunk {idx}/{len(chunks)}")
                
                chunk_message = f"[Часть {idx} из {len(chunks)}]\n\n{chunk}"
                result = client.send_message_with_usage(chunk_message)
                all_texts.append(result["text"])
                
                for key in total_usage:
                    total_usage[key] += result["usage"].get(key, 0)
            
            texts = '\n\n'.join(all_texts)
            logging.info(f"DeepSeek completed {len(chunks)} chunks. Total tokens: {total_usage['total_tokens']}")
    
    elif ai_model == "sonnet":
        client = SonnetClient(
            api_key=SECRET_KEY_SONNET,
            model_name=prompt_data.model,
            system_prompt=prompt,
            mathematical_percent=10
        )
        
        request_tokens = client.count_tokens(prompt_data.request)
        system_tokens = client.count_tokens(prompt) if prompt else 0
        total_input_tokens = request_tokens + system_tokens
        
        logging.info(f"Claude request tokens: ~{request_tokens}, System tokens: ~{system_tokens}, Total: ~{total_input_tokens}, Max: {client.max_tokens}")
        
        if total_input_tokens <= client.max_tokens:
            result = client.send_full_request_with_usage(prompt_data.request)
            texts = result["text"]
            total_usage = result["usage"]
            logging.info(f"Claude sent as single request. Tokens used: {total_usage['total_tokens']}")
        
        else:
            logging.warning(f"Claude request too large (~{total_input_tokens} tokens), splitting into chunks")
            result = client.send_chunked_message_with_usage(prompt_data.request)
            texts = result["text"]
            total_usage = result["usage"]
            logging.info(f"Claude completed chunked request. Total tokens: {total_usage['total_tokens']}")
        
    else:
        raise HTTPException(status_code=400, detail="Нет такой AI модели")
    
    # Сохраняем результат в БД (синхронно)
    job_record = db.query(JobResult).filter(JobResult.job_id == job_id).first()
    
    if job_record:
        job_record.result_text = texts
        job_record.prompt_tokens = total_usage["prompt_tokens"]
        job_record.completion_tokens = total_usage["completion_tokens"]
        job_record.total_tokens = total_usage["total_tokens"]
        job_record.status = 'finished'
        job_record.completed_at = datetime.utcnow()
        db.commit()
        logging.info(f"Job {job_id} saved to database successfully")
    
    db.close()
    
    return {
        "ai_model": prompt_data.ai_model,
        "model": prompt_data.model,
        "prompt_name": prompt_name,
        "request_statistics": {
            "prompt_tokens": total_usage["prompt_tokens"],
            "completion_tokens": total_usage["completion_tokens"],
            "total_tokens": total_usage["total_tokens"],
        }
    }
    
    


async def send_task(request_data: request_form, db: AsyncSession):
    redis_conn = redis.Redis(host='redis', port=6379)
    q = Queue('to_aimodel', connection=redis_conn)
    
    prompts_dir = Path("api/prompts")
    prompt_files = list(prompts_dir.glob("*.txt"))
    
    if not prompt_files:
        raise HTTPException(status_code=500, detail="Не найдено ни одного промпта в папке api/prompts")
    
    jobs = []
    for prompt_file in prompt_files:
        with prompt_file.open("r") as _file:
            prompt_content = _file.read()
        
        # Создаём запись в БД сначала (чтобы получить job_id)
        job_record = JobResult(
            job_id="",  # временно пустое, обновим после создания job
            ai_model=request_data.ai_model,
            model=request_data.model,
            prompt_name=prompt_file.stem,
            request_code=request_data.request,
            status='queued'
        )
        db.add(job_record)
        await db.flush()  # получаем ID до commit
        
        # Сначала создаём job без job_id, чтобы получить ID
        data = {
            "prompt_data": request_data,
            "prompt": prompt_content,
            "prompt_name": prompt_file.stem,
            "job_id": None  
        }
        job = q.enqueue(add_prompt_task, data)
        
        # Теперь обновляем data с правильным job_id и пересоздаём job
        data["job_id"] = job.id
        job_record.job_id = job.id
        
        # Отменяем первую задачу и создаём новую с правильным job_id
        job.cancel()
        job = q.enqueue(add_prompt_task, data)
        
        print(f"Задача поставлена в очередь: {job.id} (промпт: {prompt_file.name})")
        jobs.append({
            "job_id": job.id,
            "prompt_name": prompt_file.stem
        })
    
    await db.commit()
    
    return {"jobs": jobs, "total": len(jobs)}
            
