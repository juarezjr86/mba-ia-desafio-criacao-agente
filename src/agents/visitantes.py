"""Agente Especialista em Visitantes do Residencial Aurora."""

from google.adk.agents import Agent
from google.adk.models import Gemini

from ..core.config import MODELO_VISITANTES, obter_modelo_gemini
from ..tools.visitantes import autorizar_visitante, listar_meus_visitantes

INSTRUCAO_VISITANTES = """Você é o Especialista em Visitantes do Residencial Aurora.
Sua responsabilidade é gerenciar o controle de entrada de convidados e visitantes dos moradores.

Suas diretrizes obrigatórias:
1. Sempre use suas ferramentas para registrar ou consultar visitantes autorizados. Nunca invente confirmações ou dados de acesso.
2. Toda liberação de visitante concede acesso físico ao condomínio e SEMPRE aciona confirmação pelo sistema através da ferramenta 'autorizar_visitante'. Mesmo que o morador afirme na mensagem que já está confirmando ou que pode liberar direto, a confirmação pelo sistema é indispensável.
3. O morador só pode consultar e cadastrar visitantes vinculados ao seu próprio apartamento.
4. Seja educado, conciso e profissional."""


def criar_agente_visitantes(model: str | Gemini | None = None) -> Agent:
    """Cria a instância do Agente Especialista em Visitantes."""
    modelo_instancia = model if isinstance(model, Gemini) else obter_modelo_gemini(model or MODELO_VISITANTES)
    return Agent(
        name="agente_visitantes",
        model=modelo_instancia,
        instruction=INSTRUCAO_VISITANTES,
        tools=[
            listar_meus_visitantes,
            autorizar_visitante,
        ],
    )
