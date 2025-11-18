import logging
from fastapi                    import HTTPException
from api.core.db_con            import RequestData, JobResult, PromptTemplate, BatchStatus, async_session
from openai_.openai_client      import ChatGPTClient
from openai_.deepseek_client    import DeepSeekClient
from openai_.sonnet_client      import SonnetClient
from api.core.security          import SECRET_KEY_OPENAI, SECRET_KEY_DEEPSEEK, SECRET_KEY_SONNET
from api.schemas.openapi_schema import request_form
from sqlalchemy.ext.asyncio     import AsyncSession
from sqlalchemy                 import select, create_engine
from sqlalchemy.orm             import sessionmaker, Session
from datetime                   import datetime
import asyncio
import uuid
import requests

import redis
from rq import Queue

# синхронный engine для воркеров
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
    batch_id: str = data.get("batch_id")

    db = SyncSessionLocal()
    
    try:
        job_record = db.query(JobResult).filter(JobResult.job_id == job_id).first()
        if job_record:
            job_record.status = 'started'
            db.commit()
            logging.info(f"Job {job_id} ({prompt_name}) started")
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
        logging.info(f"Job {job_id} ({prompt_name}) saved to database successfully")
        
        # Обновляем статус батча
        check_and_update_batch_status(batch_id, db)
    else:
        logging.error(f"Job {job_id} not found in database after processing")
    
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
    

def check_and_update_batch_status(batch_id: str, db: Session):
    """Проверяет статус всех задач в батче и обновляет BatchStatus"""
    try:
        # Получаем статус батча
        batch_status = db.query(BatchStatus).filter(BatchStatus.batch_id == batch_id).first()
        if not batch_status:
            logging.warning(f"Batch {batch_id} not found")
            return
        
        # Получаем все задачи этого батча
        all_jobs = db.query(JobResult).filter(JobResult.batch_id == batch_id).all()
        
        completed_count = sum(1 for job in all_jobs if job.status == 'finished')
        failed_count = sum(1 for job in all_jobs if job.status == 'failed')
        started_count = sum(1 for job in all_jobs if job.status == 'started')
        queued_count = sum(1 for job in all_jobs if job.status == 'queued')
        
        # Обновляем счетчики
        batch_status.completed_jobs = completed_count
        batch_status.failed_jobs = failed_count
        
        # Проверяем, все ли задачи завершены
        total_finished = completed_count + failed_count
        if total_finished >= batch_status.total_jobs:
            batch_status.status = 'completed' if failed_count == 0 else 'completed_with_errors'
            batch_status.completed_at = datetime.utcnow()
            db.commit()
            
            logging.info(f"Batch {batch_id} completed: {completed_count} successful, {failed_count} failed")
            
            # Объединяем результаты в один файл
            if completed_count > 0:
                merged_id = merge_batch_results(batch_id, db)
                if merged_id:
                    logging.info(f"Merged result created with ID: {merged_id}")
            
            # Отправляем webhook если указан
            if batch_status.callback_url and not batch_status.callback_sent:
                send_webhook_notification(batch_status, db)
        else:
            db.commit()
            logging.info(f"Batch {batch_id} progress: {total_finished}/{batch_status.total_jobs} (completed: {completed_count}, failed: {failed_count}, started: {started_count}, queued: {queued_count})")
            
            # Логируем задачи, которые долго выполняются
            for job in all_jobs:
                if job.status == 'started' and job.created_at:
                    # Если задача выполняется больше 10 минут
                    time_diff = (datetime.utcnow() - job.created_at).total_seconds()
                    if time_diff > 600:
                        logging.warning(f"Job {job.job_id} ({job.prompt_name}) has been running for {time_diff/60:.1f} minutes")
            
    except Exception as e:
        logging.error(f"Error updating batch status for {batch_id}: {e}", exc_info=True)
        db.rollback()


def merge_batch_results(batch_id: str, db: Session):
    """Объединяет все результаты батча в один файл"""
    try:
        # Получаем все успешно завершенные задачи батча
        all_jobs = db.query(JobResult).filter(
            JobResult.batch_id == batch_id,
            JobResult.status == 'finished'
        ).order_by(JobResult.prompt_name).all()
        
        if not all_jobs:
            logging.warning(f"No finished jobs found for batch {batch_id}")
            return None
        
        # Объединяем все результаты
        merged_content = []
        merged_content.append(f"# Объединенные результаты документации\n")
        merged_content.append(f"Batch ID: {batch_id}\n")
        merged_content.append(f"Дата: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}\n")
        merged_content.append(f"Всего секций: {len(all_jobs)}\n")
        merged_content.append("\n" + "=" * 80 + "\n\n")
        
        for idx, job in enumerate(all_jobs, 1):
            merged_content.append(f"\n\n{'=' * 80}\n")
            merged_content.append(f"# Секция {idx}: {job.prompt_name}\n")
            merged_content.append(f"{'=' * 80}\n\n")
            merged_content.append(job.result_text)
            merged_content.append("\n\n")
        
        # Добавляем статистику в конец
        total_prompt_tokens = sum(job.prompt_tokens or 0 for job in all_jobs)
        total_completion_tokens = sum(job.completion_tokens or 0 for job in all_jobs)
        total_tokens = sum(job.total_tokens or 0 for job in all_jobs)
        
        merged_content.append("\n\n" + "=" * 80 + "\n")
        merged_content.append("# Статистика обработки\n")
        merged_content.append("=" * 80 + "\n\n")
        merged_content.append(f"- Обработано секций: {len(all_jobs)}\n")
        merged_content.append(f"- AI модель: {all_jobs[0].ai_model}\n")
        merged_content.append(f"- Модель: {all_jobs[0].model}\n")
        merged_content.append(f"- Всего токенов (prompt): {total_prompt_tokens:,}\n")
        merged_content.append(f"- Всего токенов (completion): {total_completion_tokens:,}\n")
        merged_content.append(f"- Всего токенов: {total_tokens:,}\n")
        
        merged_text = "".join(merged_content)
        
        # Создаем новую запись с объединенным результатом
        merged_job = JobResult(
            job_id=f"merged_{batch_id}",
            batch_id=batch_id,
            ai_model=all_jobs[0].ai_model,
            model=all_jobs[0].model,
            prompt_name="MERGED_DOCUMENTATION",
            request_code=all_jobs[0].request_code,
            result_text=merged_text,
            prompt_tokens=total_prompt_tokens,
            completion_tokens=total_completion_tokens,
            total_tokens=total_tokens,
            status='finished',
            completed_at=datetime.utcnow()
        )
        db.add(merged_job)
        db.commit()
        
        logging.info(f"Merged results created for batch {batch_id}: {len(all_jobs)} sections, {total_tokens:,} tokens")
        return merged_job.id
        
    except Exception as e:
        logging.error(f"Error merging batch results for {batch_id}: {e}", exc_info=True)
        db.rollback()
        return None


def send_webhook_notification(batch_status: BatchStatus, db: Session):
    """Отправляет webhook уведомление о завершении батча"""
    try:
        payload = {
            "batch_id": batch_status.batch_id,
            "status": batch_status.status,
            "total_jobs": batch_status.total_jobs,
            "completed_jobs": batch_status.completed_jobs,
            "failed_jobs": batch_status.failed_jobs,
            "completed_at": batch_status.completed_at.isoformat() if batch_status.completed_at else None
        }
        
        response = requests.post(
            batch_status.callback_url,
            json=payload,
            timeout=10,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.ok:
            batch_status.callback_sent = True
            db.commit()
            logging.info(f"Webhook sent successfully for batch {batch_status.batch_id}")
        else:
            logging.warning(f"Webhook failed for batch {batch_status.batch_id}: {response.status_code}")
            
    except Exception as e:
        logging.error(f"Error sending webhook for batch {batch_status.batch_id}: {e}")
    

async def send_task(request_data: request_form, db: AsyncSession):
    redis_conn = redis.Redis(host='redis', port=6379)
    q = Queue('to_aimodel', connection=redis_conn)
    
    # Генерируем уникальный batch_id для всего батча задач
    batch_id = str(uuid.uuid4())
    
    # Загружаем все активные промпты из БД
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.is_active == True)
    )
    prompts = result.scalars().all()
    
    if not prompts:
        raise HTTPException(status_code=500, detail="Не найдено ни одного активного промпта в БД")
    
    # Создаём запись о батче
    batch_status = BatchStatus(
        batch_id=batch_id,
        total_jobs=len(prompts),
        callback_url=request_data.callback_url,
        status='processing'
    )
    db.add(batch_status)
    await db.flush()
    
    jobs = []
    for prompt in prompts:
        job_record = JobResult(
            job_id="",
            batch_id=batch_id,
            ai_model=request_data.ai_model,
            model=request_data.model,
            prompt_name=prompt.name,
            request_code=request_data.request,
            status='queued'
        )
        db.add(job_record)
        await db.flush() 
        
        data = {
            "prompt_data": request_data,
            "prompt": prompt.content,
            "prompt_name": prompt.name,
            "job_id": None,
            "batch_id": batch_id
        }
        job = q.enqueue(add_prompt_task, data)
        
        data["job_id"] = job.id
        job_record.job_id = job.id
        
        job.cancel()
        job = q.enqueue(add_prompt_task, data)
        
        print(f"Задача поставлена в очередь: {job.id} (промпт: {prompt.name}, batch: {batch_id})")
        jobs.append({
            "job_id": job.id,
            "prompt_name": prompt.name
        })
    
    await db.commit()
    
    return {"jobs": jobs, "total": len(jobs), "batch_id": batch_id}
            
