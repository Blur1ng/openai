import logging
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from api.core.db_con import get_db, PromptTemplate
from api.core.security import verify_admin_token
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

prompt_router = APIRouter(prefix="/api/v1/prompts", tags=["prompts"])


class PromptCreate(BaseModel):
    name: str
    content: str
    description: Optional[str] = None
    is_active: bool = True


class PromptUpdate(BaseModel):
    content: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class PromptResponse(BaseModel):
    id: int
    name: str
    content: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@prompt_router.post("/", status_code=status.HTTP_201_CREATED, response_model=PromptResponse, dependencies=[Depends(verify_admin_token)])
async def create_prompt(prompt_data: PromptCreate, db: AsyncSession = Depends(get_db)):
    """Создать новый промпт"""
    
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == prompt_data.name)
    )
    existing_prompt = result.scalar_one_or_none()
    
    if existing_prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Промпт с именем '{prompt_data.name}' уже существует"
        )
    
    # Создаём новый промпт
    new_prompt = PromptTemplate(
        name=prompt_data.name,
        content=prompt_data.content,
        description=prompt_data.description,
        is_active=prompt_data.is_active
    )
    
    db.add(new_prompt)
    await db.commit()
    await db.refresh(new_prompt)
    
    logging.info(f"Создан новый промпт: {new_prompt.name}")
    
    return new_prompt


@prompt_router.get("/", response_model=PromptResponse, dependencies=[Depends(verify_admin_token)])
async def get_all_prompts(is_active: Optional[bool] = None, db: AsyncSession = Depends(get_db)):
    """Получить список всех промптов"""
    
    query = select(PromptTemplate.id, PromptTemplate.name, PromptTemplate.description).order_by(PromptTemplate.created_at.desc())
    
    if is_active is not None:
        query = query.where(PromptTemplate.is_active == is_active)
    
    result = await db.execute(query)
    prompts = result.scalar_one_or_none()

    return {prompts.id, prompts.name, prompts.description}


@prompt_router.get("/{prompt_name}", response_model=PromptResponse, dependencies=[Depends(verify_admin_token)])
async def get_prompt(prompt_name: str, db: AsyncSession = Depends(get_db)):
    """Получить промпт по имени"""
    
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == prompt_name)
    )
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Промпт '{prompt_name}' не найден"
        )
    
    return prompt


@prompt_router.put("/{prompt_name}", response_model=PromptResponse, dependencies=[Depends(verify_admin_token)])
async def update_prompt(prompt_name: str, prompt_data: PromptUpdate, db: AsyncSession = Depends(get_db)):
    """Обновить промпт"""
    
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == prompt_name)
    )
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Промпт '{prompt_name}' не найден"
        )
    
    if prompt_data.content is not None:
        prompt.content = prompt_data.content
    if prompt_data.description is not None:
        prompt.description = prompt_data.description
    if prompt_data.is_active is not None:
        prompt.is_active = prompt_data.is_active
    
    prompt.updated_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(prompt)
    
    logging.info(f"Обновлён промпт: {prompt.name}")
    
    return prompt


@prompt_router.delete("/{prompt_name}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(verify_admin_token)])
async def delete_prompt(prompt_name: str, db: AsyncSession = Depends(get_db)):
    """Удалить промпт"""
    
    result = await db.execute(
        select(PromptTemplate).where(PromptTemplate.name == prompt_name)
    )
    prompt = result.scalar_one_or_none()
    
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Промпт '{prompt_name}' не найден"
        )
    
    await db.delete(prompt)
    await db.commit()
    
    logging.info(f"Удалён промпт: {prompt_name}")
    
    return None

