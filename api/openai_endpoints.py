from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from api.core.db_con import Prompt, get_db
from api.schemas.openapi_schema import prompt_form
from openai_.client import ChatGPTClient
from api.core.security import SECRET_KEY_OPENAI, verify_admin_token

openai = APIRouter(prefix="/api/v1/openai", tags=["openai"])

@openai.post("/send_prompt/", status_code=status.HTTP_201_CREATED, dependencies=[Depends(verify_admin_token)])
async def add_prompt(prompt_data: prompt_form, db: AsyncSession = Depends(get_db)):
    row = Prompt(prompt_name=prompt_data.prompt_name, prompt=prompt_data.prompt)
    db.add(row)
    await db.commit()
    await db.refresh(row)

    chatgpt_client = ChatGPTClient(
        api_key=SECRET_KEY_OPENAI,
        model_name=prompt_data.model, #"gpt-4o-mini",
        embeddings_model_name="text-embedding-3-small",
        system_prompt=prompt_data.prompt,
    )

    chunks = chatgpt_client.split_text_into_chunks(prompt_data.request, chunk_size=chatgpt_client.max_tokens)
    texts = ''.join(chatgpt_client.send_message(chunk) for chunk in chunks)


    return {
        "prompt_name": row.prompt_name,
        "system_prompt": row.prompt,
        "user_request": prompt_data.request,
        "gpt_response": texts,
    }
