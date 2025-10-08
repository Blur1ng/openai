import requests

class DeepSeekClient:
    def __init__(self, api_key: str, model_name: str, system_prompt: str = ""):
        self.api_key = api_key
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.api_url = "https://api.deepseek.com" 
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def send_message(self, user_input: str, max_tokens: int = 2048, chunk_pause: float = 0.5) -> list[str]:
        """
        Отправляет сообщение и возвращает список текстовых чанков (частей ответа).
        """
        messages = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        messages.append({"role": "user", "content": user_input})

        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.7,
            "stream": True  
        }

        response = requests.post(self.api_url, headers=self.headers, json=payload, stream=True)

        if response.status_code != 200:
            raise Exception(f"DeepSeek API error: {response.status_code} - {response.text}")

        chunks = []
        buffer = ""

        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')

                if decoded_line.startswith("data: "):
                    content = decoded_line[len("data: "):].strip()

                    if content == "[DONE]":
                        break

                    try:
                        json_data = eval(content) 
                        delta = json_data.get("choices", [{}])[0].get("delta", {})
                        text = delta.get("content", "")

                        if text:
                            buffer += text

                            if len(buffer) > 1000:
                                chunks.append(buffer)
                                buffer = ""
                    except Exception as e:
                        print(f"Error parsing stream chunk: {e}")
                        continue

        if buffer:
            chunks.append(buffer)

        return chunks
