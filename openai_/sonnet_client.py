import time
import logging
import anthropic
from   anthropic import Anthropic
from   typing    import List, Optional, Dict


class SonnetClient:
    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-sonnet-4-5-20250929",
        system_prompt: Optional[str] = None,
        mathematical_percent: int = 20,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.client = Anthropic(api_key=api_key)
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.math_p = mathematical_percent
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self.token = self.get_model_token_limit(self.model_name)
        self.max_tokens = self.token - int((self.token / 100) * self.math_p)
        
        self.max_tokens_response = 20000 

    def get_model_token_limit(self, model_name: str) -> int:
        """Возвращает лимит контекста для модели Claude"""
        model_token_limits = {
            'claude-3-opus-20240229': 200000,
            'claude-3-sonnet-20240229': 200000,
            'claude-3-haiku-20240307': 200000,
            'claude-3-5-sonnet-20240620': 200000,
            'claude-3-5-sonnet-20241022': 200000,
            'claude-sonnet-4-20250514': 200000,  
            'claude-opus-4-20250514': 200000,    
        }
        return model_token_limits.get(model_name, 200000)

    def count_tokens(self, text: str) -> int:
        """
        Приблизительный подсчет токенов для Claude.
        Claude использует свой токенизатор, но для оценки можно использовать:
        ~4 символа = 1 токен
        """
        return len(text) // 4

    def split_text_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """
        Разбивает текст на чанки по приблизительному количеству токенов.
        Старается не разрывать строки кода.
        """
        lines = text.split('\n')
        chunks = []
        current_chunk = []
        current_size = 0
        
        for line in lines:
            line_tokens = self.count_tokens(line + '\n')
            
            if line_tokens > chunk_size:
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
                    current_size = 0
                chunks.append(line)
                continue
            
            if current_size + line_tokens > chunk_size and current_chunk:
                chunks.append('\n'.join(current_chunk))
                current_chunk = [line]
                current_size = line_tokens
            else:
                current_chunk.append(line)
                current_size += line_tokens
        
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        logging.info(f'Split text into {len(chunks)} chunks for Claude.')
        return chunks

    def _send_with_retry(self, messages: List[Dict], include_system: bool = True) -> anthropic.types.Message:
        """Отправляет запрос с retry логикой"""
        api_kwargs = {
            "model": self.model_name,
            "max_tokens": self.max_tokens_response,
            "messages": messages
        }
        
        if include_system and self.system_prompt:
            api_kwargs["system"] = self.system_prompt

        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(**api_kwargs)
                return response
            except anthropic.RateLimitError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logging.warning(f"Rate limit hit, waiting {wait_time}s before retry {attempt + 1}/{self.max_retries}")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Claude API rate limit exceeded after {self.max_retries} retries: {str(e)}")
            except anthropic.APIError as e:
                if attempt < self.max_retries - 1:
                    wait_time = self.retry_delay * (2 ** attempt)
                    logging.warning(f"API error, retrying in {wait_time}s: {str(e)}")
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Claude API error after {self.max_retries} retries: {str(e)}")
            except Exception as e:
                raise Exception(f"Claude API unexpected error: {str(e)}")

    def send_message(self, user_text: str) -> str:
        """Отправляет сообщение и возвращает текст ответа"""
        result = self.send_message_with_usage(user_text)
        return result["text"]

    def send_message_with_usage(self, user_text: str) -> Dict:
        """
        Отправляет одно сообщение (без разбиения) и возвращает ответ с usage.
        Возвращает: {'text': str, 'usage': dict}
        """
        messages = [{"role": "user", "content": user_text}]
        
        response = self._send_with_retry(messages, include_system=True)
        
        text = ""
        if response.content:
            text = response.content[0].text.strip()
        
        usage = {
            "prompt_tokens": response.usage.input_tokens or 0,
            "completion_tokens": response.usage.output_tokens or 0,
            "total_tokens": (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)
        }
        
        return {
            "text": text,
            "usage": usage
        }

    def send_full_request_with_usage(self, user_message: str) -> Dict:
        """
        Отправляет полный запрос с проверкой размера.
        Для единообразия API с другими клиентами.
        """
        total_tokens = self.count_tokens(user_message)
        if self.system_prompt:
            total_tokens += self.count_tokens(self.system_prompt)
        
        if total_tokens > self.max_tokens:
            raise ValueError(f"Запрос слишком большой: ~{total_tokens} токенов, максимум {self.max_tokens}")
        
        return self.send_message_with_usage(user_message)

    def send_chunked_message_with_usage(self, user_text: str) -> Dict:
        """
        Разбивает текст на чанки и отправляет их последовательно.
        Собирает результаты и usage статистику.
        """
        system_tokens = self.count_tokens(self.system_prompt) if self.system_prompt else 0
        chunk_size = int(self.max_tokens * 0.8) - system_tokens
        
        chunks = self.split_text_into_chunks(user_text, chunk_size=chunk_size)
        
        full_text = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for i, chunk in enumerate(chunks, 1):
            logging.info(f"Processing Claude chunk {i}/{len(chunks)}")
            
            chunk_message = f"[Часть {i} из {len(chunks)}]\n\n{chunk}"
            messages = [{"role": "user", "content": chunk_message}]
            
            response = self._send_with_retry(messages, include_system=(i == 1))

            if response.content:
                full_text.append(response.content[0].text.strip())

            if response.usage:
                total_usage["prompt_tokens"] += response.usage.input_tokens or 0
                total_usage["completion_tokens"] += response.usage.output_tokens or 0
                total_usage["total_tokens"] += (response.usage.input_tokens or 0) + (response.usage.output_tokens or 0)

        return {
            "text": "\n\n".join(full_text).strip(),
            "usage": total_usage
        }

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> Optional[float]:
        """
        Рассчитывает стоимость запроса для Claude.
        Цены обновлены на октябрь 2024.
        """
        prices = {
            "claude-3-opus-20240229": {"prompt": 15.0, "completion": 75.0},
            "claude-3-sonnet-20240229": {"prompt": 3.0, "completion": 15.0},
            "claude-3-haiku-20240307": {"prompt": 0.25, "completion": 1.25},
            "claude-3-5-sonnet-20240620": {"prompt": 3.0, "completion": 15.0},
            "claude-3-5-sonnet-20241022": {"prompt": 3.0, "completion": 15.0},
            "claude-sonnet-4-20250514": {"prompt": 3.0, "completion": 15.0},  
            "claude-opus-4-20250514": {"prompt": 15.0, "completion": 75.0},  
        }

        price = prices.get(self.model_name)
        if not price:
            return None

        cost = (prompt_tokens * price["prompt"] + completion_tokens * price["completion"]) / 1_000_000
        return round(cost, 6)