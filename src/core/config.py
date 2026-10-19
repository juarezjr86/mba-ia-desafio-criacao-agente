"""Configurações centrais do Residencial Aurora."""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from google.adk.models import Gemini
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from pydantic import Field

logger = logging.getLogger(__name__)

# Carrega variáveis de ambiente do .env se existir
load_dotenv()

# Pool ordenado de modelos Gemini ativos e funcionais no Free-Tier com fallback automático
POOL_MODELOS = [
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
    "gemini-3.7-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite-preview",
]

# Modelos primários preferenciais por agente para distribuir quotas
MODELO_PRINCIPAL = os.getenv("MODELO_PRINCIPAL", "gemini-flash-latest")
MODELO_RESERVAS = os.getenv("MODELO_RESERVAS", "gemini-flash-lite-latest")
MODELO_VISITANTES = os.getenv("MODELO_VISITANTES", "gemini-3.7-flash")
MODELO_REGULAMENTO = os.getenv("MODELO_REGULAMENTO", "gemini-3.1-flash-lite")
DEFAULT_MODEL = MODELO_PRINCIPAL

# Caminhos do banco
DB_DIR = Path("dados_app")
CONDOMINIO_DB_PATH = DB_DIR / "condominio.db"
SESSOES_DB_PATH = DB_DIR / "sessoes.db"
SESSOES_DB_URL = f"sqlite+aiosqlite:///{SESSOES_DB_PATH.as_posix()}"


class FallbackGemini(Gemini):
    """Modelo Gemini resiliente com alternância e memorização de modelos ativos em 429 ou 503."""

    fallback_models: list[str] = Field(default_factory=list)

    async def generate_content_async(self, llm_request: LlmRequest, stream: bool = False):
        models_to_try = [self.model] + [m for m in self.fallback_models if m != self.model]
        last_exc = None
        for m in models_to_try:
            try:
                llm_request.model = m
                async for resp in super().generate_content_async(llm_request, stream=stream):
                    yield resp
                # Memoriza o modelo bem-sucedido para evitar tentativas em modelos esgotados
                self.model = m
                return
            except Exception as e:
                err_str = str(e).upper()
                if (
                    "429" in err_str
                    or "503" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "UNAVAILABLE" in err_str
                    or "NOT_FOUND" in err_str  # modelo inexistente ou sem acesso na conta
                ):
                    logger.warning(
                        "Modelo %s indisponivel, sem acesso ou com quota esgotada (%s). Alternando para proximo modelo...",
                        m,
                        err_str[:60],
                    )
                    last_exc = e
                    continue
                raise
        if last_exc:
            raise last_exc


def obter_modelo_gemini(model_name: str | None = None) -> FallbackGemini:
    """Cria uma instância de FallbackGemini com pool de tolerância a falhas e esgotamento de quota."""
    primary = model_name or DEFAULT_MODEL
    fallbacks = [m for m in POOL_MODELOS if m != primary]
    client = genai.Client(
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=2,
                initial_delay=1.0,
                max_delay=3.0,
                http_status_codes=[429, 503],
            )
        )
    )
    return FallbackGemini(model=primary, fallback_models=fallbacks, client=client)
