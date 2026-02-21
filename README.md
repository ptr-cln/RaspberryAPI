# RaspberryAPI

API REST in Python (FastAPI) da esporre su Raspberry Pi, con documentazione Swagger UI.
Il progetto e' generico: puo' contenere endpoint di servizi diversi.

## Endpoint disponibili (modulo HevyBot)

- `GET /runtime/likes-count` -> contenuto di `/home/pi/HevyBot/runtime/likes_count.txt`
- `GET /runtime/hevybot-out` -> contenuto di `/home/pi/HevyBot/runtime/hevybot.out`

## Endpoint disponibili (modulo System)

- `GET /system/metrics` -> metriche live Raspberry Pi:
  - percentuale CPU utilizzata
  - percentuale RAM utilizzata
  - percentuale disco utilizzata, spazio libero e totale
  - temperatura CPU (quando disponibile)
  - uptime, load average, frequenza CPU, indirizzi IPv4

Swagger UI:

- `http://<IP_RASPBERRY>:8000/docs`

OpenAPI JSON:

- `http://<IP_RASPBERRY>:8000/openapi.json`

## Avvio locale

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Servizio sempre attivo (systemd)

1. Copia il repository in `/home/pi/RaspberryAPI`
2. Crea e popola il virtualenv come nella sezione precedente
3. Installa il servizio:

```bash
sudo cp deploy/raspberryapi.service /etc/systemd/system/raspberryapi.service
sudo systemctl daemon-reload
sudo systemctl enable raspberryapi.service
sudo systemctl start raspberryapi.service
```

Comandi utili:

```bash
sudo systemctl status raspberryapi.service
sudo journalctl -u raspberryapi.service -f
```

## Test rapido

```bash
curl http://127.0.0.1:8000/runtime/likes-count
curl http://127.0.0.1:8000/runtime/hevybot-out
curl http://127.0.0.1:8000/system/metrics
```
