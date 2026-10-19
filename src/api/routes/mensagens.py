"""Rota para envio de mensagens conversacionais na sessão."""

from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...core.runtime import RuntimeManager

router = APIRouter(prefix="/sessoes", tags=["Mensagens"])


class MensagemPayload(BaseModel):
    texto: str


@router.post("/{session_id}/mensagens")
async def enviar_mensagem(session_id: str, payload: MensagemPayload) -> dict[str, Any]:
    """Processa a mensagem do morador através do Agente Principal e seus especialistas."""
    runtime = RuntimeManager.obter_instancia()
    session = await runtime.obter_sessao(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sessão '{session_id}' não encontrada.",
        )

    resultado = await runtime.executar_mensagem(
        session_id=session_id,
        texto=payload.texto,
    )

    if resultado.get("codigo_status") == 404:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sessão não encontrada.")

    return resultado
