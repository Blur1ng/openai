import logging
from fastapi                    import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio     import AsyncSession
from api.core.db_con            import get_db, JobResult, BatchStatus
from api.schemas.openapi_schema import prompt_form, request_form
from api.core.security          import SECRET_KEY_OPENAI, SECRET_KEY_DEEPSEEK, SECRET_KEY_SONNET, verify_admin_token
from api.broker.task            import send_task
from api.core.db_con            import Prompt, get_db
from openai_.openai_client      import ChatGPTClient
from openai_.deepseek_client    import DeepSeekClient
from openai_.sonnet_client      import SonnetClient
from sqlalchemy import select

ai_model = APIRouter(prefix="/api/v1/ai_model", tags=["ai_model"])

#new version(send only code(promt from files on the Server))
# TODO: Вернуть проверку авторизации после добавления системы регистрации
@ai_model.post("/send_prompt/", status_code=status.HTTP_201_CREATED)
async def add_prompt_new(request_data: request_form, db: AsyncSession = Depends(get_db)):
    return await send_task(request_data, db)

@ai_model.get("/jobs", dependencies=[Depends(verify_admin_token)])
async def get_all_jobs(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
    status_filter: str = None
):
    """Получить список всех задач с фильтрацией"""
    query = select(JobResult).order_by(JobResult.created_at.desc())
    
    if status_filter:
        query = query.where(JobResult.status == status_filter)
    
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return {
        "jobs": [
            {
                "job_id": job.job_id,
                "status": job.status,
                "ai_model": job.ai_model,
                "model": job.model,
                "prompt_name": job.prompt_name,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            }
            for job in jobs
        ],
        "total": len(jobs)
    }


@ai_model.get("/results/{result_id}", dependencies=[Depends(verify_admin_token)])
async def get_result_by_id(result_id: int, db: AsyncSession = Depends(get_db)):
    """Получить полную информацию о результате по ID"""
    result = await db.execute(
        select(JobResult).where(JobResult.id == result_id)
    )
    job_record = result.scalar_one_or_none()
    
    if not job_record:
        raise HTTPException(status_code=404, detail=f"Результат с ID {result_id} не найден")
    
    return {
        "id": job_record.id,
        "job_id": job_record.job_id,
        "batch_id": job_record.batch_id,
        "status": job_record.status,
        "ai_model": job_record.ai_model,
        "model": job_record.model,
        "prompt_name": job_record.prompt_name,
        "request_code": job_record.request_code,
        "result_text": job_record.result_text,
        "prompt_tokens": job_record.prompt_tokens,
        "completion_tokens": job_record.completion_tokens,
        "total_tokens": job_record.total_tokens,
        "error_message": job_record.error_message,
        "created_at": job_record.created_at.isoformat() if job_record.created_at else None,
        "completed_at": job_record.completed_at.isoformat() if job_record.completed_at else None
    }


@ai_model.get("/results", dependencies=[Depends(verify_admin_token)])
async def get_all_results(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0
):
    """Получить список всех завершённых результатов (только ID)"""
    query = select(JobResult).where(JobResult.status == 'finished').order_by(JobResult.completed_at.desc())
    query = query.limit(limit).offset(offset)
    result = await db.execute(query)
    jobs = result.scalars().all()
    
    return [
        {
            "id": job.id,
            "job_id": job.job_id
        }
        for job in jobs
    ]


# TODO: Вернуть проверку авторизации после добавления системы регистрации
@ai_model.get("/batch/{batch_id}")
async def get_batch_status(batch_id: str, db: AsyncSession = Depends(get_db)):
    """Получить статус всего батча задач"""
    # Получаем информацию о батче
    batch_result = await db.execute(
        select(BatchStatus).where(BatchStatus.batch_id == batch_id)
    )
    batch = batch_result.scalar_one_or_none()
    
    if not batch:
        raise HTTPException(status_code=404, detail="Батч не найден")
    
    # Получаем все задачи этого батча (исключая объединенный файл)
    jobs_result = await db.execute(
        select(JobResult).where(
            JobResult.batch_id == batch_id,
            JobResult.prompt_name != "MERGED_DOCUMENTATION"
        ).order_by(JobResult.created_at)
    )
    jobs = jobs_result.scalars().all()
    
    # Проверяем наличие объединенного файла
    merged_result = await db.execute(
        select(JobResult).where(
            JobResult.batch_id == batch_id,
            JobResult.prompt_name == "MERGED_DOCUMENTATION"
        )
    )
    merged_job = merged_result.scalar_one_or_none()
    
    response = {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "total_jobs": batch.total_jobs,
        "completed_jobs": batch.completed_jobs,
        "failed_jobs": batch.failed_jobs,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
        "has_merged_result": merged_job is not None,
        "merged_job_id": merged_job.job_id if merged_job else None,
        "jobs": [
            {
                "job_id": job.job_id,
                "prompt_name": job.prompt_name,
                "status": job.status,
                "total_tokens": job.total_tokens,
                "error_message": job.error_message,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "completed_at": job.completed_at.isoformat() if job.completed_at else None
            }
            for job in jobs
        ]
    }
    
    return response


# TODO: Вернуть проверку авторизации после добавления системы регистрации
@ai_model.get("/jobs/{job_id}")
async def get_job_status(job_id: str, db: AsyncSession = Depends(get_db)):
    """Получить статус и результат задачи из БД"""
    result = await db.execute(
        select(JobResult).where(JobResult.job_id == job_id)
    )
    job_record = result.scalar_one_or_none()
    
    if not job_record:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    
    response = {
        "job_id": job_record.job_id,
        "status": job_record.status,
        "ai_model": job_record.ai_model,
        "model": job_record.model,
        "prompt_name": job_record.prompt_name,
        "created_at": job_record.created_at.isoformat() if job_record.created_at else None,
        "completed_at": job_record.completed_at.isoformat() if job_record.completed_at else None
    }
    
    if job_record.status == 'finished':
        response["result"] = job_record.result_text
        response["statistics"] = {
            "prompt_tokens": job_record.prompt_tokens,
            "completion_tokens": job_record.completion_tokens,
            "total_tokens": job_record.total_tokens
        }
    elif job_record.status == 'failed':
        response["error"] = job_record.error_message
    
    return response
