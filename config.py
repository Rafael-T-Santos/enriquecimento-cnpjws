"""Carrega a configuração a partir do arquivo .env / variáveis de ambiente."""
import os
from dotenv import load_dotenv

# override=False: se a variável já existir no ambiente do Windows, ela vence.
# Assim reaproveitamos DB_USER/DB_PASS/DB_DSN já configurados para a internal-api-sankhya.
load_dotenv(override=False)

DB_USER = os.environ.get("DB_USER")
DB_PASS = os.environ.get("DB_PASS")
DB_DSN = os.environ.get("DB_DSN")

CNPJWS_TOKEN = os.environ.get("CNPJWS_TOKEN")

DB_SQLITE = os.environ.get("DB_SQLITE", "enriquecimento.db")
CNPJWS_DELAY = float(os.environ.get("CNPJWS_DELAY", "0.3"))


def validar():
    """Garante que o mínimo necessário está configurado antes de rodar."""
    faltando = []
    if not DB_USER:
        faltando.append("DB_USER")
    if not DB_PASS:
        faltando.append("DB_PASS")
    if not DB_DSN:
        faltando.append("DB_DSN")
    if not CNPJWS_TOKEN:
        faltando.append("CNPJWS_TOKEN")
    if faltando:
        raise SystemExit(
            "Configuração faltando: " + ", ".join(faltando) +
            ".\nDefina no arquivo .env ou nas variáveis de ambiente do Windows."
        )
