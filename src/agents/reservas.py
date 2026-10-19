"""Agente Especialista em Reservas do Residencial Aurora."""

from google.adk.agents import Agent
from google.adk.models import Gemini

from ..core.config import MODELO_RESERVAS, obter_modelo_gemini
from ..tools.reservas import (
    cancelar_reserva,
    consultar_disponibilidade_area,
    listar_minhas_reservas,
    reservar_area,
)

INSTRUCAO_RESERVAS = """Você é o Especialista em Reservas do Residencial Aurora.
Sua responsabilidade é gerenciar as reservas das áreas comuns: salão de festas, churrasqueira e quadra poliesportiva.

Suas diretrizes obrigatórias:
1. Sempre use suas ferramentas para ler ou gravar dados. Nunca invente códigos de reserva, disponibilidades ou informações de titulares.
2. Ao consultar a disponibilidade de uma data, informe apenas se a área está 'livre' ou 'ocupada'. Nunca revele quem é o morador que reservou.
3. Se o morador pedir para reservar uma área com taxa (salão de festas ou churrasqueira), a ferramenta 'reservar_area' solicitará confirmação automaticamente.
4. Se a área tiver taxa 0 (quadra), a reserva é concluída imediatamente sem confirmação.
5. O morador pode cancelar as reservas do próprio apartamento sem confirmação. Caso ele peça para cancelar a reserva de outro apartamento, informe que não é possível cancelar reservas de terceiros.
6. Seja cordial, direto e objetivo nas respostas."""


def criar_agente_reservas(model: str | Gemini | None = None) -> Agent:
    """Cria a instância do Agente Especialista em Reservas."""
    modelo_instancia = model if isinstance(model, Gemini) else obter_modelo_gemini(model or MODELO_RESERVAS)
    return Agent(
        name="agente_reservas",
        model=modelo_instancia,
        instruction=INSTRUCAO_RESERVAS,
        tools=[
            listar_minhas_reservas,
            consultar_disponibilidade_area,
            reservar_area,
            cancelar_reserva,
        ],
    )
