"""Acesso ao Oracle do Sankhya: busca os parceiros a serem enriquecidos."""
import cx_Oracle
import config

# Parceiros pessoa jurídica (TIPPESSOA <> 'F'), que tenham documento preenchido.
SQL_PARCEIROS = """
    SELECT CODPARC, NOMEPARC, CGC_CPF, TIPPESSOA
    FROM TGFPAR
    WHERE TIPPESSOA <> 'F'
      AND CGC_CPF IS NOT NULL
    ORDER BY CODPARC
"""


def conectar():
    print(f"Conectando ao Oracle ({config.DB_DSN})...")
    conexao = cx_Oracle.connect(
        user=config.DB_USER,
        password=config.DB_PASS,
        dsn=config.DB_DSN,
    )
    print("Conexão com Oracle bem-sucedida!")
    return conexao


def buscar_parceiros():
    """Retorna a lista de parceiros como dicts: codparc, nomeparc, cgc_cpf, tippessoa."""
    conexao = conectar()
    try:
        cursor = conexao.cursor()
        cursor.execute(SQL_PARCEIROS)
        colunas = [c[0].lower() for c in cursor.description]
        parceiros = [dict(zip(colunas, linha)) for linha in cursor]
        print(f"{len(parceiros)} parceiros pessoa jurídica encontrados no Sankhya.")
        return parceiros
    finally:
        conexao.close()
