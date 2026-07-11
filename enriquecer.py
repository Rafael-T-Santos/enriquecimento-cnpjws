"""
Enriquecimento de parceiros do Sankhya com dados da API cnpj.ws.

Uso:
    python enriquecer.py rodar                 # retoma execução aberta ou cria uma nova
    python enriquecer.py rodar --nova          # força nova execução (reconsulta todos)
    python enriquecer.py rodar --limite 20     # processa só os 20 primeiros (teste)
    python enriquecer.py execucoes             # lista as execuções já feitas
    python enriquecer.py exportar              # exporta a última execução para CSV
    python enriquecer.py exportar --execucao 3 --saida saida.csv
"""
import argparse
import csv
import json
import os
import sys

import config
from cnpjws import CnpjWsClient, limpar_cnpj, extrair_campos
from storage import Storage, COLUNAS_RESULTADO


def cmd_rodar(args):
    config.validar()
    import db  # importado aqui para não exigir cx_Oracle nos comandos offline
    store = Storage(config.DB_SQLITE)
    try:
        parceiros = db.buscar_parceiros()
        if args.limite:
            parceiros = parceiros[: args.limite]
            print(f"Limite de teste aplicado: {len(parceiros)} parceiros.")

        # Decide a execução: nova, ou retoma a última em aberto.
        if args.nova:
            execucao_id = store.criar_execucao(args.rotulo, len(parceiros))
            print(f">>> Nova execução criada: #{execucao_id}")
        else:
            aberta = store.execucao_aberta()
            if aberta:
                execucao_id = aberta["id"]
                print(f">>> Retomando execução aberta #{execucao_id} "
                      f"(iniciada em {aberta['iniciado_em']}).")
            else:
                execucao_id = store.criar_execucao(args.rotulo, len(parceiros))
                print(f">>> Nenhuma execução aberta. Nova execução criada: #{execucao_id}")

        ja_ok = store.codparcs_ja_ok(execucao_id)
        if ja_ok:
            print(f"    {len(ja_ok)} parceiros já consultados com sucesso serão pulados.")

        cliente = CnpjWsClient(config.CNPJWS_TOKEN, delay=config.CNPJWS_DELAY)

        total = len(parceiros)
        for i, parc in enumerate(parceiros, start=1):
            codparc = parc["codparc"]
            if codparc in ja_ok:
                continue

            prefixo = f"[{i}/{total}] Parc {codparc} - {(parc.get('nomeparc') or '')[:40]}"
            cnpj = limpar_cnpj(parc.get("cgc_cpf"))

            if not cnpj:
                store.salvar_consulta(execucao_id, parc, None, "CNPJ_INVALIDO",
                                      erro="Documento não é um CNPJ válido (14 dígitos + DV)")
                print(f"{prefixo}: CNPJ inválido ({parc.get('cgc_cpf')})")
                continue

            http_status, dados, erro = cliente.consultar(cnpj)

            if dados:
                campos = extrair_campos(dados)
                store.salvar_consulta(
                    execucao_id, parc, cnpj, "OK",
                    http_status=http_status, campos=campos,
                    json_completo=json.dumps(dados, ensure_ascii=False),
                )
                print(f"{prefixo}: OK - {campos.get('razao_social') or ''}")
            else:
                status = "NAO_ENCONTRADO" if http_status == 404 else "ERRO"
                store.salvar_consulta(execucao_id, parc, cnpj, status,
                                      http_status=http_status, erro=erro)
                print(f"{prefixo}: {status} - {erro}")

            # Pausa entre chamadas para respeitar o rate limit da API.
            _sleep(config.CNPJWS_DELAY)

        store.atualizar_totais(execucao_id)
        store.finalizar_execucao(execucao_id)
        exec_final = store.obter_execucao(execucao_id)
        print("\n===== Execução concluída =====")
        _imprimir_execucao(exec_final)
    finally:
        store.close()


def cmd_execucoes(args):
    store = Storage(config.DB_SQLITE)
    try:
        execs = store.listar_execucoes()
        if not execs:
            print("Nenhuma execução registrada ainda.")
            return
        for e in execs:
            _imprimir_execucao(e)
    finally:
        store.close()


def cmd_exportar(args):
    store = Storage(config.DB_SQLITE)
    try:
        if args.execucao:
            execucao_id = args.execucao
        else:
            execs = store.listar_execucoes()
            if not execs:
                print("Nenhuma execução para exportar.")
                return
            execucao_id = execs[0]["id"]

        exec_row = store.obter_execucao(execucao_id)
        if not exec_row:
            print(f"Execução #{execucao_id} não encontrada.")
            return

        linhas = store.consultas_da_execucao(execucao_id)
        if not linhas:
            print(f"Execução #{execucao_id} não tem consultas.")
            return

        saida = args.saida or f"exports/execucao_{execucao_id}.csv"
        os.makedirs(os.path.dirname(saida) or ".", exist_ok=True)

        # Exporta as colunas úteis (sem o json_completo bruto).
        colunas = ["codparc", "nomeparc", "cgc_cpf", "cnpj", "status", "http_status",
                   "erro", *COLUNAS_RESULTADO, "consultado_em"]

        with open(saida, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=";")
            writer.writerow(colunas)
            for l in linhas:
                writer.writerow([l[c] for c in colunas])

        print(f"Exportado {len(linhas)} registros da execução #{execucao_id} para: {saida}")
    finally:
        store.close()


def _imprimir_execucao(e):
    status = "ABERTA" if e["finalizado_em"] is None else "finalizada"
    rotulo = f" [{e['rotulo']}]" if e["rotulo"] else ""
    print(f"#{e['id']}{rotulo} ({status}) | início {e['iniciado_em']} | "
          f"parceiros {e['total_parceiros']} | ok {e['total_ok']} | "
          f"erro {e['total_erro']} | inválido {e['total_invalido']}")


def _sleep(segundos):
    if segundos > 0:
        import time
        time.sleep(segundos)


def main():
    parser = argparse.ArgumentParser(description="Enriquecimento de parceiros via cnpj.ws")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_rodar = sub.add_parser("rodar", help="Processa os parceiros na API")
    p_rodar.add_argument("--nova", action="store_true",
                         help="Força uma nova execução (reconsulta todos os parceiros)")
    p_rodar.add_argument("--limite", type=int, default=None,
                         help="Processa apenas os N primeiros parceiros (teste)")
    p_rodar.add_argument("--rotulo", type=str, default=None,
                         help="Rótulo opcional para identificar a execução")
    p_rodar.set_defaults(func=cmd_rodar)

    p_exec = sub.add_parser("execucoes", help="Lista as execuções")
    p_exec.set_defaults(func=cmd_execucoes)

    p_exp = sub.add_parser("exportar", help="Exporta uma execução para CSV")
    p_exp.add_argument("--execucao", type=int, default=None,
                       help="ID da execução (padrão: a mais recente)")
    p_exp.add_argument("--saida", type=str, default=None,
                       help="Caminho do CSV de saída")
    p_exp.set_defaults(func=cmd_exportar)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário. A execução fica ABERTA e pode ser retomada "
              "com 'python enriquecer.py rodar'.")
        sys.exit(130)
