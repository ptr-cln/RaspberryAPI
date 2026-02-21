from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse

LIKES_COUNT_PATH = Path("/home/pi/HevyBot/runtime/likes_count.txt")
HEVYBOT_OUT_PATH = Path("/home/pi/HevyBot/runtime/hevybot.out")

app = FastAPI(
    title="HevyBot Runtime API",
    description="API REST per leggere file runtime di HevyBot.",
    version="1.0.0",
)


def _read_runtime_file(path: Path) -> str:
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File non trovato: {path}",
        )

    if not path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Il path non punta a un file: {path}",
        )

    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Permessi insufficienti per leggere: {path}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Errore nella lettura del file: {path}",
        ) from exc


@app.get(
    "/runtime/likes-count",
    response_class=PlainTextResponse,
    tags=["runtime"],
    summary="Legge likes_count.txt",
)
def get_likes_count() -> str:
    return _read_runtime_file(LIKES_COUNT_PATH)


@app.get(
    "/runtime/hevybot-out",
    response_class=PlainTextResponse,
    tags=["runtime"],
    summary="Legge hevybot.out",
)
def get_hevybot_out() -> str:
    return _read_runtime_file(HEVYBOT_OUT_PATH)
