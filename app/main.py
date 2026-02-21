from datetime import datetime, timezone
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
from typing import List, Optional, Tuple

import psutil
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

LIKES_COUNT_PATH = Path("/home/pi/HevyBot/runtime/likes_count.txt")
HEVYBOT_OUT_PATH = Path("/home/pi/HevyBot/runtime/hevybot.out")

app = FastAPI(
    title="RaspberryPi API",
    description=(
        "API REST esposte dal Raspberry Pi. "
        "Alcuni endpoint sono specifici di servizi locali, come HevyBot."
    ),
    version="1.0.0",
    openapi_tags=[
        {
            "name": "HevyBot",
            "description": "Endpoint specifici di HevyBot.",
        },
        {
            "name": "System",
            "description": "Endpoint generici con metriche e stato Raspberry.",
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


@app.get(
    "/runtime/likes-count",
    response_class=PlainTextResponse,
    tags=["HevyBot"],
    summary="Legge likes_count.txt",
)
def get_likes_count() -> str:
    return _read_runtime_file(LIKES_COUNT_PATH)


@app.get(
    "/runtime/hevybot-out",
    response_class=PlainTextResponse,
    tags=["HevyBot"],
    summary="Legge hevybot.out",
)
def get_hevybot_out() -> str:
    return _read_runtime_file(HEVYBOT_OUT_PATH)


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
