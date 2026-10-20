from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.config import get_settings


def build_chat_model() -> ChatOpenAI:
    settings = get_settings()
    kwargs: dict = {
        "model": settings.model_name,
        "api_key": settings.model_api_key,
        "temperature": 0,
        "streaming": False,
    }
    if settings.model_base_url:
        kwargs["base_url"] = settings.model_base_url
    return ChatOpenAI(**kwargs)


def build_embeddings() -> OpenAIEmbeddings:
    settings = get_settings()
    kwargs: dict = {
        "model": settings.embedding_model,
        "api_key": settings.embedding_api_key,
        "check_embedding_ctx_length": False,
    }
    if settings.embedding_base_url:
        kwargs["base_url"] = settings.embedding_base_url
    return OpenAIEmbeddings(**kwargs)

