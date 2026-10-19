"""Ferramenta para consulta seletiva ao Regulamento Interno do Residencial Aurora (Garantia 4)."""

from pathlib import Path
import re
from typing import Any

from google.adk.tools.tool_context import ToolContext

REGULAMENTO_PATH = Path("dados/regulamento.md")


def _carregar_capitulos() -> list[dict[str, str]]:
    """Lê o regulamento e segmenta o texto estritamente por capítulos."""
    if not REGULAMENTO_PATH.exists():
        return []

    with open(REGULAMENTO_PATH, "r", encoding="utf-8") as f:
        conteudo = f.read()

    # Divide por cabeçalhos de capítulos (## Capítulo ...)
    partes = re.split(r"(?m)^(?=##\s+Capítulo\s+)", conteudo)
    capitulos = []

    for parte in partes:
        parte = parte.strip()
        if not parte:
            continue
        linhas = parte.splitlines()
        titulo = linhas[0] if linhas else ""
        capitulos.append({
            "titulo": titulo,
            "conteudo": parte,
        })

    return capitulos


def consultar_regulamento(topico: str, tool_context: ToolContext | None = None) -> dict[str, Any]:
    """
    Consulta o regulamento interno do condomínio sobre um tema específico.
    Retorna estritamente o trecho ou capítulo pertinente, sem vazar outros assuntos (Garantia 4).
    
    Args:
        topico: O assunto a ser consultado (ex.: 'piscina', 'salao de festas', 'barulho', 'animais', 'garagem').
    """
    termo = topico.lower().strip()
    capitulos = _carregar_capitulos()

    # 1. Busca por correspondência no título do capítulo
    for cap in capitulos:
        if termo in cap["titulo"].lower():
            return {
                "topico": topico,
                "resultado": cap["conteudo"],
            }

    # 2. Busca por palavras-chave principais no corpo dos capítulos
    mapeamento_palavras = {
        "piscina": "Piscina",
        "domingo": "Piscina",
        "horario": "Piscina",
        "festa": "Salão de festas",
        "churrasqueira": "Salão de festas",
        "quadra": "Quadra",
        "animal": "Animais",
        "pet": "Animais",
        "cachorro": "Animais",
        "carro": "Garagem",
        "garagem": "Garagem",
        "vaga": "Garagem",
        "obra": "Mudanças",
        "mudanca": "Mudanças",
        "reforma": "Mudanças",
        "multa": "Penalidades",
        "penalidade": "Penalidades",
    }

    capitulo_alvo = None
    for palavra, titulo_chave in mapeamento_palavras.items():
        if palavra in termo:
            capitulo_alvo = titulo_chave
            break

    if capitulo_alvo:
        for cap in capitulos:
            if capitulo_alvo.lower() in cap["titulo"].lower():
                return {
                    "topico": topico,
                    "resultado": cap["conteudo"],
                }

    # 3. Busca por ocorrência exata dentro do texto
    for cap in capitulos:
        if termo in cap["conteudo"].lower():
            # Retorna apenas o capítulo que contém a menção
            return {
                "topico": topico,
                "resultado": cap["conteudo"],
            }

    return {
        "topico": topico,
        "resultado": "Nao foram encontradas disposicoes especificas sobre este assunto no regulamento interno.",
    }
