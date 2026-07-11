# Como rodar o enriquecimento (runbook)

Tutorial prático para rodar o enriquecimento de parceiros na **máquina Linux**
(`nd-db-02`), que é a única com acesso ao Oracle do Sankhya. Roda tudo em
Docker, em background, e sobrevive à desconexão do SSH.

> **Onde rodar:** sempre no Linux, na pasta `~/enriquecimento-cnpjws`.
> De fora da rede da empresa a conexão com o Oracle dá timeout (`ORA-12170`).

---

## Cola rápida

```bash
cd ~/enriquecimento-cnpjws

# 1. Atualizar código (quando houver mudança) e reconstruir a imagem
git pull && docker compose build

# 2. Rodar tudo em background (roda + retoma se cair + exporta no fim)
nohup sh -c '
  docker compose run --rm -e PYTHONUNBUFFERED=1 enriquecimento rodar --nova
  while [ $? -ne 0 ]; do
    echo ">>> interrompido, retomando em 15s..."
    sleep 15
    docker compose run --rm -e PYTHONUNBUFFERED=1 enriquecimento rodar
  done
  docker compose run --rm enriquecimento exportar
  echo "===ENRIQUECIMENTO CONCLUIDO==="
' > run.log 2>&1 &
echo "Rodando em background (PID $!). Pode dar 'exit' no SSH."

# 3. (pode desconectar) Depois, reconectar e conferir:
cd ~/enriquecimento-cnpjws
grep -c '===ENRIQUECIMENTO CONCLUIDO===' run.log   # 1 = terminou
tail -n 40 run.log                                 # progresso
ls -la exports/                                    # o CSV gerado
```

---

## Passo a passo detalhado

### 0. Pré-requisitos (só na primeira vez)

- Estar na máquina Linux da empresa, dentro da rede que enxerga o Oracle.
- Ter `docker` e `docker compose` instalados.
- Ter o repositório clonado: `git clone <url> ~/enriquecimento-cnpjws`
- Criar o arquivo `.env` na pasta (ele **não** vem pelo git):

  ```bash
  cd ~/enriquecimento-cnpjws
  cat > .env <<'EOF'
  DB_USER=sankhya
  DB_PASS=SUA_SENHA
  DB_DSN=192.168.255.250:1521/xe
  CNPJWS_TOKEN=SEU_TOKEN_CNPJWS
  CNPJWS_DELAY=0.3
  DB_SQLITE=enriquecimento.db
  EOF
  ```

### 1. Atualizar quando houver mudança de código

Sempre que o código mudar (push feito na máquina de desenvolvimento):

```bash
cd ~/enriquecimento-cnpjws
git pull
docker compose build      # reconstrói a imagem com o código novo
```

> Se **só** os dados mudaram (não o código), não precisa `build`.

### 2. Rodar a base completa em background

Use o bloco da **Cola rápida** (passo 2). Ele:

- roda todos os parceiros (`rodar --nova`);
- se cair no meio (rede/API), **retoma sozinho** a cada 15s pulando os que já
  deram `OK`;
- ao terminar, **exporta o CSV** automaticamente;
- escreve tudo em `run.log`;
- com `nohup ... &`, continua rodando mesmo depois do `exit` no SSH.

Depois de disparar, pode fechar o SSH.

### 3. Acompanhar / conferir o resultado

Reconecte por SSH e:

```bash
cd ~/enriquecimento-cnpjws

# Terminou? (retorna 1 quando concluiu)
grep -c '===ENRIQUECIMENTO CONCLUIDO===' run.log

# Ver as últimas linhas do progresso (mostra [i/total] por parceiro)
tail -n 40 run.log

# Ver ao vivo (Ctrl+C para sair do tail, não mata o processo)
tail -f run.log

# Ainda tem container rodando?
docker ps --filter name=enriquecimento

# Resumo das execuções (ok / erro / inválido)
docker compose run --rm enriquecimento execucoes

# O CSV fica em exports/ — pegue o mais recente
ls -la exports/
```

O CSV sai com `;` e BOM UTF-8 (abre direto no Excel), com todas as colunas.

### 4. Conferir os que não deram OK

```bash
# Troque N pelo número da execução (ex.: execucao_2.csv)
CSV=exports/execucao_N.csv

# Contagem por status
cut -d';' -f5 "$CSV" | tail -n +2 | sort | uniq -c

# Detalhe dos que não deram OK: codparc | nome | cnpj | status | http | erro
awk -F';' 'NR==1 || $5!="OK"' "$CSV" | cut -d';' -f1,2,3,5,6,7
```

Significado dos status:

| Status           | O que é                                             | Ação                          |
|------------------|-----------------------------------------------------|-------------------------------|
| `OK`             | Consultou e trouxe os dados                         | —                             |
| `CNPJ_INVALIDO`  | Documento não é CNPJ válido (zerado, CPF, DV errado)| Corrigir cadastro no Sankhya  |
| `NAO_ENCONTRADO` | CNPJ válido, mas não existe na Receita               | Verificar cadastro            |
| `ERRO`           | Falha de API (rede, rate limit, 5xx)                | Transitório — retomar recupera|

---

## Situações comuns

### Caiu no meio / quero retomar manualmente
Pula os que já deram `OK` e continua de onde parou (não use `--nova`):
```bash
docker compose run --rm enriquecimento rodar
```

### Reprocessar os que deram ERRO/NAO_ENCONTRADO
Retomar já reconsulta tudo que não é `OK`. Basta rodar o comando de retomada
acima mais uma vez.

### Só re-exportar o CSV (sem consultar de novo)
```bash
docker compose run --rm enriquecimento exportar                 # execução mais recente
docker compose run --rm enriquecimento exportar --execucao 2    # execução específica
```

### Parar tudo
```bash
docker ps --filter name=enriquecimento     # pega o NAME do container
docker stop <name>                          # para a consulta atual
pkill -f 'enriquecer.py'                     # encerra o loop de retomada em background
```

### Rate limit alto (muito "429" no run.log)
Aumente a pausa entre chamadas no `.env` e retome:
```bash
# no .env: CNPJWS_DELAY=0.5
docker compose run --rm enriquecimento rodar
```

---

## Referência de comandos da CLI

| Comando                                               | O que faz                                  |
|-------------------------------------------------------|--------------------------------------------|
| `rodar --nova`                                        | Nova execução, consulta todos os parceiros |
| `rodar`                                               | Retoma a execução aberta (pula os `OK`)    |
| `rodar --limite 20 --nova`                            | Teste rápido com 20 parceiros              |
| `rodar --rotulo "junho"`                              | Nova execução com um rótulo                |
| `execucoes`                                           | Lista as execuções (id, totais, status)    |
| `exportar`                                            | Exporta a execução mais recente para CSV   |
| `exportar --execucao 3 --saida saida.csv`             | Exporta uma execução para um caminho        |

Prefixe cada um com `docker compose run --rm enriquecimento`.
Ex.: `docker compose run --rm enriquecimento execucoes`.
