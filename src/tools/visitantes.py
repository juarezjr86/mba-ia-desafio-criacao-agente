"""Ferramentas para autorização e listagem de visitantes com confirmação de acesso e isolamento."""

from typing import Any

from google.adk.tools.tool_context import ToolContext

from ..db.repositorio import (
    autorizar_visitante as db_autorizar_visitante,
    obter_visitantes_apartamento as db_obter_visitantes,
)


def listar_meus_visitantes(tool_context: ToolContext) -> dict[str, Any]:
    """
    Lista todos os visitantes autorizados pertencentes exclusivamente ao apartamento da sessão (Garantia 2).
    """
    apartamento = str(tool_context.state.get("apartamento", ""))
    if not apartamento:
        return {"status": "erro", "mensagem": "Sessão sem apartamento vinculado."}

    visitantes = db_obter_visitantes(apartamento)
    return {
        "status": "sucesso",
        "apartamento": apartamento,
        "visitantes": visitantes,
    }


def autorizar_visitante(
    nome: str,
    data: str,
    tool_context: ToolContext,
) -> dict[str, Any]:
    """
    Cadastra a autorização de entrada de um visitante no condomínio.
    Por liberar acesso físico ao edifício (Regra 3 e Garantia 1), SEMPRE exige confirmação
    pela rota do sistema, mesmo que o morador afirme na conversa que já está confirmando.
    
    Args:
        nome: Nome completo do visitante.
        data: Data da visita no formato AAAA-MM-DD (ex.: '2030-04-21').
    """
    apartamento = str(tool_context.state.get("apartamento", ""))
    if not apartamento:
        return {"status": "erro", "mensagem": "Sessão inválida: apartamento ausente."}

    nome_formatado = nome.strip()

    # GARANTIA 1: Liberação de acesso sempre requer confirmação do sistema
    confirmation = tool_context.tool_confirmation
    if confirmation is None:
        # Pausa a execução e emite pedido de confirmação
        tool_context.request_confirmation(
            hint=f"Autorização de entrada para {nome_formatado} em {data}",
            payload={"nome": nome_formatado, "data": data},
        )
        return {
            "status": "pendente_confirmacao",
            "mensagem": f"A liberação de acesso para o visitante '{nome_formatado}' em {data} requer confirmação pela rota do sistema.",
            "nome": nome_formatado,
            "data": data,
        }

    # Avalia a resposta recebida
    if not confirmation.confirmed:
        return {
            "status": "recusada_pelo_morador",
            "mensagem": f"A autorização de entrada para '{nome_formatado}' em {data} foi recusada pelo morador.",
        }

    # Grava a autorização no banco de dados para o apartamento da sessão
    registro = db_autorizar_visitante(
        apartamento=apartamento,
        nome=nome_formatado,
        data=data,
    )

    return {
        "status": "sucesso",
        "nome": registro["nome"],
        "data": registro["data"],
        "apartamento": registro["apartamento"],
        "mensagem": f"Visitante '{registro['nome']}' autorizado com sucesso para a data {registro['data']}.",
    }
