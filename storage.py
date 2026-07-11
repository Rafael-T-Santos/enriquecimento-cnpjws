"""Camada de persistência em SQLite: execuções e consultas."""
import sqlite3
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    rotulo          TEXT,
    iniciado_em     TEXT NOT NULL,
    finalizado_em   TEXT,
    total_parceiros INTEGER,
    total_ok        INTEGER DEFAULT 0,
    total_erro      INTEGER DEFAULT 0,
    total_invalido  INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS consultas (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    execucao_id              INTEGER NOT NULL REFERENCES execucoes(id),
    codparc                  INTEGER NOT NULL,
    nomeparc                 TEXT,
    cgc_cpf                  TEXT,
    cnpj                     TEXT,
    status                   TEXT NOT NULL,   -- OK | ERRO | CNPJ_INVALIDO | NAO_ENCONTRADO
    http_status              INTEGER,
    erro                     TEXT,
    -- Empresa
    razao_social                TEXT,
    nome_fantasia               TEXT,
    cnpj_raiz                   TEXT,
    tipo_estabelecimento        TEXT,
    capital_social              TEXT,
    porte                       TEXT,
    natureza_juridica           TEXT,
    qualificacao_responsavel    TEXT,
    responsavel_federativo      TEXT,
    dados_atualizado_em         TEXT,
    -- Situação cadastral
    situacao_cadastral          TEXT,
    data_situacao_cadastral     TEXT,
    motivo_situacao_cadastral   TEXT,
    situacao_especial           TEXT,
    data_situacao_especial      TEXT,
    data_inicio_atividade       TEXT,
    -- Atividades (CNAE)
    cnae_principal_codigo       TEXT,
    cnae_principal_descricao    TEXT,
    cnae_secundarios            TEXT,
    -- Endereço
    tipo_logradouro             TEXT,
    logradouro                  TEXT,
    numero                      TEXT,
    complemento                 TEXT,
    bairro                      TEXT,
    municipio                   TEXT,
    uf                          TEXT,
    cep                         TEXT,
    pais                        TEXT,
    nome_cidade_exterior        TEXT,
    -- Contato
    email                       TEXT,
    telefone                    TEXT,
    telefone2                   TEXT,
    fax                         TEXT,
    -- Inscrições
    inscricao_estadual          TEXT,
    inscricoes_estaduais_todas  TEXT,
    inscricoes_suframa          TEXT,
    -- Fiscal
    opta_simples                TEXT,
    data_opcao_simples          TEXT,
    data_exclusao_simples       TEXT,
    opta_mei                    TEXT,
    data_opcao_mei              TEXT,
    data_exclusao_mei           TEXT,
    regime_tributario           TEXT,
    regime_tributario_ano       INTEGER,
    -- Quadro societário
    socios                      TEXT,
    json_completo            TEXT,
    consultado_em            TEXT,
    UNIQUE(execucao_id, codparc)
);
"""

# Colunas de resultado gravadas em cada consulta (na ordem do INSERT).
# A ordem aqui define a ordem das colunas no CSV exportado.
COLUNAS_RESULTADO = [
    # Empresa
    "razao_social", "nome_fantasia", "cnpj_raiz", "tipo_estabelecimento",
    "capital_social", "porte", "natureza_juridica", "qualificacao_responsavel",
    "responsavel_federativo", "dados_atualizado_em",
    # Situação cadastral
    "situacao_cadastral", "data_situacao_cadastral", "motivo_situacao_cadastral",
    "situacao_especial", "data_situacao_especial", "data_inicio_atividade",
    # Atividades
    "cnae_principal_codigo", "cnae_principal_descricao", "cnae_secundarios",
    # Endereço
    "tipo_logradouro", "logradouro", "numero", "complemento", "bairro",
    "municipio", "uf", "cep", "pais", "nome_cidade_exterior",
    # Contato
    "email", "telefone", "telefone2", "fax",
    # Inscrições
    "inscricao_estadual", "inscricoes_estaduais_todas", "inscricoes_suframa",
    # Fiscal
    "opta_simples", "data_opcao_simples", "data_exclusao_simples",
    "opta_mei", "data_opcao_mei", "data_exclusao_mei",
    "regime_tributario", "regime_tributario_ano",
    # Quadro societário
    "socios",
]


def _agora():
    return datetime.now().isoformat(timespec="seconds")


class Storage:
    def __init__(self, caminho):
        self.conn = sqlite3.connect(caminho)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        self.conn.close()

    # ---------------- Execuções ----------------

    def criar_execucao(self, rotulo, total_parceiros):
        cur = self.conn.execute(
            "INSERT INTO execucoes (rotulo, iniciado_em, total_parceiros) VALUES (?, ?, ?)",
            (rotulo, _agora(), total_parceiros),
        )
        self.conn.commit()
        return cur.lastrowid

    def execucao_aberta(self):
        """Retorna a última execução não finalizada, ou None."""
        row = self.conn.execute(
            "SELECT * FROM execucoes WHERE finalizado_em IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row

    def obter_execucao(self, execucao_id):
        return self.conn.execute(
            "SELECT * FROM execucoes WHERE id = ?", (execucao_id,)
        ).fetchone()

    def finalizar_execucao(self, execucao_id):
        self.conn.execute(
            "UPDATE execucoes SET finalizado_em = ? WHERE id = ?",
            (_agora(), execucao_id),
        )
        self.conn.commit()

    def atualizar_totais(self, execucao_id):
        row = self.conn.execute(
            """
            SELECT
                SUM(CASE WHEN status = 'OK' THEN 1 ELSE 0 END) AS ok,
                SUM(CASE WHEN status IN ('ERRO', 'NAO_ENCONTRADO') THEN 1 ELSE 0 END) AS erro,
                SUM(CASE WHEN status = 'CNPJ_INVALIDO' THEN 1 ELSE 0 END) AS invalido
            FROM consultas WHERE execucao_id = ?
            """,
            (execucao_id,),
        ).fetchone()
        self.conn.execute(
            "UPDATE execucoes SET total_ok = ?, total_erro = ?, total_invalido = ? WHERE id = ?",
            (row["ok"] or 0, row["erro"] or 0, row["invalido"] or 0, execucao_id),
        )
        self.conn.commit()

    def listar_execucoes(self):
        return self.conn.execute(
            "SELECT * FROM execucoes ORDER BY id DESC"
        ).fetchall()

    # ---------------- Consultas ----------------

    def codparcs_ja_ok(self, execucao_id):
        """Set de codparc já consultados com sucesso nesta execução (para retomar)."""
        rows = self.conn.execute(
            "SELECT codparc FROM consultas WHERE execucao_id = ? AND status = 'OK'",
            (execucao_id,),
        ).fetchall()
        return {r["codparc"] for r in rows}

    def salvar_consulta(self, execucao_id, parceiro, cnpj, status,
                        http_status=None, erro=None, campos=None, json_completo=None):
        campos = campos or {}
        valores = [campos.get(c) for c in COLUNAS_RESULTADO]
        # UPSERT: se rodar de novo a mesma execução, sobrescreve a linha do parceiro.
        self.conn.execute(
            f"""
            INSERT INTO consultas (
                execucao_id, codparc, nomeparc, cgc_cpf, cnpj, status, http_status, erro,
                {", ".join(COLUNAS_RESULTADO)},
                json_completo, consultado_em
            ) VALUES ({", ".join(["?"] * (8 + len(COLUNAS_RESULTADO) + 2))})
            ON CONFLICT(execucao_id, codparc) DO UPDATE SET
                nomeparc=excluded.nomeparc, cgc_cpf=excluded.cgc_cpf, cnpj=excluded.cnpj,
                status=excluded.status, http_status=excluded.http_status, erro=excluded.erro,
                {", ".join(f"{c}=excluded.{c}" for c in COLUNAS_RESULTADO)},
                json_completo=excluded.json_completo, consultado_em=excluded.consultado_em
            """,
            [
                execucao_id, parceiro["codparc"], parceiro.get("nomeparc"),
                parceiro.get("cgc_cpf"), cnpj, status, http_status, erro,
                *valores, json_completo, _agora(),
            ],
        )
        self.conn.commit()

    def consultas_da_execucao(self, execucao_id):
        return self.conn.execute(
            "SELECT * FROM consultas WHERE execucao_id = ? ORDER BY codparc",
            (execucao_id,),
        ).fetchall()
