"""Definição do esquema DDL do banco de dados relacional SQLite do condomínio."""

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS apartamentos (
    numero TEXT PRIMARY KEY,
    morador TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS areas (
    id TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    taxa REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS reservas (
    codigo TEXT PRIMARY KEY,
    apartamento TEXT NOT NULL REFERENCES apartamentos(numero),
    area TEXT NOT NULL REFERENCES areas(id),
    data TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('ativa', 'cancelada')),
    criado_em TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_reservas_area_data_ativa 
ON reservas(area, data) WHERE status = 'ativa';

CREATE TABLE IF NOT EXISTS visitantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    apartamento TEXT NOT NULL REFERENCES apartamentos(numero),
    nome TEXT NOT NULL,
    data TEXT NOT NULL,
    criado_em TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS confirmacoes_pendentes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    invocation_id TEXT NOT NULL,
    acao TEXT NOT NULL,
    detalhes TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('pendente', 'respondida')),
    criado_em TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_confirmacoes_session_status 
ON confirmacoes_pendentes(session_id, status);
"""
