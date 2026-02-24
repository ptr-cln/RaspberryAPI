from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import re
import shlex
import socket
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import psutil
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

LIKES_COUNT_PATH = Path("/home/pi/HevyBot/runtime/likes_count.txt")
LIKED_POSTS_PATH = Path("/home/pi/HevyBot/runtime/liked_posts.txt")
INACTIVE_USERS_CACHE_PATH = Path("/home/pi/HevyBot/runtime/inactive_users_cache.json")
HEVYBOT_PID_PATH = Path("/home/pi/HevyBot/runtime/hevybot.pid")
HEVYBOT_OUT_PATH = Path("/home/pi/HevyBot/runtime/hevybot.out")
START_HEVYBOT_SCRIPT_PATH = Path(
    os.getenv("HEVYBOT_START_SCRIPT_PATH", "/home/pi/HevyBot/start_hevybot.sh")
)
STOP_HEVYBOT_SCRIPT_PATH = Path(
    os.getenv("HEVYBOT_STOP_SCRIPT_PATH", "/home/pi/HevyBot/stop_hevybot.sh")
)
SCRIPT_RUNNER_PATH = os.getenv("SCRIPT_RUNNER_PATH", "/bin/bash")
SCRIPT_TIMEOUT_SECONDS = float(os.getenv("SCRIPT_TIMEOUT_SECONDS", "25"))

app = FastAPI(
    title="RaspberryPi API",
    description=(
        "Piattaforma API REST generica per Raspberry Pi, organizzata per moduli. "
        "HevyBot e' solo uno dei moduli applicativi disponibili."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "HevyBot",
            "description": "Modulo applicativo HevyBot (specifico, non obbligatorio).",
        },
        {
            "name": "System",
            "description": "Endpoint generici con metriche e stato del Raspberry.",
        }
    ],
)


class CpuMetrics(BaseModel):
    usage_percent: float = Field(..., description="Percentuale utilizzo CPU.")
    logical_cores: int = Field(..., description="Numero core logici.")
    physical_cores: Optional[int] = Field(default=None, description="Numero core fisici.")
    load_average_1m: Optional[float] = Field(default=None, description="Load average 1 minuto.")
    load_average_5m: Optional[float] = Field(default=None, description="Load average 5 minuti.")
    load_average_15m: Optional[float] = Field(default=None, description="Load average 15 minuti.")
    current_frequency_mhz: Optional[float] = Field(
        default=None,
        description="Frequenza CPU corrente in MHz.",
    )


class RamMetrics(BaseModel):
    usage_percent: float = Field(..., description="Percentuale RAM utilizzata.")
    used_bytes: int = Field(..., description="RAM usata in byte.")
    available_bytes: int = Field(..., description="RAM disponibile in byte.")
    total_bytes: int = Field(..., description="RAM totale in byte.")


class DiskMetrics(BaseModel):
    usage_percent: float = Field(..., description="Percentuale disco utilizzata.")
    used_bytes: int = Field(..., description="Spazio disco usato in byte.")
    free_bytes: int = Field(..., description="Spazio disco libero in byte.")
    total_bytes: int = Field(..., description="Spazio disco totale in byte.")
    free_gb: float = Field(..., description="Spazio disco libero in GB.")


class TemperatureMetrics(BaseModel):
    cpu_celsius: Optional[float] = Field(
        default=None,
        description="Temperatura CPU in gradi Celsius.",
    )
    source: Optional[str] = Field(
        default=None,
        description="Sorgente usata per leggere la temperatura.",
    )


class NetworkMetrics(BaseModel):
    ipv4_addresses: List[str] = Field(
        default_factory=list,
        description="Indirizzi IPv4 non-loopback del Raspberry.",
    )


class SystemMetricsResponse(BaseModel):
    timestamp_utc: datetime = Field(..., description="Timestamp UTC della rilevazione.")
    hostname: str = Field(..., description="Hostname macchina.")
    os: str = Field(..., description="Sistema operativo.")
    kernel: str = Field(..., description="Versione kernel.")
    uptime_seconds: int = Field(..., description="Uptime sistema in secondi.")
    boot_time_utc: datetime = Field(..., description="Istante di boot in UTC.")
    cpu: CpuMetrics
    ram: RamMetrics
    disk: DiskMetrics
    temperature: TemperatureMetrics
    network: NetworkMetrics


class StartHevyBotRequest(BaseModel):
    fast_mode: Optional[bool] = Field(
        default=None,
        alias="fast-mode",
        description="Se true aggiunge il flag --fast-mode.",
    )
    execution_time_minutes: Optional[int] = Field(
        default=None,
        alias="execution-time-minutes",
        ge=1,
        description="Minuti di esecuzione (es. --execution-time-minutes 180).",
    )
    pause_time_minutes: Optional[int] = Field(
        default=None,
        alias="pause-time-minutes",
        ge=1,
        description="Pausa tra cicli in minuti (es. --pause-time-minutes 60).",
    )
    min_delay: Optional[float] = Field(
        default=None,
        alias="min-delay",
        ge=0,
        description="Delay minimo (es. --min-delay 1).",
    )
    max_delay: Optional[float] = Field(
        default=None,
        alias="max-delay",
        ge=0,
        description="Delay massimo (es. --max-delay 3).",
    )
    max_likes: Optional[int] = Field(
        default=None,
        alias="max-likes",
        ge=1,
        description="Numero massimo like (es. --max-likes 20000).",
    )
    graph_root_username: Optional[str] = Field(
        default="",
        alias="graph-root-username",
        description="Username root per il graph (es. --graph-root-username user).",
    )
    long_pause_every_min_likes: Optional[int] = Field(
        default=None,
        alias="long-pause-every-min-likes",
        ge=1,
        description="Soglia minima like prima di long pause.",
    )
    long_pause_every_max_likes: Optional[int] = Field(
        default=None,
        alias="long-pause-every-max-likes",
        ge=1,
        description="Soglia massima like prima di long pause.",
    )
    long_pause_min_seconds: Optional[int] = Field(
        default=None,
        alias="long-pause-min-seconds",
        ge=1,
        description="Durata minima long pause in secondi.",
    )
    long_pause_max_seconds: Optional[int] = Field(
        default=None,
        alias="long-pause-max-seconds",
        ge=1,
        description="Durata massima long pause in secondi.",
    )
    args: List[str] = Field(
        default_factory=list,
        description="Argomenti raw aggiuntivi inseriti in coda.",
    )

    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",
        json_schema_extra={
            "example": {
                "fast-mode": True,
                "execution-time-minutes": 180,
                "pause-time-minutes": 60,
                "min-delay": 1,
                "max-delay": 3,
                "max-likes": 20000,
                "graph-root-username": "",
                "long-pause-every-min-likes": 8,
                "long-pause-every-max-likes": 14,
                "long-pause-min-seconds": 30,
                "long-pause-max-seconds": 90,
            }
        },
    )


class ScriptExecutionResponse(BaseModel):
    command: List[str] = Field(..., description="Comando eseguito.")
    exit_code: int = Field(..., description="Codice di uscita del processo.")
    success: bool = Field(..., description="True se exit code e' 0.")
    timed_out: bool = Field(
        default=False,
        description="True se il processo e' stato interrotto per timeout.",
    )
    stdout: str = Field(..., description="Output standard del comando.")
    stderr: str = Field(..., description="Output di errore del comando.")
    combined_output: str = Field(
        ...,
        description="Output complessivo (stdout + stderr).",
    )
    debug: Dict[str, Any] = Field(
        default_factory=dict,
        description="Informazioni diagnostiche sull'ambiente di esecuzione.",
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


def _safe_get_load_average() -> Tuple[Optional[float], Optional[float], Optional[float]]:
    try:
        return os.getloadavg()
    except (AttributeError, OSError):
        return None, None, None


def _get_ipv4_addresses() -> List[str]:
    addresses: List[str] = []
    for interface_addresses in psutil.net_if_addrs().values():
        for address in interface_addresses:
            if address.family == socket.AF_INET and address.address != "127.0.0.1":
                addresses.append(address.address)

    if addresses:
        return sorted(set(addresses))

    # Fallback for edge cases where interface enumeration returns no IPv4.
    try:
        host_ip = socket.gethostbyname(socket.gethostname())
        if host_ip != "127.0.0.1":
            return [host_ip]
    except OSError:
        pass

    return []


def _get_cpu_temperature_celsius() -> Tuple[Optional[float], Optional[str]]:
    sysfs_temp_path = Path("/sys/class/thermal/thermal_zone0/temp")
    if sysfs_temp_path.exists():
        try:
            raw_value = sysfs_temp_path.read_text(encoding="utf-8").strip()
            return round(float(raw_value) / 1000.0, 2), "sysfs"
        except (OSError, ValueError):
            pass

    try:
        temperatures = psutil.sensors_temperatures(fahrenheit=False)
        if temperatures:
            preferred_sources = ("cpu_thermal", "soc_thermal", "coretemp")
            for source_name in preferred_sources:
                source_entries = temperatures.get(source_name)
                if source_entries:
                    for entry in source_entries:
                        if entry.current is not None:
                            return round(float(entry.current), 2), f"psutil:{source_name}"

            for source_name, source_entries in temperatures.items():
                for entry in source_entries:
                    if entry.current is not None:
                        return round(float(entry.current), 2), f"psutil:{source_name}"
    except (AttributeError, OSError, NotImplementedError):
        pass

    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True,
            text=True,
            check=False,
            timeout=1.0,
        )
        if result.returncode == 0:
            match = re.search(r"temp=([0-9]+(?:\.[0-9]+)?)", result.stdout)
            if match:
                return round(float(match.group(1)), 2), "vcgencmd"
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass

    return None, None


def _run_script(script_path: Path, args: Optional[List[str]] = None) -> ScriptExecutionResponse:
    if not script_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Script non trovato: {script_path}",
        )

    if not script_path.is_file():
        raise HTTPException(
            status_code=400,
            detail=f"Il path non punta a uno script file: {script_path}",
        )

    try:
        shell_probe = subprocess.run(
            [SCRIPT_RUNNER_PATH, "-lc", "echo __SHELL_OK__"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=500,
            detail=f"Impossibile eseguire shell probe con {SCRIPT_RUNNER_PATH}: {exc}",
        ) from exc

    script_and_args = [str(script_path), *(args or [])]
    shell_command = " ".join(shlex.quote(part) for part in script_and_args)
    shell_command = f"cd {shlex.quote(str(script_path.parent))} && {shell_command}"
    command = [SCRIPT_RUNNER_PATH, "-lc", shell_command]
    debug_info: Dict[str, Any] = {
        "runner": SCRIPT_RUNNER_PATH,
        "shell_probe_exit_code": shell_probe.returncode,
        "shell_probe_stdout": (shell_probe.stdout or "").strip(),
        "shell_probe_stderr": (shell_probe.stderr or "").strip(),
        "script_path": str(script_path),
        "script_exists": script_path.exists(),
        "script_is_file": script_path.is_file(),
        "script_is_executable": os.access(script_path, os.X_OK),
        "working_dir": str(script_path.parent),
        "api_process_cwd": os.getcwd(),
        "effective_uid": os.geteuid() if hasattr(os, "geteuid") else None,
        "effective_gid": os.getegid() if hasattr(os, "getegid") else None,
        "path_env": os.getenv("PATH", ""),
    }

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=SCRIPT_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Shell runner non trovato: {SCRIPT_RUNNER_PATH}",
        ) from exc
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        timeout_message = (
            f"Processo terminato per timeout dopo {SCRIPT_TIMEOUT_SECONDS} secondi."
        )
        stderr = f"{stderr}\n{timeout_message}".strip()
        return ScriptExecutionResponse(
            command=command,
            exit_code=-1,
            success=False,
            timed_out=True,
            stdout=stdout,
            stderr=stderr,
            combined_output=f"{stdout}{stderr}",
            debug=debug_info,
        )
    except PermissionError as exc:
        raise HTTPException(
            status_code=403,
            detail=f"Permessi insufficienti per eseguire lo script: {script_path}",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Errore durante l'esecuzione dello script: {script_path}",
        ) from exc

    stdout = result.stdout or ""
    stderr = result.stderr or ""

    return ScriptExecutionResponse(
        command=command,
        exit_code=result.returncode,
        success=result.returncode == 0,
        timed_out=False,
        stdout=stdout,
        stderr=stderr,
        combined_output=f"{stdout}{stderr}",
        debug=debug_info,
    )


def _build_script_args_from_payload(payload: Optional[Dict[str, Any]]) -> List[str]:
    if not payload:
        return []

    args: List[str] = []

    # Backward compatibility with previous format: {"args": ["--flag", "value"]}.
    legacy_args = payload.get("args")
    if isinstance(legacy_args, list):
        args.extend(str(item) for item in legacy_args)

    for key, value in payload.items():
        if key == "args":
            continue

        flag_name = key.strip()
        if not flag_name:
            continue
        if not flag_name.startswith("--"):
            flag_name = f"--{flag_name.lstrip('-')}"

        if value is None:
            continue

        if isinstance(value, bool):
            if value:
                args.append(flag_name)
            continue

        if isinstance(value, list):
            for item in value:
                if item is None:
                    continue
                args.extend([flag_name, str(item)])
            continue

        args.extend([flag_name, str(value)])

    return args


def _start_request_to_payload_dict(payload: Optional[StartHevyBotRequest]) -> Dict[str, Any]:
    if payload is None:
        return {}

    payload_dict: Dict[str, Any] = payload.model_dump(
        by_alias=True,
        exclude_none=True,
    )

    extra_fields = getattr(payload, "model_extra", None) or {}
    for key, value in extra_fields.items():
        payload_dict[key] = value

    return payload_dict


@app.get(
    "/runtime/likes-count",
    response_class=PlainTextResponse,
    tags=["HevyBot"],
    summary="Legge likes_count.txt",
)
def get_likes_count() -> str:
    return _read_runtime_file(LIKES_COUNT_PATH)


@app.get(
    "/runtime/liked-posts",
    response_class=PlainTextResponse,
    tags=["HevyBot"],
    summary="Legge liked_posts.txt",
)
def get_liked_posts() -> str:
    return _read_runtime_file(LIKED_POSTS_PATH)


@app.get(
    "/runtime/inactive-users-cache",
    response_class=PlainTextResponse,
    tags=["HevyBot"],
    summary="Legge inactive_users_cache.json",
)
def get_inactive_users_cache() -> str:
    return _read_runtime_file(INACTIVE_USERS_CACHE_PATH)


@app.get(
    "/runtime/hevybot-pid",
    response_class=PlainTextResponse,
    tags=["HevyBot"],
    summary="Legge hevybot.pid",
)
def get_hevybot_pid() -> str:
    return _read_runtime_file(HEVYBOT_PID_PATH)


@app.get(
    "/runtime/hevybot-out",
    response_class=PlainTextResponse,
    tags=["HevyBot"],
    summary="Legge hevybot.out",
)
def get_hevybot_out() -> str:
    return _read_runtime_file(HEVYBOT_OUT_PATH)


@app.post(
    "/hevybot/stop",
    response_model=ScriptExecutionResponse,
    tags=["HevyBot"],
    summary="Ferma HevyBot eseguendo stop_hevybot.sh",
)
def stop_hevybot() -> ScriptExecutionResponse:
    return _run_script(STOP_HEVYBOT_SCRIPT_PATH)


@app.post(
    "/hevybot/start",
    response_model=ScriptExecutionResponse,
    tags=["HevyBot"],
    summary="Avvia HevyBot eseguendo start_hevybot.sh",
)
def start_hevybot(
    payload: Optional[StartHevyBotRequest] = Body(
        default=None,
    ),
) -> ScriptExecutionResponse:
    payload_dict = _start_request_to_payload_dict(payload)
    args = _build_script_args_from_payload(payload_dict)
    return _run_script(START_HEVYBOT_SCRIPT_PATH, args)


@app.get(
    "/system/metrics",
    response_model=SystemMetricsResponse,
    tags=["System"],
    summary="Metriche live del Raspberry Pi",
)
def get_system_metrics() -> SystemMetricsResponse:
    boot_time_utc = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    uptime_seconds = int((datetime.now(timezone.utc) - boot_time_utc).total_seconds())
    cpu_frequency = psutil.cpu_freq()
    load_average_1m, load_average_5m, load_average_15m = _safe_get_load_average()
    cpu_temperature_celsius, temp_source = _get_cpu_temperature_celsius()

    ram = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return SystemMetricsResponse(
        timestamp_utc=datetime.now(timezone.utc),
        hostname=socket.gethostname(),
        os=f"{platform.system()} {platform.release()}",
        kernel=platform.version(),
        uptime_seconds=uptime_seconds,
        boot_time_utc=boot_time_utc,
        cpu=CpuMetrics(
            usage_percent=round(psutil.cpu_percent(interval=0.5), 2),
            logical_cores=psutil.cpu_count(logical=True) or 0,
            physical_cores=psutil.cpu_count(logical=False),
            load_average_1m=round(load_average_1m, 2) if load_average_1m is not None else None,
            load_average_5m=round(load_average_5m, 2) if load_average_5m is not None else None,
            load_average_15m=round(load_average_15m, 2)
            if load_average_15m is not None
            else None,
            current_frequency_mhz=round(cpu_frequency.current, 2)
            if cpu_frequency and cpu_frequency.current is not None
            else None,
        ),
        ram=RamMetrics(
            usage_percent=round(ram.percent, 2),
            used_bytes=ram.used,
            available_bytes=ram.available,
            total_bytes=ram.total,
        ),
        disk=DiskMetrics(
            usage_percent=round(disk.percent, 2),
            used_bytes=disk.used,
            free_bytes=disk.free,
            total_bytes=disk.total,
            free_gb=round(disk.free / (1024**3), 2),
        ),
        temperature=TemperatureMetrics(
            cpu_celsius=cpu_temperature_celsius,
            source=temp_source,
        ),
        network=NetworkMetrics(ipv4_addresses=_get_ipv4_addresses()),
    )
