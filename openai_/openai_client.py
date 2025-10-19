import logging
import tiktoken
from   langchain.schema import HumanMessage, SystemMessage
from   langchain_openai import ChatOpenAI, OpenAIEmbeddings
from   pydantic         import SecretStr
from   typing           import List, Optional
from   openai           import OpenAI


class ChatGPTClient(object):
    def __init__(
            self,
            api_key: SecretStr,
            model_name: str = 'gpt-4o-mini',
            embeddings_model_name: str = 'text-embedding-3-small',
            system_prompt: str | None = None,
            mathematical_percent: Optional[int] = 20,
    ):
        self._api_key = api_key
        self.model_name = model_name
        self.math_p = mathematical_percent
        self.embeddings_model_name = embeddings_model_name
        self.chat_model = ChatOpenAI(
            openai_api_key=self._api_key,
            model_name=self.model_name,
        )
        self.embeddings_model = OpenAIEmbeddings(
            openai_api_key=self._api_key,
            model=self.embeddings_model_name,
        )
        self.chat_history = []

        self.tokenizer = tiktoken.get_encoding('cl100k_base')
        self.embeddings_tokenizer = tiktoken.get_encoding('cl100k_base')

        
        self.system_prompt = system_prompt
        if self.system_prompt:
            system_message = SystemMessage(content=self.system_prompt)
            self.chat_history.append(system_message)

        self.token = self.get_model_token_limit(self.model_name)
        self.max_tokens = self.token - int((self.token / 100) * self.math_p)
        self.embeddings_max_tokens = self.get_model_token_limit(self.embeddings_model_name)

    def get_model_token_limit(self, model_name: str) -> int:
        """Возвращает лимит токенов для модели"""
        model_token_limits = {
            'gpt-3.5-turbo': 16385,
            'gpt-3.5-turbo-16k': 16384,
            'gpt-4': 8192,
            'gpt-4o-mini': 128000, 
            'gpt-4o': 128000,
            'gpt-4-32k': 32768,
            'text-embedding-ada-002': 8191,
            'text-embedding-3-small': 8191,
        }
        return model_token_limits.get(model_name, 4096)

    def tokenize_text(self, text: str, tokenizer=None) -> List[int]:
        if tokenizer is None:
            tokenizer = self.tokenizer
        tokens = tokenizer.encode(text)
        logging.info('Tokenize text.')
        return tokens

    def split_text_into_chunks(self, text: str, chunk_size: int, tokenizer=None) -> List[str]:
        """Разбивает текст на чанки по токенам"""
        if tokenizer is None:
            tokenizer = self.tokenizer
        tokens = self.tokenize_text(text, tokenizer)
        chunks = []
        for i in range(0, len(tokens), chunk_size):
            chunk_tokens = tokens[i:i + chunk_size]
            chunk_text = tokenizer.decode(chunk_tokens)
            chunks.append(chunk_text)
        logging.info(f'Split text into {len(chunks)} chunks.')
        return chunks

    def send_message(self, message: str) -> str:
        """Отправка сообщения с учетом истории чата"""
        human_message = HumanMessage(content=message)
        new_message_tokens = len(self.tokenize_text(human_message.content))
        self.trim_chat_history(new_message_tokens)
        self.chat_history.append(human_message)
        assistant_message = self.chat_model.invoke(self.chat_history)
        self.chat_history.append(assistant_message)
        logging.info('Send message to OpenAI client.')
        return assistant_message.content

    def trim_chat_history(self, new_message_tokens_length):
        """Обрезает историю чата, чтобы поместиться в лимит токенов"""
        total_tokens = new_message_tokens_length
        trimmed_history = []
        for message in reversed(self.chat_history):
            message_tokens = len(self.tokenize_text(message.content))
            if (total_tokens + message_tokens) <= self.max_tokens:
                trimmed_history.insert(0, message)
                total_tokens += message_tokens
            else:
                break

        if self.system_prompt:
            system_message = SystemMessage(content=self.system_prompt)
            trimmed_history.insert(0, system_message)

        self.chat_history = trimmed_history

    def send_message_with_usage(self, message: str) -> dict:
        """
        Отправляет ONE-SHOT запрос без истории.
        Используется для обработки отдельных чанков.
        """
        client = OpenAI(api_key=self._api_key)

        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": message})

        response = client.chat.completions.create(
            model=self.model_name,
            messages=messages,
        )

        return {
            "text": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
    
    def send_full_request_with_usage(self, user_message: str) -> dict:
        """
        НОВЫЙ МЕТОД: Отправляет весь запрос целиком с автоматическим разбиением на чанки.
        Для документирования кода - лучше отправлять весь код целиком, если помещается.
        """
        client = OpenAI(api_key=self._api_key)
        
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": user_message})
        
        total_tokens = sum(len(self.tokenize_text(msg.get("content", ""))) for msg in messages)
        
        if total_tokens > self.max_tokens:
            raise ValueError(f"Запрос слишком большой: {total_tokens} токенов, максимум {self.max_tokens}")
        
        response = client.chat.completions.create(
            model=self.model_name,
            messages=messages,
        )

        return {
            "text": response.choices[0].message.content,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
    
    def calculate_cost(self, prompt_tokens, completion_tokens):
        """Рассчитывает стоимость запроса"""
        prices = {
            "gpt-4": {"prompt": 30.0, "completion": 60.0},
            "gpt-4-1106-preview": {"prompt": 10.0, "completion": 30.0},
            "gpt-4o-mini": {"prompt": 0.150, "completion": 0.600}, 
            "gpt-4o": {"prompt": 2.50, "completion": 10.0},
            "gpt-3.5-turbo": {"prompt": 0.50, "completion": 1.50},
        }

        price = prices.get(self.model_name)
        if not price:
            return None

        cost = (prompt_tokens * price["prompt"] + completion_tokens * price["completion"]) / 1_000_000
        return round(cost, 6)