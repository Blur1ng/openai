import textwrap
import time
from typing import List, Optional
import anthropic


class SonnetClient:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-sonnet-20240229",
        system_prompt: Optional[str] = None,
        max_tokens_per_chunk: int = 1024,
        chunk_char_size: int = 4000,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens_per_chunk
        self.chunk_size = chunk_char_size
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def _chunk_text(self, text: str) -> List[str]:
        """Разбивает текст на части по символам, не по токенам."""
        return textwrap.wrap(text, self.chunk_size, break_long_words=False)

    def _send_chunk(self, chunk: str, include_system: bool = False) -> str:
        """Отправляет один чанк, с retry-логикой."""
        messages = []
        if include_system and self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": chunk})

        for attempt in range(self.max_retries):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=self.max_tokens,
                    messages=messages
                )
                if response.content:
                    return response.content[0].text.strip()
                return ""
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay * (2 ** attempt))
                else:
                    raise e

    def send_message(self, user_text: str) -> str:
        """Разбивает текст на чанки, отправляет их и собирает полный ответ."""
        chunks = self._chunk_text(user_text)
        responses = []

        for i, chunk in enumerate(chunks):
            include_system = (i == 0)
            response_text = self._send_chunk(chunk, include_system=include_system)
            responses.append(response_text)

        return "\n".join(responses).strip()
    
    def send_message_with_usage(self, user_text: str) -> dict:
        """Отправляет сообщение и возвращает {'text': ..., 'usage': {...}}"""
        chunks = self._chunk_text(user_text)
        full_text = []
        total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        for i, chunk in enumerate(chunks):
            include_system = (i == 0)
            messages = []
            if include_system and self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            messages.append({"role": "user", "content": chunk})

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=messages
            )

            # собрать текст
            if response.content:
                full_text.append(response.content[0].text.strip())

            # собрать usage
            if response.usage:
                total_usage["prompt_tokens"] += response.usage.prompt_tokens or 0
                total_usage["completion_tokens"] += response.usage.completion_tokens or 0
                total_usage["total_tokens"] += response.usage.total_tokens or 0

        return {
            "text": "\n".join(full_text).strip(),
            "usage": total_usage
        }


    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        """
        Расчитывает стоимость на основе токенов.
        """
        prices = {
            "claude-3-opus-20240229": {"prompt": 0.015, "completion": 0.075},
            "claude-3-sonnet-20240229": {"prompt": 0.003, "completion": 0.015},
            "claude-3-haiku-20240307": {"prompt": 0.00025, "completion": 0.00125}
        }

        price = prices.get(self.model)
        if not price:
            return None

        cost = (prompt_tokens * price["prompt"] + completion_tokens * price["completion"]) / 1000
        return round(cost, 6)

