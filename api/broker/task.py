import logging
from fastapi                    import HTTPException
from api.core.db_con            import Prompt, get_db
from openai_.openai_client      import ChatGPTClient
from openai_.deepseek_client    import DeepSeekClient
from openai_.sonnet_client      import SonnetClient
from api.core.security          import SECRET_KEY_OPENAI, SECRET_KEY_DEEPSEEK, SECRET_KEY_SONNET
from pathlib import Path

def add_prompt(prompt_data:dict):
    #row = Prompt(
    #    ai_model=prompt_data.ai_model, 
    #    prompt_name=prompt_data.prompt_name, 
    #    prompt=prompt_data.prompt, 
    #    request=prompt_data.request, 
    #    model=prompt_data.model
    #)
    #db.add(row)
    #await db.commit()
    #await db.refresh(row)
    
    ai_model = prompt_data["ai_model"]
    
    if ai_model == "chatgpt":
        chatgpt_client = ChatGPTClient(
            api_key=SECRET_KEY_OPENAI,
            model_name=prompt_data["model"],
            embeddings_model_name="text-embedding-3-small",
            system_prompt=prompt_data["prompt"],
            mathematical_percent=10
        )
        
        # Проверяем размер запроса
        request_tokens = len(chatgpt_client.tokenize_text(prompt_data["request"]))
        system_tokens = len(chatgpt_client.tokenize_text(prompt_data["prompt"])) if prompt_data["prompt"] else 0
        total_input_tokens = request_tokens + system_tokens
        
        logging.info(f"Request tokens: {request_tokens}, System tokens: {system_tokens}, Total: {total_input_tokens}, Max: {chatgpt_client.max_tokens}")
        
        # Если запрос помещается целиком
        if total_input_tokens <= chatgpt_client.max_tokens:
            result = chatgpt_client.send_full_request_with_usage(prompt_data["request"])
            texts = result["text"]
            total_usage = result["usage"]
            logging.info(f"Sent as single request. Tokens used: {total_usage['total_tokens']}")
        # Если не помещается - разбиваем на чанки
        else:
            logging.warning(f"Request too large ({total_input_tokens} tokens), splitting into chunks")
            
            # Размер чанка = 80% от доступного места (оставляем место на ответ)
            chunk_size = int(chatgpt_client.max_tokens * 0.8) - system_tokens
            chunks = chatgpt_client.split_text_into_chunks(prompt_data["request"], chunk_size=chunk_size)
            
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
                model_name=prompt_data["model"],
                system_prompt=prompt_data["prompt"],
                mathematical_percent=10
            )
            
            request_tokens = len(client.tokenize_text(prompt_data["request"]))
            system_tokens = len(client.tokenize_text(prompt_data["prompt"])) if prompt_data["prompt"] else 0
            total_input_tokens = request_tokens + system_tokens
            
            logging.info(f"DeepSeek request tokens: {request_tokens}, System tokens: {system_tokens}, Total: {total_input_tokens}, Max: {client.max_tokens}")
            
            # Если запрос помещается целиком
            if total_input_tokens <= client.max_tokens:
                result = client.send_full_request_with_usage(prompt_data["request"])
                texts = result["text"]
                total_usage = result["usage"]
                logging.info(f"DeepSeek sent as single request. Tokens used: {total_usage['total_tokens']}")
            
            # Если не помещается - разбиваем на чанки
            else:
                logging.warning(f"DeepSeek request too large ({total_input_tokens} tokens), splitting into chunks")
                
                # Размер чанка = 80% от доступного места (оставляем место на ответ)
                chunk_size = int(client.max_tokens * 0.8) - system_tokens
                chunks = client.split_text_into_chunks(prompt_data["request"], chunk_size=chunk_size)
                
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
                model_name=prompt_data["model"],
                system_prompt=prompt_data["prompt"],
                mathematical_percent=10
            )
            
            request_tokens = client.count_tokens(prompt_data["reques"])
            system_tokens = client.count_tokens(prompt_data["prompt"]) if prompt_data["prompt"] else 0
            total_input_tokens = request_tokens + system_tokens
            
            logging.info(f"Claude request tokens: ~{request_tokens}, System tokens: ~{system_tokens}, Total: ~{total_input_tokens}, Max: {client.max_tokens}")
            
            if total_input_tokens <= client.max_tokens:
                result = client.send_full_request_with_usage(prompt_data["request"])
                texts = result["text"]
                total_usage = result["usage"]
                logging.info(f"Claude sent as single request. Tokens used: {total_usage['total_tokens']}")
            
            else:
                logging.warning(f"Claude request too large (~{total_input_tokens} tokens), splitting into chunks")
                result = client.send_chunked_message_with_usage(prompt_data["request"])
                texts = result["text"]
                total_usage = result["usage"]
                logging.info(f"Claude completed chunked request. Total tokens: {total_usage['total_tokens']}")
        
    else:
        raise HTTPException(status_code=400, detail="Нет такой AI модели")
    
    print("zxc")
    with Path("api/broker/result.py").open("w") as res:
        res.write(texts.replace('\\n', '\n').replace('\\"', '"'))

    #cost = None
    #if ai_model == "chatgpt":
    #    cost = chatgpt_client.calculate_cost(
    #        total_usage["prompt_tokens"], 
    #        total_usage["completion_tokens"]
    #    )
    #elif ai_model == "deepseek":
    #    cost = client.calculate_cost(
    #        total_usage["prompt_tokens"],
    #        total_usage["completion_tokens"]
    #    )
    
    #return {
    #    "ai_model": prompt_data.ai_model,
    #    "prompt_name": prompt_data.prompt_name,
    #    "gpt_response": texts,
    #    "model": prompt_data.model,
    #    "request_statistics": {
    #        "prompt_tokens": total_usage["prompt_tokens"],
    #        "completion_tokens": total_usage["completion_tokens"],
    #        "total_tokens": total_usage["total_tokens"],
    #        #"approx_cost_usd": cost
    #    }
    #}
    
