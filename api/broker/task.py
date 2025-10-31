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
from sqlalchemy                 import select
from datetime                   import datetime

import redis
from rq import Queue

async def add_prompt_task(data: dict):
    prompt_data: request_form  = data["prompt_data"]
    prompt: str = data["prompt"]
    prompt_name: str = data.get("prompt_name", "result")
    job_id: str = data.get("job_id")
    
    # Создаём свою сессию БД для воркера
    async with async_session() as db:
        try:
            # Обновляем статус на 'started'
            result = await db.execute(
                select(JobResult).where(JobResult.job_id == job_id)
            )
            job_record = result.scalar_one_or_none()
            if job_record:
                job_record.status = 'started'
                await db.commit()
        except Exception as e:
            logging.warning(f"Could not update job status to started: {e}")
    

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
    


    # Сохраняем результат в БД
    async with async_session() as db:
        try:
            result = await db.execute(
                select(JobResult).where(JobResult.job_id == job_id)
            )
            job_record = result.scalar_one_or_none()
            
            if job_record:
                job_record.result_text = texts
                job_record.prompt_tokens = total_usage["prompt_tokens"]
                job_record.completion_tokens = total_usage["completion_tokens"]
                job_record.total_tokens = total_usage["total_tokens"]
                job_record.status = 'finished'
                job_record.completed_at = datetime.utcnow()
                await db.commit()
                logging.info(f"Job {job_id} saved to database successfully")
        except Exception as e:
            logging.error(f"Failed to save job {job_id} to database: {e}")

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
    prompt_files = list(prompts_dir.glob("*.md"))
    
    if not prompt_files:
        raise HTTPException(status_code=500, detail="Не найдено ни одного промпта в папке api/prompts")
    
    jobs = []
    for prompt_file in prompt_files:
        with prompt_file.open("r") as _file:
            prompt_content = _file.read()
        
        # Сначала ставим задачу в очередь RQ
        data = {
            "prompt_data": request_data,
            "prompt": prompt_content,
            "prompt_name": prompt_file.stem,
            "job_id": None  # заполним после создания job
        }
        job = q.enqueue(add_prompt_task, data)
        
        # Обновляем data с реальным job_id
        data["job_id"] = job.id
        # Обновляем задачу в Redis с правильным job_id
        job = q.enqueue(add_prompt_task, data)
        
        # Создаём запись в БД
        job_record = JobResult(
            job_id=job.id,
            ai_model=request_data.ai_model,
            model=request_data.model,
            prompt_name=prompt_file.stem,
            request_code=request_data.request,
            status='queued'
        )
        db.add(job_record)
        
        print(f"Задача поставлена в очередь: {job.id} (промпт: {prompt_file.name})")
        jobs.append({
            "job_id": job.id,
            "prompt_name": prompt_file.stem
        })
    
    await db.commit()
    
    return {"jobs": jobs, "total": len(jobs)}
            
