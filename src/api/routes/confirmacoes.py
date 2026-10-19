"""Rota para resposta a confirmações pendentes (Garantia 1)."""

import logging
from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...core.runtime import RuntimeManager
from ...db.repositorio import (
    consumir_confirmacao_pendente,
    obter_confirmacoes_pendentes,
    reverter_confirmacao_pendente,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessoes", tags=["Confirmações"])


class ConfirmacaoPayload(BaseModel):
    id: str
    confirmado: bool


@router.post("/{session_id}/confirmacoes")
async def responder_confirmacao(
    session_id: str,
    payload: ConfirmacaoPayload,
) -> dict[str, Any]:
    """
    Recebe a aprovação ou negação para uma ação sensível (cobrança ou acesso).
    Retorna 409 se o ID não estiver pendente nesta sessão ou já tiver sido respondido (Garantia 1).
    """
    runtime = RuntimeManager.obter_instancia()
    session = await runtime.obter_sessao(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sessão '{session_id}' não encontrada.",
        )

    # GARANTIA 1: Consome atomicamente a pendência. Retorna None se não pendente ou já consumida.
    confirmacao_info = consumir_confirmacao_pendente(
        session_id=session_id,
        id_confirmacao=payload.id,
    )

    if not confirmacao_info:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Não existe confirmação pendente com o ID '{payload.id}' nesta sessão.",
        )

    # Retoma a execução do fluxo no agente
    try:
        return await runtime.executar_confirmacao(
            session_id=session_id,
            confirmacao_info=confirmacao_info,
            confirmado=payload.confirmado,
        )
    except Exception:
        # A retomada falhou (quota, modelo indisponível...): devolve a pendência para o morador reenviar,
        # em vez de deixá-la consumida e irrecuperável (409 no reenvio, ação nunca executada).
        logger.exception("Falha ao retomar a confirmação %s da sessão %s", payload.id, session_id)
        reverter_confirmacao_pendente(session_id=session_id, id_confirmacao=payload.id)
        return {
            "resposta": "Não consegui concluir agora. Responda a confirmação novamente em instantes.",
            "confirmacoes_pendentes": obter_confirmacoes_pendentes(session_id),
        }
