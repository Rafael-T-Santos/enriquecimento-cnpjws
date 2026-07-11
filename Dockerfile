# Mesma base e Oracle Instant Client da internal-api-sankhya, para que o
# cx_Oracle consiga conectar no Oracle do Sankhya a partir do container.
FROM python:3.9-slim-bullseye

# --- Oracle Instant Client (necessário para o cx_Oracle) ---
WORKDIR /opt/oracle
RUN apt-get update && apt-get install -y libaio1 wget unzip \
    && wget https://download.oracle.com/otn_software/linux/instantclient/1920000/instantclient-basiclite-linux.x64-19.20.0.0.0dbru.zip \
    && unzip instantclient-basiclite-linux.x64-19.20.0.0.0dbru.zip \
    && rm -f instantclient-basiclite-linux.x64-19.20.0.0.0dbru.zip \
    && cd /opt/oracle/instantclient_19_20 \
    && echo /opt/oracle/instantclient_19_20 > /etc/ld.so.conf.d/oracle-instantclient.conf \
    && ldconfig \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Aplicação ---
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# enriquecer.py é uma CLI com subcomandos (rodar / execucoes / exportar).
# Os argumentos passados no `docker compose run` viram os argumentos da CLI.
ENTRYPOINT ["python", "enriquecer.py"]
