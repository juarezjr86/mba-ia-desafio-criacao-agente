"""Runtime de execução de agentes com Runner, App resumable e DatabaseSessionService."""

import asyncio
import logging
from typing import Any
import uuid

from google.adk.apps import App
from google.adk.apps.app import ResumabilityConfig
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.adk.sessions.session import Session
from google.genai import types

from ..agents.principal import criar_agente_principal
from ..core.config import DEFAULT_MODEL, SESSOES_DB_URL, obter_modelo_gemini
from ..db.repositorio import (
    obter_confirmacoes_pendentes,
    salvar_confirmacao_pendente,
)

logger = logging.getLogger(__name__)

APP_NAME = "residencial_aurora_app"
DEFAULT_USER_ID = "morador"


class RuntimeManager:
    """Gerenciador singleton do Runtime do ADK com persistência e resumabilidade."""

    _instance: "RuntimeManager | None" = None

    def __init__(self, model: str | Gemini | None = None):
        self.model = model if isinstance(model, Gemini) else obter_modelo_gemini(model)
        self.session_service = DatabaseSessionService(db_url=SESSOES_DB_URL)
        self.root_agent = criar_agente_principal(model=self.model)
        self.app = App(
            name=APP_NAME,
            root_agent=self.root_agent,
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        self.runner = Runner(
            app=self.app,
            session_service=self.session_service,
        )

    @classmethod
    def obter_instancia(cls) -> "RuntimeManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def criar_sessao(self, apartamento: str, session_id: str | None = None) -> Session:
        """Cria uma nova sessão associada imutavelmente a um apartamento (Garantia 2 e 3)."""
        sid = session_id or str(uuid.uuid4())
        session = await self.session_service.create_session(
            app_name=APP_NAME,
            user_id=DEFAULT_USER_ID,
            session_id=sid,
            state={"apartamento": str(apartamento)},
        )
        return session

    async def obter_sessao(self, session_id: str) -> Session | None:
        """Recupera a sessão persistida (Garantia 3)."""
        return await self.session_service.get_session(
            app_name=APP_NAME,
            user_id=DEFAULT_USER_ID,
            session_id=session_id,
        )

    async def executar_mensagem(
        self,
        session_id: str,
        texto: str,
    ) -> dict[str, Any]:
        """Executa uma nova mensagem de texto na sessão e processa eventos gerados."""
        session = await self.obter_sessao(session_id)
        if not session:
            return {"erro": "Sessão não encontrada", "codigo_status": 404}

        new_message = types.Content(
            role="user",
            parts=[types.Part.from_text(text=texto)],
        )

        respostas_texto: list[str] = []
        max_tentativas = 5

        for tentativa in range(max_tentativas):
            try:
                msg_to_send = new_message if tentativa == 0 else None
                async for event in self.runner.run_async(
                    user_id=DEFAULT_USER_ID,
                    session_id=session_id,
                    new_message=msg_to_send,
                ):
                    # 1. Coleta texto gerado pelo modelo
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                respostas_texto.append(part.text)

                    # 2. Coleta e registra eventuais pedidos de confirmação emitidos por tools
                    for function_call in event.get_function_calls():
                        if function_call.name == "adk_request_confirmation":
                            call_id = function_call.id
                            invocation_id = event.invocation_id or session_id
                            args = function_call.args or {}
                            tool_conf = args.get("toolConfirmation") or {}
                            orig_fc = args.get("originalFunctionCall") or {}

                            acao = orig_fc.get("name", "acao_desconhecida")
                            detalhes = tool_conf.get("payload") or orig_fc.get("args") or {}

                            salvar_confirmacao_pendente(
                                id_confirmacao=call_id,
                                session_id=session_id,
                                invocation_id=invocation_id,
                                acao=acao,
                                detalhes=detalhes,
                            )
                break
            except Exception as e:
                err_str = str(e).upper()
                if (
                    "429" in err_str
                    or "503" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "UNAVAILABLE" in err_str
                ) and tentativa < max_tentativas - 1:
                    wait_time = 6.0 * (tentativa + 1)
                    logger.warning(
                        "Quota/disponibilidade do Gemini atingida (%s). Aguardando %.1fs para retomar...",
                        err_str[:80],
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise

        # Monta resposta final conforme o contrato da API
        resposta_final = "".join(respostas_texto).strip()
        pendentes = obter_confirmacoes_pendentes(session_id)

        return {
            "resposta": resposta_final,
            "confirmacoes_pendentes": pendentes,
        }

    async def executar_confirmacao(
        self,
        session_id: str,
        confirmacao_info: dict[str, Any],
        confirmado: bool,
    ) -> dict[str, Any]:
        """Retoma a execução de uma tool pausada via confirmação respondida."""
        confirmacao_id = confirmacao_info["id"]
        invocation_id = confirmacao_info["invocation_id"]

        # Constrói o FunctionResponse no formato esperado pelo ADK
        confirmation_response = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="adk_request_confirmation",
                        id=confirmacao_id,
                        response={"confirmed": confirmado},
                    )
                )
            ],
        )

        respostas_texto: list[str] = []
        max_tentativas = 5

        for tentativa in range(max_tentativas):
            try:
                msg_to_send = confirmation_response if tentativa == 0 else None
                async for event in self.runner.run_async(
                    user_id=DEFAULT_USER_ID,
                    session_id=session_id,
                    new_message=msg_to_send,
                    invocation_id=invocation_id,
                ):
                    # 1. Coleta texto gerado após a retomada
                    if event.content and event.content.parts:
                        for part in event.content.parts:
                            if part.text:
                                respostas_texto.append(part.text)

                    # 2. Captura novas pendências se houver
                    for function_call in event.get_function_calls():
                        if function_call.name == "adk_request_confirmation":
                            call_id = function_call.id
                            inv_id = event.invocation_id or invocation_id
                            args = function_call.args or {}
                            tool_conf = args.get("toolConfirmation") or {}
                            orig_fc = args.get("originalFunctionCall") or {}

                            acao = orig_fc.get("name", "acao_desconhecida")
                            detalhes = tool_conf.get("payload") or orig_fc.get("args") or {}

                            salvar_confirmacao_pendente(
                                id_confirmacao=call_id,
                                session_id=session_id,
                                invocation_id=inv_id,
                                acao=acao,
                                detalhes=detalhes,
                            )
                break
            except Exception as e:
                err_str = str(e).upper()
                if (
                    "429" in err_str
                    or "503" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "UNAVAILABLE" in err_str
                ) and tentativa < max_tentativas - 1:
                    wait_time = 6.0 * (tentativa + 1)
                    logger.warning(
                        "Quota/disponibilidade do Gemini atingida na confirmação (%s). Aguardando %.1fs...",
                        err_str[:80],
                        wait_time,
                    )
                    await asyncio.sleep(wait_time)
                    continue
                raise

        resposta_final = "".join(respostas_texto).strip()
        pendentes = obter_confirmacoes_pendentes(session_id)

        return {
            "resposta": resposta_final,
            "confirmacoes_pendentes": pendentes,
        }
