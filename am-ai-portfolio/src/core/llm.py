from functools import cache
from typing import TypeAlias

from langchain_openai import ChatOpenAI

from core.settings import settings

@cache
def get_model(model_name: str):
    if not settings.COMPATIBLE_BASE_URL:
        raise ValueError("OpenAICompatible base url must be configured")

    return ChatOpenAI(
        model=model_name,
        temperature=0.1,
        streaming=True,
        openai_api_base=settings.COMPATIBLE_BASE_URL,
        openai_api_key=settings.COMPATIBLE_API_KEY,
    )
