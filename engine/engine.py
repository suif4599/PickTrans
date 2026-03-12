from abc import ABCMeta, abstractmethod
from typing import overload
import warnings
import traceback
from html import escape


class TranslationEngine(metaclass=ABCMeta):
    engines: dict[str, type['TranslationEngine']] = {}
    @abstractmethod
    def translate(self, input_text: str) -> str:
        """Translate the input text and return the translated text in HTML format for display."""
        pass

    @abstractmethod
    def __str__(self) -> str:
        pass

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        cls.engines[cls.__name__] = cls

    @staticmethod
    def make_engine(engine_name: str, **kwargs) -> 'TranslationEngine':
        if engine_name not in TranslationEngine.engines:
            raise ValueError(f"Unknown engine: {engine_name}")
        return TranslationEngine.engines[engine_name](**kwargs)

    @staticmethod
    def make_engines(config: dict) -> list['TranslationEngine']:
        engines: list['TranslationEngine'] = []
        engines_config = config.get("engines", {})
        engine_order = config.get("engine-order", [])
        for name in engine_order:
            if name not in engines_config:
                warnings.warn(f"Engine {name} is specified in engine_order but not found in engines config.")
                continue
            try:
                for config in engines_config[name]:
                    engine = TranslationEngine.make_engine(name, **config)
                    engines.append(engine)
            except Exception as e:
                warnings.warn(f"Failed to initialize engine {name}: {e}\n{traceback.format_exc()}")
        return engines

class EngineCollection:
    def __init__(self, engines: list[TranslationEngine]) -> None:
        self._engines = engines

    def __len__(self) -> int:
        return len(self._engines)

    def __iter__(self):
        return iter(self._engines)

    def names(self) -> list[str]:
        return [str(engine) for engine in self._engines]

    def get(self, index: int) -> TranslationEngine:
        return self._engines[index]

    def index_name(self, index: int) -> str:
        return str(self._engines[index])

    @staticmethod
    def _error_html(message: str) -> str:
        return (
            "<div style='color:#b00020'>翻译失败</div>"
            f"<pre style='white-space:pre-wrap'>{escape(message)}</pre>"
        )
    
    @overload
    def translate(self, input_text: str) -> tuple[int, str]:
        """Translate the input text using the first available engine. Returns a tuple of (engine_index, translated_html)."""
    
    @overload
    def translate(self, input_text: str, engine_index: int) -> str:
        """Translate the input text using the specified engine index. Returns the translated HTML."""
    
    def translate(self, input_text: str, engine_index: int | None = None) -> str | tuple[int, str]:
        # Won't raise any error, just return error message in translation result if engine fails.
        if not self._engines:
            error = self._error_html("No translation engine is available.")
            if engine_index is None:
                return -1, error
            return error

        if engine_index is not None:
            if engine_index < 0 or engine_index >= len(self._engines):
                return self._error_html(f"Invalid engine index: {engine_index}")
            try:
                return self._engines[engine_index].translate(input_text)
            except Exception:
                return self._error_html(traceback.format_exc())

        errors: list[str] = []
        for idx, engine in enumerate(self._engines):
            try:
                return idx, engine.translate(input_text)
            except Exception:
                errors.append(f"[{idx}] {engine}:\n{traceback.format_exc()}")
        return -1, self._error_html("\n\n".join(errors))
