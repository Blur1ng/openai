import asyncio
import logging
from fastapi                    import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio     import AsyncSession
from api.core.db_con            import Prompt, get_db
from api.schemas.openapi_schema import prompt_form, one_file_form
from openai_.client             import ChatGPTClient
from openai_.deepseek_client    import DeepSeekClient
from openai_.sonnet_client      import SonnetClient
from api.core.security          import SECRET_KEY_OPENAI, SECRET_KEY_DEEPSEEK, SECRET_KEY_SONNET, verify_admin_token
from pathlib                    import Path
from typing                     import Dict, Any

openai = APIRouter(prefix="/api/v1/openai", tags=["openai"])

@openai.post("/send_prompt/", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_admin_token)])
async def add_prompt(prompt_data: prompt_form, db: AsyncSession = Depends(get_db)):
    """
    Эндпоинт для документирования кода через AI.
    Принимает системный промпт и код, возвращает задокументированный код.
    """
    
    # Сохраняем запрос в БД
    row = Prompt(
        ai_model=prompt_data.ai_model, 
        prompt_name=prompt_data.prompt_name, 
        prompt=prompt_data.prompt, 
        request=prompt_data.request, 
        model=prompt_data.model
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    
    ai_model = prompt_data.ai_model
    
    #try:
    if ai_model == "chatgpt":
        chatgpt_client = ChatGPTClient(
            api_key=SECRET_KEY_OPENAI,
            model_name=prompt_data.model,
            embeddings_model_name="text-embedding-3-small",
            system_prompt=prompt_data.prompt,
            mathematical_percent=10  # Оставляем 10% запаса на ответ
        )
        
        # Проверяем размер запроса
        request_tokens = len(chatgpt_client.tokenize_text(prompt_data.request))
        system_tokens = len(chatgpt_client.tokenize_text(prompt_data.prompt)) if prompt_data.prompt else 0
        total_input_tokens = request_tokens + system_tokens
        
        logging.info(f"Request tokens: {request_tokens}, System tokens: {system_tokens}, Total: {total_input_tokens}, Max: {chatgpt_client.max_tokens}")
        
        # ВАРИАНТ 1: Если запрос помещается целиком - отправляем одним запросом (РЕКОМЕНДУЕТСЯ)
        if total_input_tokens <= chatgpt_client.max_tokens:
            result = chatgpt_client.send_full_request_with_usage(prompt_data.request)
            texts = result["text"]
            total_usage = result["usage"]
            logging.info(f"Sent as single request. Tokens used: {total_usage['total_tokens']}")
        
        # ВАРИАНТ 2: Если не помещается - разбиваем на чанки
        else:
            logging.warning(f"Request too large ({total_input_tokens} tokens), splitting into chunks")
            
            # Размер чанка = 80% от доступного места (оставляем место на ответ)
            chunk_size = int(chatgpt_client.max_tokens * 0.8) - system_tokens
            chunks = chatgpt_client.split_text_into_chunks(prompt_data.request, chunk_size=chunk_size)
            
            all_texts = []
            total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            
            for idx, chunk in enumerate(chunks, 1):
                logging.info(f"Processing chunk {idx}/{len(chunks)}")
                
                # Добавляем контекст для каждого чанка
                chunk_message = f"[Часть {idx} из {len(chunks)}]\n\n{chunk}"
                
                result = chatgpt_client.send_message_with_usage(chunk_message)
                all_texts.append(result["text"])
                
                for key in total_usage:
                    total_usage[key] += result["usage"].get(key, 0)
            
            texts = '\n\n'.join(all_texts)  # Объединяем через двойной перенос
            logging.info(f"Completed processing {len(chunks)} chunks. Total tokens: {total_usage['total_tokens']}")
    
    elif ai_model == "deepseek":
        client = DeepSeekClient(
            api_key=SECRET_KEY_DEEPSEEK,
            model_name=prompt_data.model,
            system_prompt=prompt_data.prompt
        )
        texts = client.send_message(prompt_data.request)
        # DeepSeek не возвращает usage, ставим заглушку
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    elif ai_model == "sonnet":
        client = SonnetClient(
            api_key=SECRET_KEY_SONNET,
            model_name=prompt_data.model,
            system_prompt=prompt_data.prompt
        )
        texts = client.send_message(prompt_data.request)
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    
    else:
        raise HTTPException(status_code=400, detail="Нет такой AI модели")
    
    cost = None
    if ai_model == "chatgpt":
        cost = chatgpt_client.calculate_cost(
            total_usage["prompt_tokens"], 
            total_usage["completion_tokens"]
        )
    
    return {
        "ai_model": row.ai_model,
        "prompt_name": row.prompt_name,
        "system_prompt": row.prompt,
        "user_request": prompt_data.request[:500] + "..." if len(prompt_data.request) > 500 else prompt_data.request,  
        "gpt_response": texts,
        "model": row.model,
        "request_statistics": {
            "prompt_tokens": total_usage["prompt_tokens"],
            "completion_tokens": total_usage["completion_tokens"],
            "total_tokens": total_usage["total_tokens"],
            "approx_cost_usd": cost
        }
    }
    
    #except Exception as e:
    #    logging.error(f"Error processing request: {str(e)}")
    #    raise HTTPException(status_code=500, detail=f"Ошибка обработки запроса: {str(e)}")
    
@openai.post("/make_krasivo/", status_code=status.HTTP_201_CREATED)
async def make_krasivo(one_file_form_data: one_file_form, db: AsyncSession = Depends(get_db)):
    prompt_names = ["tech_doc", "architecture", "dataflow"]
    
    async def process_prompt(prompt_name: str) -> Dict[str, Any]:
        """Обрабатывает один промпт асинхронно"""
        try:
            prompt_dir = Path(__file__).parent / "prompts"
            prompt_path = prompt_dir / f"{prompt_name}.txt"
            with open(prompt_path, "r") as promptfile:
                system_prompt = promptfile.read()
                
            client = SonnetClient(
                api_key=SECRET_KEY_SONNET,
                system_prompt=system_prompt
            )
            
            result = await asyncio.to_thread(
                client.send_message_with_usage, 
                one_file_form_data.code
            )
            row = Prompt(ai_model="claude-sonnet-4-20250514", prompt_name=one_file_form_data.prompt_name_, prompt=prompt_name, request=one_file_form_data.code, model="-")
            db.add(row)
            await db.commit()
            await db.refresh(row)
            print(f"Запрос {prompt_name} выполнен успешно")
            
            return {
                "prompt_name": prompt_name,
                "text": f"## {prompt_name.replace('_', ' ').title()}\n\n{result['text']}",
                "usage": result["usage"],
                "error": None
            }
            
        except Exception as e:
            return {
                "prompt_name": prompt_name,
                "text": f"## {prompt_name.replace('_', ' ').title()}\n\nError: {str(e)}",
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "error": str(e)
            }
    
    results = await asyncio.gather(*[
        process_prompt(prompt_name) 
        for prompt_name in prompt_names
    ])
    
    combined_text = "\n\n---\n\n".join([r["text"] for r in results])
    
    total_usage = {
        "prompt_tokens": sum(r["usage"]["prompt_tokens"] for r in results),
        "completion_tokens": sum(r["usage"]["completion_tokens"] for r in results),
        "total_tokens": sum(r["usage"]["total_tokens"] for r in results)
    }
    
    return {
        "response": combined_text,
        "request_statistics": {
            "total_requests": len(prompt_names),
            "successful_requests": len([r for r in results if r["error"] is None]),
            "prompt_tokens": total_usage["prompt_tokens"],
            "completion_tokens": total_usage["completion_tokens"],
            "total_tokens": total_usage["total_tokens"]
        }
    }