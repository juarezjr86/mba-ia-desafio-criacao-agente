"""Rotas para gerenciamento do ciclo de vida das sessões e consulta de eventos."""

from typing import Any
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ...core.runtime import RuntimeManager

router = APIRouter(prefix="/sessoes", tags=["Sessões"])


class CriarSessaoPayload(BaseModel):
    apartamento: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def criar_sessao(payload: CriarSessaoPayload) -> dict[str, str]:
    """Cria uma nova sessão vinculando imutavelmente o morador (Garantia 2)."""
    runtime = RuntimeManager.obter_instancia()
    session = await runtime.criar_sessao(apartamento=payload.apartamento)
    return {"session_id": session.id}


@router.get("/{session_id}/eventos")
async def obter_eventos_sessao(session_id: str) -> list[dict[str, Any]]:
    """Retorna todos os eventos gravados na sessão com conteúdo completo (Garantia 3 e 4)."""
    runtime = RuntimeManager.obter_instancia()
    session = await runtime.obter_sessao(session_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sessão '{session_id}' não encontrada.",
        )

    # Retorna todos os eventos serializados em ordem
    eventos = [event.model_dump(by_alias=True, mode="json") for event in session.events]
    return eventos
