"""macOS 호스트 · 모델 · 칩 감지 (캐싱).

첫 호출 시 sysctl/system_profiler 를 실행해 프로세스 수명 동안 캐싱한다.
캐시는 프로세스-로컬 — 재시작 전까지 유지.
"""
from __future__ import annotations

import os
import platform
import socket
import subprocess
from pathlib import Path
from typing import Optional

_DEVICE_INFO_CACHE: Optional[dict] = None


def _device_label_from_model(model_name: str, hostname: str) -> str:
    """모델명·호스트명에서 한국어 라벨 추론 — UI 표시용."""
    mn = (model_name or "").lower()
    if "macbook" in mn: return "맥북"
    if "mac mini" in mn: return "맥미니"
    if "imac" in mn: return "아이맥"
    if "mac pro" in mn: return "맥 프로"
    if "mac studio" in mn: return "맥 스튜디오"
    h = (hostname or "").lower()
    if "macbook" in h or "mbp" in h: return "맥북"
    if "macmini" in h or "mac-mini" in h or "mini" in h: return "맥미니"
    return hostname or "Mac"


def _detect_device_info() -> dict:
    """현재 호스트 정보 반환. 최초 1회만 실제 감지, 이후 캐시."""
    global _DEVICE_INFO_CACHE
    if _DEVICE_INFO_CACHE is not None:
        return _DEVICE_INFO_CACHE
    hostname = socket.gethostname()
    model_id = model_name = chip = ""
    try:
        username = os.getlogin()
    except Exception:
        username = Path.home().name
    try:
        model_id = subprocess.check_output(
            ["sysctl", "-n", "hw.model"], text=True, timeout=5
        ).strip()
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["system_profiler", "SPHardwareDataType"], text=True, timeout=10
        )
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("Model Name:"):
                model_name = s.split(":", 1)[1].strip()
            elif s.startswith("Chip:"):
                chip = s.split(":", 1)[1].strip()
    except Exception:
        pass
    label = _device_label_from_model(model_name, hostname)
    _DEVICE_INFO_CACHE = {
        "hostname": hostname, "modelId": model_id, "modelName": model_name,
        "chip": chip, "username": username, "label": label,
        "platform": platform.system(), "arch": platform.machine(),
    }
    return _DEVICE_INFO_CACHE
