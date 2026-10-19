"""Ferramentas para gestão de reservas com confirmação de taxa, isolamento e concorrência."""

from typing import Any

from google.adk.tools.tool_context import ToolContext

from ..db.repositorio import (
    cancelar_reserva as db_cancelar_reserva,
    criar_reserva as db_criar_reserva,
    obter_area,
    obter_reservas_apartamento,
    verificar_disponibilidade_area as db_verificar_disponibilidade,
)


def listar_minhas_reservas(tool_context: ToolContext) -> dict[str, Any]:
    """
    Lista todas as reservas ativas pertencentes exclusivamente ao apartamento da sessão (Garantia 2).
    """
    apartamento = str(tool_context.state.get("apartamento", ""))
    if not apartamento:
        return {"status": "erro", "mensagem": "Sessão sem apartamento vinculado."}

    reservas = obter_reservas_apartamento(apartamento)
    return {
        "status": "sucesso",
        "apartamento": apartamento,
        "reservas": reservas,
    }


def consultar_disponibilidade_area(
    area: str,
    data: str,
    tool_context: ToolContext | None = None,
) -> dict[str, Any]:
    """
    Consulta se uma determinada área comum está livre ou ocupada em uma data específica.
    Por segurança (Garantia 2), apenas informa 'livre' ou 'ocupada', nunca expondo quem reservou.
    
    Args:
        area: Identificador da área (ex.: 'salao-de-festas', 'churrasqueira', 'quadra').
        data: Data no formato AAAA-MM-DD (ex.: '2030-04-20').
    """
    area_id = area.lower().strip()
    area_info = obter_area(area_id)
    if not area_info:
        # Tenta normalizar nomes comuns
        nomes_map = {
            "salão de festas": "salao-de-festas",
            "salao de festas": "salao-de-festas",
            "quadra": "quadra",
            "quadra poliesportiva": "quadra",
            "churrasqueira": "churrasqueira",
        }
        area_id = nomes_map.get(area_id, area_id)
        area_info = obter_area(area_id)

    if not area_info:
        return {"status": "erro", "mensagem": f"Área '{area}' não encontrada no condomínio."}

    disponivel = db_verificar_disponibilidade(area_id, data)
    return {
        "status": "sucesso",
        "area": area_id,
        "data": data,
        "disponivel": disponivel,
        "situacao": "livre" if disponivel else "ocupada",
        "taxa": area_info["taxa"],
    }


def reservar_area(
    area: str,
    data: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Reserva uma área comum para o morador da sessão.
    Se a área possuir taxa maior que zero, exige aprovação pela rota de confirmações (Garantia 1).
    A exclusividade é imposta no instante da gravação (Garantia 5).
    
    Args:
        area: Identificador da área (ex.: 'salao-de-festas', 'churrasqueira', 'quadra').
        data: Data no formato AAAA-MM-DD (ex.: '2030-04-20').
    """
    apartamento = str(tool_context.state.get("apartamento", ""))
    if not apartamento:
        return {"status": "erro", "mensagem": "Sessão inválida: apartamento ausente."}

    area_id = area.lower().strip()
    nomes_map = {
        "salão de festas": "salao-de-festas",
        "salao de festas": "salao-de-festas",
        "quadra": "quadra",
        "quadra poliesportiva": "quadra",
        "churrasqueira": "churrasqueira",
    }
    area_id = nomes_map.get(area_id, area_id)

    area_info = obter_area(area_id)
    if not area_info:
        return {"status": "erro", "mensagem": f"Área '{area}' não existe no condomínio."}

    taxa = float(area_info["taxa"])

    # REGRA 2 / GARANTIA 1: Taxa > 0 exige confirmação via rota /confirmacoes
    if taxa > 0:
        confirmation = tool_context.tool_confirmation
        if confirmation is None:
            # Pausa a execução e solicita confirmação humana
            tool_context.request_confirmation(
                hint=f"Reserva do {area_info['nome']} para {data} com taxa de R$ {taxa:.2f}",
                payload={"area": area_id, "data": data},
            )
            return {
                "status": "pendente_confirmacao",
                "mensagem": f"A reserva da área '{area_info['nome']}' para {data} gera cobrança de R$ {taxa:.2f} e requer confirmação.",
                "area": area_id,
                "data": data,
                "taxa": taxa,
            }

        # Morador respondeu à confirmação
        if not confirmation.confirmed:
            return {
                "status": "recusada_pelo_morador",
                "mensagem": f"A reserva da área '{area_info['nome']}' para {data} foi cancelada porque a confirmação foi negada.",
            }

    # Executa a gravação atômica da reserva (Garantia 5)
    reserva = db_criar_reserva(apartamento=apartamento, area_id=area_id, data=data)
    if reserva is None:
        # Colisão de reserva simultânea no banco
        return {
            "status": "recusada",
            "mensagem": f"Não foi possível reservar: a área '{area_info['nome']}' já está reservada para o dia {data}.",
        }

    return {
        "status": "sucesso",
        "codigo": reserva["codigo"],
        "area": area_id,
        "data": data,
        "taxa": taxa,
        "mensagem": f"Reserva confirmada com sucesso! Código: {reserva['codigo']}.",
    }


def cancelar_reserva(
    data: str | None = None,
    area: str | None = None,
    codigo: str | None = None,
    tool_context: ToolContext = None,
) -> dict[str, Any]:
    """
    Cancela uma reserva do próprio apartamento sem confirmação (Regra 4 e Garantia 2).
    Apenas reservas do apartamento vinculado à sessão podem ser canceladas.
    
    Args:
        data: Data da reserva (AAAA-MM-DD), se conhecida.
        area: Nome ou ID da área, se conhecido.
        codigo: Código da reserva (ex.: 'RSV-1377'), se conhecido.
    """
    apartamento = str(tool_context.state.get("apartamento", "")) if tool_context else ""
    if not apartamento:
        return {"status": "erro", "mensagem": "Sessão inválida: apartamento ausente."}

    area_id = None
    if area:
        area_clean = area.lower().strip()
        nomes_map = {
            "salão de festas": "salao-de-festas",
            "salao de festas": "salao-de-festas",
            "quadra": "quadra",
            "quadra poliesportiva": "quadra",
            "churrasqueira": "churrasqueira",
        }
        area_id = nomes_map.get(area_clean, area_clean)

    sucesso = db_cancelar_reserva(
        apartamento=apartamento,
        area_id=area_id,
        data=data,
        codigo=codigo,
    )

    if sucesso:
        return {
            "status": "sucesso",
            "mensagem": "Reserva cancelada com sucesso.",
        }
    else:
        return {
            "status": "nao_encontrada",
            "mensagem": "Nenhuma reserva ativa encontrada com esses critérios para o seu apartamento.",
        }
