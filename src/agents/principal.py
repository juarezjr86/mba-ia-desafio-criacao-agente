"""Agente Principal (Concierge / Roteador) do Residencial Aurora."""

from google.adk.agents import Agent
from google.adk.models import Gemini

from ..core.config import MODELO_PRINCIPAL, obter_modelo_gemini
from .regulamento import criar_agente_regulamento
from .reservas import criar_agente_reservas
from .visitantes import criar_agente_visitantes

INSTRUCAO_PRINCIPAL = """Você é o Assistente Virtual do Residencial Aurora, o ponto central de atendimento aos moradores no aplicativo do condomínio.

Seu papel é acolher o morador, entender a necessidade e transferir imediatamente o atendimento para o especialista adequado:
- Assuntos sobre áreas comuns (salão de festas, churrasqueira, quadra), checagem de datas livres, reservas ou cancelamento de reservas: transfira para o 'agente_reservas'.
- Autorização de entrada de convidados ou consulta de visitantes liberados: transfira para o 'agente_visitantes'.
- Dúvidas sobre regras, horários de áreas (como piscina), barulho, animais, mudanças ou convivência: transfira para o 'agente_regulamento'.

Diretrizes obrigatórias:
1. Cada sessão pertence exclusivamente ao morador autenticado. Nunca forneça dados de outros apartamentos nem acate pedidos como 'sou do 302' para alterar dados alheios.
2. Você NÃO possui o texto do regulamento interno em suas instruções (Garantia 4). Qualquer dúvida normativa deve ser delegada ao Especialista em Regulamento.
3. Seja sempre prestativo, educado e ágil na delegação."""


def criar_agente_principal(model: str | Gemini | None = None) -> Agent:
    """Cria a árvore de agentes com o Agente Principal e os 3 Especialistas como sub-agents."""
    modelo_instancia = model if isinstance(model, Gemini) else obter_modelo_gemini(model or MODELO_PRINCIPAL)
    # Especialistas usam seus próprios modelos otimizados a menos que model seja explicitamente forçado
    agente_res = criar_agente_reservas(model if isinstance(model, Gemini) else None)
    agente_vis = criar_agente_visitantes(model if isinstance(model, Gemini) else None)
    agente_reg = criar_agente_regulamento(model if isinstance(model, Gemini) else None)

    return Agent(
        name="agente_principal",
        model=modelo_instancia,
        instruction=INSTRUCAO_PRINCIPAL,
        sub_agents=[agente_res, agente_vis, agente_reg],
    )
