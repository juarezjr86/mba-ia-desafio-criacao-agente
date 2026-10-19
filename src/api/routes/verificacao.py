"""Rotas de verificação direta para auditoria de reservas e visitantes (sem passar pelo modelo)."""

from typing import Any
from fastapi import APIRouter

from ...db.repositorio import (
    obter_reservas_apartamento,
    obter_visitantes_apartamento,
)

router = APIRouter(prefix="/apartamentos", tags=["Verificação"])


@router.get("/{numero}/reservas")
async def listar_reservas_apartamento(numero: str) -> list[dict[str, Any]]:
    """Consulta direta ao banco das reservas ativas de um apartamento."""
    return obter_reservas_apartamento(numero)


@router.get("/{numero}/visitantes")
async def listar_visitantes_apartamento(numero: str) -> list[dict[str, Any]]:
    """Consulta direta ao banco dos visitantes autorizados de um apartamento."""
    return obter_visitantes_apartamento(numero)
