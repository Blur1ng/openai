from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from api.core.db_con import Prompt, get_db
from api.schemas.openapi_schema import prompt_form
from openai_.client import ChatGPTClient
from openai_.deepseek_client import DeepSeekClient
#from openai_.sonnet_client import SonnetClient
from api.core.security import SECRET_KEY_OPENAI, SECRET_KEY_DEEPSEEK, SECRET_KEY_SONNET, verify_admin_token

openai = APIRouter(prefix="/api/v1/openai", tags=["openai"])

@openai.post("/send_prompt/", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_admin_token)])
async def add_prompt(prompt_data: prompt_form, db: AsyncSession = Depends(get_db)):
    row = Prompt(ai_model = prompt_data.ai_model, prompt_name=prompt_data.prompt_name, prompt=prompt_data.prompt, request=prompt_data.request, model=prompt_data.model)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    ai_model = prompt_data.ai_model

    if ai_model == "chatgpt":
        chatgpt_client = ChatGPTClient(
            api_key=SECRET_KEY_OPENAI,
            model_name=prompt_data.model, #"gpt-4o-mini",
            embeddings_model_name="text-embedding-3-small",
            system_prompt=prompt_data.prompt
        )
        chunks = chatgpt_client.split_text_into_chunks(prompt_data.request, chunk_size=chatgpt_client.max_tokens)
        all_texts = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for chunk in chunks:
            result = chatgpt_client.send_message_with_usage(chunk)
            all_texts.append(result["text"])
            for key in total_usage:
                total_usage[key] += result["usage"].get(key, 0)

        texts = ''.join(all_texts)


    elif ai_model == "deepseek":
        client = DeepSeekClient(
            api_key=SECRET_KEY_DEEPSEEK,
            model_name="deepseek-chat",
            system_prompt=prompt_data.prompt
        )

        texts = client.send_message(prompt_data.request)

    #elif ai_model == "sonnet":
    #    client = SonnetClient(
    #        api_key=SECRET_KEY_SONNET,
    #        model_name="claude-sonnet...",
    #        system_prompt=prompt_data.prompt
    #    )
    #
    #    texts = client.send_message(prompt_data.request)

    else:
        raise HTTPException(status_code=400, detail="Нет такой аи модели")
    
    return {
        "ai_model": row.ai_model,
        "prompt_name": row.prompt_name,
        "system_prompt": row.prompt,
        "user_request": prompt_data.request,
        "gpt_response": texts,
        "model": row.model,
        "request_statistics": {
            "prompt_tokens": total_usage["prompt_tokens"],
            "completion_tokens": total_usage["completion_tokens"],
            "total_tokens": total_usage["total_tokens"],
            "approx_cost_usd": chatgpt_client.calculate_cost(total_usage["prompt_tokens"], total_usage["completion_tokens"])
        }
    }

