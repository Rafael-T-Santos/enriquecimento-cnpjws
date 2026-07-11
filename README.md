# Enriquecimento de parceiros via cnpj.ws

Projeto separado que lê os parceiros **pessoa jurídica** do Sankhya
(`TGFPAR` onde `TIPPESSOA <> 'F'`), consulta cada CNPJ na
[API comercial do cnpj.ws](https://docs.cnpj.ws) e salva os dados enriquecidos
num banco **SQLite** local.

Cada vez que o processo roda vira uma **execução** com um id próprio, então dá
pra rodar quantas vezes quiser mantendo o histórico separado. Uma execução
interrompida pode ser **retomada** de onde parou.

## Onde rodar

O comando `rodar` conecta no Oracle do Sankhya (`192.168.255.250:1521/xe`), que
**só é acessível de dentro da rede da empresa** — na prática, da mesma máquina
Linux onde a `internal-api-sankhya` roda. De um PC de desenvolvimento fora da
rede a conexão dá timeout (`ORA-12170`), mesmo com as credenciais corretas.

Por isso o jeito recomendado é rodar via **Docker no Linux**, do mesmo modo que a
internal-api. Os comandos offline (`execucoes`, `exportar`) funcionam em
qualquer lugar, pois só leem o SQLite local.

## Rodando no Linux com Docker (recomendado)

Pré-requisito: `docker` e `docker compose` instalados (a máquina que builda a
internal-api já tem).

```bash
# 1. Trazer o código (mesmo fluxo da internal-api: pull do repositório)
git pull

# 2. Criar o .env com as credenciais (fica no .gitignore, não vem pelo git).
#    São as MESMAS do .env da internal-api, mais o token do cnpj.ws:
cat > .env <<'EOF'
DB_USER=sankhya
DB_PASS=sua_senha
DB_DSN=192.168.255.250:1521/xe
CNPJWS_TOKEN=DFNBJFE3NR5mYw2ze92CESzPRMobLsSRdFEviRC6kMox
CNPJWS_DELAY=0.3
DB_SQLITE=enriquecimento.db
EOF

# 3. Buildar a imagem (baixa o Oracle Instant Client; precisa de internet)
docker compose build

# 4. Teste rápido com 20 parceiros reais
docker compose run --rm enriquecimento rodar --limite 20 --nova

# 5. Exportar o CSV (sai em ./exports/, salvo aqui no host pelo volume)
docker compose run --rm enriquecimento exportar
```

`enriquecimento.db` e a pasta `exports/` ficam salvos na própria pasta do
projeto no host (o `docker-compose.yml` monta `.:/app`).

## Instalação sem Docker (só onde há acesso ao Oracle + Instant Client)

```bash
cd enriquecimento-cnpjws
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

> `cx_Oracle` precisa do Oracle Instant Client instalado na máquina
> (o mesmo que a internal-api-sankhya já usa).

## Configuração

Copie `.env.example` para `.env` e ajuste. O `.env` já vem com o token do
cnpj.ws preenchido. As credenciais do banco (`DB_USER`, `DB_PASS`, `DB_DSN`)
são reaproveitadas das variáveis de ambiente do Windows que a
internal-api-sankhya já usa — só defina no `.env` se quiser sobrescrever.

| Variável        | Descrição                                             |
|-----------------|-------------------------------------------------------|
| `DB_USER`       | Usuário do Oracle                                     |
| `DB_PASS`       | Senha do Oracle                                       |
| `DB_DSN`        | Ex: `192.168.255.250:1521/xe`                         |
| `CNPJWS_TOKEN`  | Token da API comercial do cnpj.ws                     |
| `DB_SQLITE`     | Caminho do banco SQLite (padrão `enriquecimento.db`)  |
| `CNPJWS_DELAY`  | Pausa em segundos entre chamadas (padrão `0.3`)       |

## Uso

```bash
# Teste rápido com 20 parceiros antes de soltar em cima de tudo
python enriquecer.py rodar --limite 20 --nova

# Roda tudo (nova execução, reconsultando todos os parceiros)
python enriquecer.py rodar --nova

# Retoma uma execução interrompida de onde parou
python enriquecer.py rodar

# Lista as execuções já feitas (com id, totais e status)
python enriquecer.py execucoes

# Exporta a execução mais recente para CSV
python enriquecer.py exportar

# Exporta uma execução específica para um caminho
python enriquecer.py exportar --execucao 3 --saida saida.csv
```

O CSV sai com `;` como separador e BOM UTF-8, pronto pra abrir no Excel.

## O que fica salvo

- **`execucoes`**: id, rótulo, início/fim, e totais (ok / erro / inválido).
- **`consultas`**: uma linha por parceiro por execução, com **todos** os campos
  que a API do cnpj.ws retorna já extraídos para colunas (ver lista abaixo),
  **mais** o JSON completo da resposta na coluna `json_completo`, como rede de
  segurança para qualquer detalhe que não virou coluna.

Status possíveis de cada consulta: `OK`, `NAO_ENCONTRADO` (404 na Receita),
`ERRO` (falha na API) e `CNPJ_INVALIDO` (documento não tem 14 dígitos).

### Campos exportados no CSV

Além de `codparc`, `nomeparc`, `cgc_cpf`, `cnpj`, `status`, `http_status`,
`erro` e `consultado_em`, cada linha traz:

| Grupo | Colunas |
|-------|---------|
| **Empresa** | `razao_social`, `nome_fantasia`, `cnpj_raiz`, `tipo_estabelecimento` (Matriz/Filial), `capital_social`, `porte`, `natureza_juridica`, `qualificacao_responsavel`, `responsavel_federativo`, `dados_atualizado_em` |
| **Situação cadastral** | `situacao_cadastral`, `data_situacao_cadastral`, `motivo_situacao_cadastral`, `situacao_especial`, `data_situacao_especial`, `data_inicio_atividade` |
| **Atividade (CNAE)** | `cnae_principal_codigo`, `cnae_principal_descricao`, `cnae_secundarios` |
| **Endereço** | `tipo_logradouro`, `logradouro`, `numero`, `complemento`, `bairro`, `municipio`, `uf`, `cep`, `pais`, `nome_cidade_exterior` |
| **Contato** | `email`, `telefone`, `telefone2`, `fax` |
| **Inscrições** | `inscricao_estadual`, `inscricoes_estaduais_todas`, `inscricoes_suframa` |
| **Fiscal** | `opta_simples`, `data_opcao_simples`, `data_exclusao_simples`, `opta_mei`, `data_opcao_mei`, `data_exclusao_mei`, `regime_tributario`, `regime_tributario_ano` |
| **Quadro societário** | `socios` |

Observações:
- `inscricao_estadual` é a inscrição **ativa do estado do estabelecimento**;
  `inscricoes_estaduais_todas` lista todas (de todos os estados), no formato
  `SP:110042490114, MG:0621783250082 (inativa)`.
- Listas (`cnae_secundarios`, `inscricoes_suframa`, `socios`) são gravadas numa
  única coluna, com os itens separados por ` | `.
