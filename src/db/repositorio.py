"""Repositório de dados com operações atômicas, isolamento e integridade."""

from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sqlite3
from typing import Any

from .database import conectar, inicializar_banco


def obter_timestamp() -> str:
    """Retorna timestamp ISO 8601 UTC."""
    return datetime.now(timezone.utc).isoformat()


# --- APARTAMENTOS E ÁREAS ---


def obter_apartamentos() -> list[dict[str, Any]]:
    """Retorna todos os apartamentos cadastrados."""
    with conectar() as conn:
        cursor = conn.execute("SELECT numero, morador FROM apartamentos ORDER BY numero;")
        return [dict(row) for row in cursor.fetchall()]


def obter_apartamento(numero: str) -> dict[str, Any] | None:
    """Retorna um apartamento pelo número."""
    with conectar() as conn:
        cursor = conn.execute("SELECT numero, morador FROM apartamentos WHERE numero = ?;", (str(numero),))
        row = cursor.fetchone()
        return dict(row) if row else None


def obter_areas() -> list[dict[str, Any]]:
    """Retorna todas as áreas comuns cadastradas."""
    with conectar() as conn:
        cursor = conn.execute("SELECT id, nome, taxa FROM areas ORDER BY id;")
        return [dict(row) for row in cursor.fetchall()]


def obter_area(area_id: str) -> dict[str, Any] | None:
    """Retorna uma área comum pelo identificador."""
    with conectar() as conn:
        cursor = conn.execute("SELECT id, nome, taxa FROM areas WHERE id = ?;", (area_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# --- RESERVAS (GARANTIAS 1, 2 e 5) ---


def obter_reservas_apartamento(apartamento: str) -> list[dict[str, Any]]:
    """Retorna as reservas ativas de um apartamento (Garantia 2)."""
    with conectar() as conn:
        cursor = conn.execute(
            """
            SELECT codigo, area, data 
            FROM reservas 
            WHERE apartamento = ? AND status = 'ativa'
            ORDER BY data ASC;
            """,
            (str(apartamento),),
        )
        return [dict(row) for row in cursor.fetchall()]


def verificar_disponibilidade_area(area_id: str, data: str) -> bool:
    """Verifica se uma área está livre em determinada data (sem expor morador titular)."""
    with conectar() as conn:
        cursor = conn.execute(
            "SELECT 1 FROM reservas WHERE area = ? AND data = ? AND status = 'ativa';",
            (area_id, data),
        )
        return cursor.fetchone() is None


def _gerar_codigo_reserva_unico(conn: sqlite3.Connection) -> str:
    """Gera código RSV-XXXX que nunca repete nenhum código histórico (ativo ou cancelado)."""
    while True:
        # Sorteia código e valida contra toda a tabela de reservas (ativas e canceladas)
        num = random.randint(5000, 9999)
        codigo = f"RSV-{num}"
        cursor = conn.execute("SELECT 1 FROM reservas WHERE codigo = ?;", (codigo,))
        if cursor.fetchone() is None:
            return codigo


def criar_reserva(apartamento: str, area_id: str, data: str) -> dict[str, Any] | None:
    """
    Cria uma reserva com exclusividade atômica no instante da gravação (Garantia 5).
    Retorna os dados da reserva se bem-sucedida, ou None se houver colisão de agenda.
    """
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        try:
            codigo = _gerar_codigo_reserva_unico(conn)
            criado_em = obter_timestamp()
            conn.execute(
                """
                INSERT INTO reservas (codigo, apartamento, area, data, status, criado_em)
                VALUES (?, ?, ?, ?, 'ativa', ?);
                """,
                (codigo, str(apartamento), area_id, data, criado_em),
            )
            conn.execute("COMMIT;")
            return {
                "codigo": codigo,
                "apartamento": str(apartamento),
                "area": area_id,
                "data": data,
            }
        except sqlite3.IntegrityError:
            conn.execute("ROLLBACK;")
            return None


def cancelar_reserva(apartamento: str, area_id: str | None = None, data: str | None = None, codigo: str | None = None) -> bool:
    """
    Cancela uma reserva ativa do apartamento da sessão via soft-delete (Garantia 2).
    Apenas cancela se o apartamento pertencer estritamente ao morador da sessão.
    """
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        if codigo:
            cursor = conn.execute(
                """
                UPDATE reservas 
                SET status = 'cancelada' 
                WHERE codigo = ? AND apartamento = ? AND status = 'ativa';
                """,
                (codigo, str(apartamento)),
            )
        elif area_id and data:
            cursor = conn.execute(
                """
                UPDATE reservas 
                SET status = 'cancelada' 
                WHERE area = ? AND data = ? AND apartamento = ? AND status = 'ativa';
                """,
                (area_id, data, str(apartamento)),
            )
        elif data:
            cursor = conn.execute(
                """
                UPDATE reservas 
                SET status = 'cancelada' 
                WHERE data = ? AND apartamento = ? AND status = 'ativa';
                """,
                (data, str(apartamento)),
            )
        else:
            conn.execute("ROLLBACK;")
            return False

        afetados = cursor.rowcount
        conn.execute("COMMIT;")
        return afetados > 0


# --- VISITANTES (GARANTIAS 1 e 2) ---


def autorizar_visitante(apartamento: str, nome: str, data: str) -> dict[str, Any]:
    """Cadastra a autorização de visitante para o apartamento da sessão."""
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        criado_em = obter_timestamp()
        # Idempotente: reexecução da mesma autorização (retomada após falha) não duplica o registro
        existente = conn.execute(
            "SELECT 1 FROM visitantes WHERE apartamento = ? AND nome = ? AND data = ?;",
            (str(apartamento), nome.strip(), data),
        ).fetchone()
        if existente is None:
            conn.execute(
                """
                INSERT INTO visitantes (apartamento, nome, data, criado_em)
                VALUES (?, ?, ?, ?);
                """,
                (str(apartamento), nome.strip(), data, criado_em),
            )
        conn.execute("COMMIT;")
        return {
            "apartamento": str(apartamento),
            "nome": nome.strip(),
            "data": data,
        }


def obter_visitantes_apartamento(apartamento: str) -> list[dict[str, Any]]:
    """Retorna a lista de visitantes autorizados para o apartamento."""
    with conectar() as conn:
        cursor = conn.execute(
            """
            SELECT nome, data 
            FROM visitantes 
            WHERE apartamento = ?
            ORDER BY id ASC;
            """,
            (str(apartamento),),
        )
        return [dict(row) for row in cursor.fetchall()]


# --- CONFIRMAÇÕES PENDENTES (GARANTIA 1) ---


def salvar_confirmacao_pendente(
    id_confirmacao: str,
    session_id: str,
    invocation_id: str,
    acao: str,
    detalhes: dict[str, Any],
) -> None:
    """Registra uma confirmação pendente vinculada à sessão."""
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute(
            """
            INSERT OR REPLACE INTO confirmacoes_pendentes 
            (id, session_id, invocation_id, acao, detalhes, status, criado_em)
            VALUES (?, ?, ?, ?, ?, 'pendente', ?);
            """,
            (
                id_confirmacao,
                session_id,
                invocation_id,
                acao,
                json.dumps(detalhes, ensure_ascii=False),
                obter_timestamp(),
            ),
        )
        conn.execute("COMMIT;")


def obter_confirmacoes_pendentes(session_id: str) -> list[dict[str, Any]]:
    """Retorna todas as confirmações ativas (pendentes) da sessão."""
    with conectar() as conn:
        cursor = conn.execute(
            """
            SELECT id, acao, detalhes 
            FROM confirmacoes_pendentes 
            WHERE session_id = ? AND status = 'pendente'
            ORDER BY criado_em ASC;
            """,
            (session_id,),
        )
        resultado = []
        for row in cursor.fetchall():
            resultado.append({
                "id": row["id"],
                "acao": row["acao"],
                "detalhes": json.loads(row["detalhes"]),
            })
        return resultado


def consumir_confirmacao_pendente(session_id: str, id_confirmacao: str) -> dict[str, Any] | None:
    """
    Consome atomicamente uma confirmação pendente (Garantia 1).
    Retorna os dados da pendência se estava pendente, ou None se inexistente/já respondida (provocando 409).
    """
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        cursor = conn.execute(
            """
            SELECT id, session_id, invocation_id, acao, detalhes 
            FROM confirmacoes_pendentes 
            WHERE session_id = ? AND id = ? AND status = 'pendente';
            """,
            (session_id, id_confirmacao),
        )
        row = cursor.fetchone()
        if not row:
            conn.execute("ROLLBACK;")
            return None

        # Marca como respondida para prevenir reenvio
        conn.execute(
            "UPDATE confirmacoes_pendentes SET status = 'respondida' WHERE id = ?;",
            (id_confirmacao,),
        )
        conn.execute("COMMIT;")
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "invocation_id": row["invocation_id"],
            "acao": row["acao"],
            "detalhes": json.loads(row["detalhes"]),
        }


def reverter_confirmacao_pendente(session_id: str, id_confirmacao: str) -> None:
    """Devolve a pendência ao estado 'pendente' quando a retomada do Runner falhou, para permitir novo envio."""
    with conectar() as conn:
        conn.execute("BEGIN IMMEDIATE;")
        conn.execute(
            "UPDATE confirmacoes_pendentes SET status = 'pendente' WHERE session_id = ? AND id = ? AND status = 'respondida';",
            (session_id, id_confirmacao),
        )
        conn.execute("COMMIT;")
