from .engine import TranslationEngine
from urllib import request
import json

class OllamaEngine(TranslationEngine):
    def __init__(
        self,
        host: str,
        port: int,
        model_name: str,
        prompt_template: str, # Use {input} as placeholder
        **kwargs
    ):
        self.url = f"http://{host}:{port}/api/generate"
        self.data = {
            "model": model_name,
            "prompt": prompt_template,
            "stream": False,
            **kwargs
        }
    
    def translate(self, input_text: str) -> str:
        data = self.data.copy()
        data["prompt"] = data["prompt"].format(input=input_text)
        req = request.Request(self.url, method="POST")
        req.add_header("Content-Type", "application/json")
        with request.urlopen(req, data=json.dumps(data).encode()) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Ollama API returned status {resp.status}")
            response_data = json.load(resp)
            if isinstance(response_data.get("response"), str):
                return response_data["response"]
            return response_data.get("choices", [{}])[0].get("message", {}).get("content", "")

    def __str__(self) -> str:
        return f"Ollama({self.data['model']})"
