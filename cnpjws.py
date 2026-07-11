"""Cliente da API comercial do cnpj.ws."""
import re
import time
import requests

BASE_URL = "https://comercial.cnpj.ws/cnpj/"


def limpar_cnpj(valor):
    """Deixa só os dígitos. Retorna None se não for um CNPJ válido.

    Valida os dígitos verificadores, então CNPJs estruturalmente inválidos
    (00000000000000, dígitos repetidos, erros de digitação) são rejeitados aqui
    e nem chegam a gastar uma consulta na API.
    """
    if not valor:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    if len(digitos) != 14 or not _cnpj_dv_valido(digitos):
        return None
    return digitos


def _cnpj_dv_valido(cnpj):
    """Confere os dois dígitos verificadores de um CNPJ de 14 dígitos."""
    if cnpj == cnpj[0] * 14:  # todos os dígitos iguais (00000..., 11111...)
        return False

    def dv(base, pesos):
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(cnpj[:12], pesos1)
    d2 = dv(cnpj[:12] + d1, pesos2)
    return cnpj[12:] == d1 + d2


class CnpjWsClient:
    def __init__(self, token, delay=0.3, timeout=30, max_tentativas=4):
        self.delay = delay
        self.timeout = timeout
        self.max_tentativas = max_tentativas
        self.session = requests.Session()
        self.session.headers.update({"x_api_token": token})

    def consultar(self, cnpj):
        """
        Consulta um CNPJ (14 dígitos, só números).
        Retorna (http_status, dados_json_ou_None, mensagem_erro_ou_None).
        Trata rate limit (429) e erros de servidor (5xx) com novas tentativas.
        """
        url = BASE_URL + cnpj
        tentativa = 0
        while True:
            tentativa += 1
            try:
                resp = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as e:
                if tentativa < self.max_tentativas:
                    time.sleep(2 * tentativa)
                    continue
                return None, None, f"Falha de conexão: {e}"

            if resp.status_code == 200:
                return resp.status_code, resp.json(), None

            if resp.status_code == 404:
                return resp.status_code, None, "CNPJ não encontrado na Receita"

            # Rate limit: espera o tempo pedido (ou um padrão) e tenta de novo.
            if resp.status_code == 429 and tentativa < self.max_tentativas:
                espera = _retry_after(resp, padrao=5)
                print(f"    Rate limit (429). Aguardando {espera}s...")
                time.sleep(espera)
                continue

            if resp.status_code >= 500 and tentativa < self.max_tentativas:
                time.sleep(2 * tentativa)
                continue

            # Erro definitivo.
            return resp.status_code, None, f"HTTP {resp.status_code}: {resp.text[:200]}"


def _retry_after(resp, padrao):
    valor = resp.headers.get("Retry-After")
    try:
        return int(valor)
    except (TypeError, ValueError):
        return padrao


def extrair_campos(dados):
    """Extrai TODOS os campos do JSON da cnpj.ws para colunas planas.

    Listas (CNAEs secundários, sócios, inscrições) são achatadas em uma única
    coluna, com os itens separados por ' | '. O JSON bruto continua salvo em
    json_completo para qualquer detalhe que não vire coluna.
    """
    est = dados.get("estabelecimento") or {}
    ativ = est.get("atividade_principal") or {}
    simples = dados.get("simples") or {}
    uf = (est.get("estado") or {}).get("sigla")

    ie_principal, ie_todas = _extrair_inscricoes_estaduais(est, uf)
    regime, regime_ano = _regime_mais_recente(est.get("regimes_tributarios"))

    return {
        # --- Empresa (raiz) ---
        "razao_social": dados.get("razao_social"),
        "nome_fantasia": est.get("nome_fantasia"),
        "cnpj_raiz": dados.get("cnpj_raiz"),
        "tipo_estabelecimento": est.get("tipo"),  # Matriz / Filial
        "capital_social": dados.get("capital_social"),
        "porte": _desc(dados.get("porte")),
        "natureza_juridica": _desc(dados.get("natureza_juridica")),
        "qualificacao_responsavel": _desc(dados.get("qualificacao_do_responsavel")),
        "responsavel_federativo": dados.get("responsavel_federativo") or None,
        "dados_atualizado_em": dados.get("atualizado_em"),

        # --- Situação cadastral ---
        "situacao_cadastral": est.get("situacao_cadastral"),
        "data_situacao_cadastral": est.get("data_situacao_cadastral"),
        "motivo_situacao_cadastral": _desc(est.get("motivo_situacao_cadastral")),
        "situacao_especial": est.get("situacao_especial"),
        "data_situacao_especial": est.get("data_situacao_especial"),
        "data_inicio_atividade": est.get("data_inicio_atividade"),

        # --- Atividades (CNAE) ---
        "cnae_principal_codigo": ativ.get("subclasse") or ativ.get("id"),
        "cnae_principal_descricao": ativ.get("descricao"),
        "cnae_secundarios": _flat_cnaes(est.get("atividades_secundarias")),

        # --- Endereço ---
        "tipo_logradouro": est.get("tipo_logradouro"),
        "logradouro": est.get("logradouro"),
        "numero": est.get("numero"),
        "complemento": est.get("complemento"),
        "bairro": est.get("bairro"),
        "municipio": (est.get("cidade") or {}).get("nome"),
        "uf": uf,
        "cep": est.get("cep"),
        "pais": (est.get("pais") or {}).get("nome"),
        "nome_cidade_exterior": est.get("nome_cidade_exterior"),

        # --- Contato ---
        "email": est.get("email"),
        "telefone": _telefone(est.get("ddd1"), est.get("telefone1")),
        "telefone2": _telefone(est.get("ddd2"), est.get("telefone2")),
        "fax": _telefone(est.get("ddd_fax"), est.get("fax")),

        # --- Inscrições ---
        "inscricao_estadual": ie_principal,
        "inscricoes_estaduais_todas": ie_todas,
        "inscricoes_suframa": _flat_suframa(est.get("inscricoes_suframa")),

        # --- Fiscal (Simples / MEI / Regime tributário) ---
        "opta_simples": simples.get("simples"),
        "data_opcao_simples": simples.get("data_opcao_simples"),
        "data_exclusao_simples": simples.get("data_exclusao_simples"),
        "opta_mei": simples.get("mei"),
        "data_opcao_mei": simples.get("data_opcao_mei"),
        "data_exclusao_mei": simples.get("data_exclusao_mei"),
        "regime_tributario": regime,
        "regime_tributario_ano": regime_ano,

        # --- Quadro societário ---
        "socios": _flat_socios(dados.get("socios")),
    }


def _desc(obj):
    """Retorna a 'descricao' de um objeto {id, descricao}, ou o próprio valor."""
    if isinstance(obj, dict):
        d = obj.get("descricao")
        return d.strip() if isinstance(d, str) else d
    return obj or None


def _telefone(ddd, numero):
    if not numero:
        return None
    return f"({ddd}) {numero}" if ddd else str(numero)


def _regime_mais_recente(regimes):
    """Do array regimes_tributarios, retorna (regime, ano) do ano mais recente."""
    if not regimes:
        return None, None
    mais = max(regimes, key=lambda r: r.get("ano") or 0)
    return mais.get("regime_tributario"), mais.get("ano")


def _flat_cnaes(lista):
    """'4711-3/02 Comércio... | 4623-1/09 Comércio...' para os CNAEs secundários."""
    if not lista:
        return None
    partes = []
    for item in lista:
        cod = item.get("subclasse") or item.get("id")
        partes.append(f"{cod} {item.get('descricao') or ''}".strip())
    return " | ".join(partes)


def _flat_socios(lista):
    """'NOME (Qualificação, entrada AAAA-MM-DD) | ...' para o quadro societário."""
    if not lista:
        return None
    partes = []
    for s in lista:
        nome = s.get("nome") or ""
        qual = _desc(s.get("qualificacao_socio"))
        entrada = s.get("data_entrada")
        detalhe = ", ".join(x for x in [qual, f"entrada {entrada}" if entrada else None] if x)
        partes.append(f"{nome} ({detalhe})" if detalhe else nome)
    return " | ".join(partes)


def _flat_suframa(lista):
    if not lista:
        return None
    partes = []
    for item in lista:
        numero = item.get("inscricao_suframa") or item.get("numero")
        sigla = (item.get("estado") or {}).get("sigla")
        marca = "" if item.get("ativo", True) else " (inativa)"
        partes.append(f"{sigla}:{numero}{marca}" if sigla else f"{numero}{marca}")
    return " | ".join(partes)


def _extrair_inscricoes_estaduais(est, uf):
    """
    A partir de estabelecimento.inscricoes_estaduais, retorna:
      - ie_principal: a inscrição do estado do estabelecimento (UF), preferindo a
        ativa; se não houver, a primeira ativa; se nenhuma ativa, a primeira.
      - ie_todas: string com todas as inscrições no formato
        "SP:110042490114, MG:0621783250082 (inativa)".
    """
    lista = est.get("inscricoes_estaduais") or []
    if not lista:
        return None, None

    partes = []
    ie_principal = None
    for item in lista:
        numero = item.get("inscricao_estadual")
        ativo = item.get("ativo")
        sigla = (item.get("estado") or {}).get("sigla")

        marca = "" if ativo else " (inativa)"
        rotulo = f"{sigla}:{numero}" if sigla else str(numero)
        partes.append(f"{rotulo}{marca}")

        # Escolhe a principal: prioriza a do estado do estabelecimento e ativa.
        if numero and _melhor_ie(item, ie_principal, uf, sigla, ativo):
            ie_principal = numero

    return ie_principal, ", ".join(partes)


def _melhor_ie(item, atual_numero, uf, sigla, ativo):
    """Regra de desempate para escolher a inscrição estadual principal."""
    if atual_numero is None:
        return True
    # Uma inscrição do próprio estado (UF) e ativa sempre vence.
    if uf and sigla == uf and ativo:
        return True
    return False
