import requests
import json
import logging
import tiktoken
from   typing   import Dict, List, Optional


class DeepSeekClient:
    """
    Чанки по 1000 символов
    """
    def __init__(
        self, 
        api_key: str, 
        model_name: str = "deepseek-chat",
        system_prompt: str = "",
        mathematical_percent: int = 20
    ):
        self.api_key = api_key
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.math_p = mathematical_percent
        
        self.api_url = "https://api.deepseek.com/v1/chat/completions"
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        self.tokenizer = tiktoken.get_encoding('cl100k_base')
        
        self.token = self.get_model_token_limit(self.model_name)
        self.max_tokens = self.token - int((self.token / 100) * self.math_p)
    
    def get_model_token_limit(self, model_name: str) -> int:
        """Возвращает лимит токенов для модели DeepSeek"""
        model_token_limits = {
            'deepseek-chat': 64000,  
            'deepseek-coder': 16000,  
        }
        return model_token_limits.get(model_name, 32000)
    
    def tokenize_text(self, text: str) -> List[int]:
        """Токенизирует текст"""
        tokens = self.tokenizer.encode(text)
        return tokens
    
    def split_text_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """Разбивает текст на чанки по токенам"""
        tokens = self.tokenize_text(text)
        chunks = []
        
        for i in range(0, len(tokens), chunk_size):
            chunk_tokens = tokens[i:i + chunk_size]
            chunk_text = self.tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
        
        logging.info(f'Split text into {len(chunks)} chunks for DeepSeek.')
        return chunks

    def send_message(self, user_input: str) -> str:
        """
        Отправляет сообщение и возвращает полный текст ответа (без streaming).
        Для совместимости с основным API.
        """
        result = self.send_message_with_usage(user_input)
        return result["text"]

    def send_message_with_usage(self, user_input: str, temperature: float = 0.7) -> Dict:
        """
        Отправляет сообщение и возвращает ответ с usage статистикой.
        Возвращает: {'text': str, 'usage': dict}
        """
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_input})
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": False
        }
        
        try:
            response = requests.post(
                self.api_url, 
                headers=self.headers, 
                json=payload,
                timeout=300
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")
            
            result = response.json()
            
            text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
            
            usage = result.get("usage", {})
            
            return {
                "text": text,
                "usage": {
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0)
                }
            }
            
        except requests.exceptions.Timeout:
            raise Exception("DeepSeek API timeout - запрос слишком долгий")
        except requests.exceptions.RequestException as e:
            raise Exception(f"DeepSeek API connection error: {str(e)}")
        except Exception as e:
            raise Exception(f"DeepSeek API error: {str(e)}")
    
    def send_message_streaming(self, user_input: str, temperature: float = 0.7) -> List[str]:
        """
        Отправляет сообщение со streaming и возвращает список чанков.
        Используется если нужен потоковый вывод.
        """
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_input})
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }
        
        try:
            response = requests.post(
                self.api_url,
                headers=self.headers,
                json=payload,
                stream=True,
                timeout=300
            )
            
            if response.status_code != 200:
                raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")
            
            chunks = []
            buffer = ""
            
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    
                    if decoded_line.startswith("data: "):
                        content = decoded_line[6:].strip()
                        
                        if content == "[DONE]":
                            break
                        
                        try:
                            json_data = json.loads(content)
                            delta = json_data.get("choices", [{}])[0].get("delta", {})
                            text = delta.get("content", "")
                            
                            if text:
                                buffer += text
                                
                                if len(buffer) > 1000:
                                    chunks.append(buffer)
                                    buffer = ""
                                    
                        except json.JSONDecodeError as e:
                            logging.error(f"Error parsing stream chunk: {e}")
                            continue
            
            if buffer:
                chunks.append(buffer)
            
            return chunks
            
        except requests.exceptions.Timeout:
            raise Exception("DeepSeek API timeout")
        except Exception as e:
            raise Exception(f"DeepSeek streaming error: {str(e)}")
    
    def send_full_request_with_usage(self, user_message: str) -> Dict:
        """
        Отправляет полный запрос с проверкой размера.
        Аналог метода из ChatGPT клиента для единообразия API.
        """
        total_tokens = len(self.tokenize_text(user_message))
        if self.system_prompt:
            total_tokens += len(self.tokenize_text(self.system_prompt))
        
        if total_tokens > self.max_tokens:
            raise ValueError(f"Запрос слишком большой: {total_tokens} токенов, максимум {self.max_tokens}")
        
        return self.send_message_with_usage(user_message)
    
    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
        """
        Рассчитывает стоимость запроса для DeepSeek.
        """
        prices = {
            "deepseek-chat": {"prompt": 0.14, "completion": 0.28},
            "deepseek-coder": {"prompt": 0.14, "completion": 0.28},
        }
        
        price = prices.get(self.model_name)
        if not price:
            return None
        
        cost = (prompt_tokens * price["prompt"] + completion_tokens * price["completion"]) / 1_000_000
        return round(cost, 6)