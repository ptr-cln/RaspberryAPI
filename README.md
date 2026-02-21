# RaspberryAPI

RaspberryAPI e' una piattaforma REST generica in Python (FastAPI) da esporre su Raspberry Pi, con documentazione Swagger UI.
L'obiettivo e' avere un singolo servizio API modulare: HevyBot e' solo un modulo, non il focus esclusivo del progetto.

## Moduli API attuali

### HevyBot (modulo specifico)

- `GET /runtime/likes-count` -> contenuto di `/home/pi/HevyBot/runtime/likes_count.txt`
- `GET /runtime/hevybot-out` -> contenuto di `/home/pi/HevyBot/runtime/hevybot.out`
- `POST /hevybot/stop` -> esegue `stop_hevybot.sh` e restituisce output console
- `POST /hevybot/start` -> esegue `start_hevybot.sh` con argomenti dal body e restituisce output console

### System (modulo generico)

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

## Come estendere con nuovi moduli

- Aggiungi nuovi endpoint senza legarli a HevyBot.
- Raggruppa gli endpoint con un tag OpenAPI dedicato (es. `Camera`, `GPIO`, `Network`, `Storage`).
- Usa path coerenti per modulo (es. `/camera/...`, `/gpio/...`, `/network/...`).
- Mantieni documentazione Swagger aggiornata con summary e descrizioni chiare.

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
curl -X POST http://127.0.0.1:8000/hevybot/stop
curl -X POST http://127.0.0.1:8000/hevybot/start \
  -H "Content-Type: application/json" \
  -d '{"fast-mode":true,"execution-time-minutes":180,"pause-time-minutes":60,"min-delay":1,"max-delay":3,"max-likes":20000,"long-pause-every-min-likes":8,"long-pause-every-max-likes":14,"long-pause-min-seconds":30,"long-pause-max-seconds":90}'
```

### Nota su start/stop HevyBot

- Gli endpoint sono `POST` perche' eseguono azioni con side-effect (avvio/arresto processo).
- `POST /hevybot/start` accetta un body JSON key/value e lo converte in argomenti CLI.
- Esempio completo: `{"fast-mode":true,"execution-time-minutes":180,"pause-time-minutes":60,"min-delay":1,"max-delay":3,"max-likes":20000,"long-pause-every-min-likes":8,"long-pause-every-max-likes":14,"long-pause-min-seconds":30,"long-pause-max-seconds":90}`.
- In Swagger (`/docs`) trovi template tipizzato con campi noti: `fast-mode`, `execution-time-minutes`, `pause-time-minutes`, `min-delay`, `max-delay`, `max-likes`, `long-pause-every-min-likes`, `long-pause-every-max-likes`, `long-pause-min-seconds`, `long-pause-max-seconds`, `args`.
- Supportato anche il formato legacy `{"args":["--flag","value"]}`.
- Risposta per entrambi: `exit_code`, `success`, `stdout`, `stderr`, `combined_output`, `command`.
- Se uno script resta bloccato, l'API interrompe l'attesa dopo `SCRIPT_TIMEOUT_SECONDS` (default `25`) e ritorna `timed_out: true` con output parziale.
- La risposta include `debug` con probe shell (`shell_probe_*`), utente effettivo (`effective_uid/gid`), path script e PATH ambiente per troubleshooting.
