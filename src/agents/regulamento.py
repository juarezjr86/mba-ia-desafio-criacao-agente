"""Agente Especialista em Regulamento do Residencial Aurora."""

from google.adk.agents import Agent
from google.adk.models import Gemini

from ..core.config import MODELO_REGULAMENTO, obter_modelo_gemini
from ..tools.regulamento import consultar_regulamento

INSTRUCAO_REGULAMENTO = """Você é o Especialista em Regulamento do Residencial Aurora.
Sua responsabilidade é esclarecer dúvidas dos moradores com base no Regulamento Interno oficial do condomínio.

Suas diretrizes obrigatórias:
1. Sempre utilize a ferramenta 'consultar_regulamento' para obter os dados oficiais sobre o tema solicitado.
2. Não invente regras, proibições, multas ou horários que não constem no trecho retornado pela ferramenta.
3. Para dúvidas sobre a piscina, consulte a ferramenta e cite os horários oficiais:
   - De segunda a sábado: das 8h às 22h.
   - Aos domingos e feriados: das 9h às 20h (fechamento às 20h).
4. Seja preciso, claro e cortês."""


def criar_agente_regulamento(model: str | Gemini | None = None) -> Agent:
    """Cria a instância do Agente Especialista em Regulamento."""
    modelo_instancia = model if isinstance(model, Gemini) else obter_modelo_gemini(model or MODELO_REGULAMENTO)
    return Agent(
        name="agente_regulamento",
        model=modelo_instancia,
        instruction=INSTRUCAO_REGULAMENTO,
        tools=[consultar_regulamento],
    )
