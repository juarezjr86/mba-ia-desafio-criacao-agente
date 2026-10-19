"""Rota para resposta a confirmações pendentes (Garantia 1)."""

from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...core.runtime import RuntimeManager
from ...db.repositorio import consumir_confirmacao_pendente

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
    resultado = await runtime.executar_confirmacao(
        session_id=session_id,
        confirmacao_info=confirmacao_info,
        confirmado=payload.confirmado,
    )

    return resultado
