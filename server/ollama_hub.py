"""Ollama 모델 허브 — 검색 · 다운로드 · 삭제 · 상태 조회.

Open WebUI 스타일의 Ollama 모델 관리:
  - 인기 모델 카탈로그 (내장 + ollama.com 조회)
  - ollama pull / rm 래핑 (SSE 진행률 스트림)
  - 설치된 모델 목록 + 상세 정보
  - 모델 실행 테스트
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any, Optional

from .logger import log


# ───────── Ollama 접속 설정 ─────────

def _ollama_host() -> str:
    return (os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")


def _ollama_bin() -> str:
    return shutil.which("ollama") or ""


# ───────── 인기 모델 카탈로그 (내장) ─────────

OLLAMA_MODEL_CATALOG: list[dict] = [
    # ── LLM (대화/생성) ──
    {"name": "llama3.1", "label": "Llama 3.1 (8B)", "size": "4.7GB", "category": "llm",
     "desc": "Meta의 오픈소스 LLM. 범용 대화·코드·추론.", "tags": ["meta", "chat", "code"]},
    {"name": "llama3.1:70b", "label": "Llama 3.1 (70B)", "size": "40GB", "category": "llm",
     "desc": "Llama 3.1 대형 모델. 높은 추론 능력.", "tags": ["meta", "chat", "reasoning"]},
    {"name": "llama3.2", "label": "Llama 3.2 (3B)", "size": "2.0GB", "category": "llm",
     "desc": "경량 Llama. 빠른 응답.", "tags": ["meta", "chat", "lightweight"]},
    {"name": "gemma2", "label": "Gemma 2 (9B)", "size": "5.4GB", "category": "llm",
     "desc": "Google DeepMind 오픈 모델.", "tags": ["google", "chat"]},
    {"name": "gemma2:2b", "label": "Gemma 2 (2B)", "size": "1.6GB", "category": "llm",
     "desc": "Gemma 2 경량 버전.", "tags": ["google", "chat", "lightweight"]},
    {"name": "mistral", "label": "Mistral 7B", "size": "4.1GB", "category": "llm",
     "desc": "Mistral AI 범용 모델. 빠르고 정확.", "tags": ["mistral", "chat"]},
    {"name": "mixtral", "label": "Mixtral 8x7B", "size": "26GB", "category": "llm",
     "desc": "Mistral MoE. 전문가 혼합.", "tags": ["mistral", "chat", "moe"]},
    {"name": "qwen2.5", "label": "Qwen 2.5 (7B)", "size": "4.7GB", "category": "llm",
     "desc": "Alibaba Qwen. 다국어 강점.", "tags": ["alibaba", "chat", "multilingual"]},
    {"name": "qwen2.5:72b", "label": "Qwen 2.5 (72B)", "size": "41GB", "category": "llm",
     "desc": "Qwen 2.5 대형. 코드+추론.", "tags": ["alibaba", "chat", "code"]},
    {"name": "phi3", "label": "Phi-3 Mini (3.8B)", "size": "2.3GB", "category": "llm",
     "desc": "Microsoft 소형 모델. 효율적.", "tags": ["microsoft", "chat", "lightweight"]},
    {"name": "deepseek-r1", "label": "DeepSeek R1", "size": "4.7GB", "category": "llm",
     "desc": "DeepSeek 추론 특화 모델.", "tags": ["deepseek", "reasoning"]},
    {"name": "command-r", "label": "Command R (35B)", "size": "20GB", "category": "llm",
     "desc": "Cohere RAG 특화 모델.", "tags": ["cohere", "rag", "chat"]},
    # ── 코드 ──
    {"name": "codellama", "label": "Code Llama (7B)", "size": "3.8GB", "category": "code",
     "desc": "Meta 코드 생성 특화.", "tags": ["meta", "code"]},
    {"name": "deepseek-coder-v2", "label": "DeepSeek Coder V2", "size": "8.9GB", "category": "code",
     "desc": "DeepSeek 코드 생성.", "tags": ["deepseek", "code"]},
    {"name": "starcoder2", "label": "StarCoder2 (7B)", "size": "4.0GB", "category": "code",
     "desc": "BigCode 코드 생성.", "tags": ["bigcode", "code"]},
    {"name": "qwen2.5-coder", "label": "Qwen 2.5 Coder (7B)", "size": "4.7GB", "category": "code",
     "desc": "Qwen 코드 특화.", "tags": ["alibaba", "code"]},
    # ── 임베딩 ──
    {"name": "bge-m3", "label": "BGE-M3", "size": "1.2GB", "category": "embedding",
     "desc": "BAAI 다국어 임베딩. 1024 dims. 한국어 우수.", "tags": ["baai", "embedding", "multilingual"]},
    {"name": "nomic-embed-text", "label": "Nomic Embed Text", "size": "274MB", "category": "embedding",
     "desc": "Nomic 텍스트 임베딩. 768 dims.", "tags": ["nomic", "embedding"]},
    {"name": "mxbai-embed-large", "label": "MXBai Embed Large", "size": "669MB", "category": "embedding",
     "desc": "MixedBread 임베딩. 1024 dims.", "tags": ["mixedbread", "embedding"]},
    {"name": "snowflake-arctic-embed", "label": "Snowflake Arctic Embed", "size": "669MB", "category": "embedding",
     "desc": "Snowflake 임베딩. 1024 dims.", "tags": ["snowflake", "embedding"]},
    {"name": "all-minilm", "label": "All-MiniLM-L6", "size": "45MB", "category": "embedding",
     "desc": "초경량 임베딩. 384 dims. 빠른 프로토타이핑.", "tags": ["sentence-transformers", "embedding", "lightweight"]},
    # ── 비전 ──
    {"name": "llava", "label": "LLaVA (7B)", "size": "4.7GB", "category": "vision",
     "desc": "이미지+텍스트 멀티모달.", "tags": ["vision", "multimodal"]},
    {"name": "llava-phi3", "label": "LLaVA Phi-3 Mini", "size": "2.9GB", "category": "vision",
     "desc": "경량 멀티모달.", "tags": ["vision", "multimodal", "lightweight"]},
]


# ───────── 설치된 모델 조회 ─────────

def api_ollama_models() -> dict:
    """설치된 Ollama 모델 목록 + 카탈로그 매칭."""
    host = _ollama_host()
    installed: list[dict] = []
    try:
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            name = m.get("name", "")
            size = m.get("size", 0)
            details = m.get("details") or {}
            # 카탈로그 매칭
            cat_entry = next((c for c in OLLAMA_MODEL_CATALOG if c["name"] == name or name.startswith(c["name"] + ":")), None)
            installed.append({
                "name": name,
                "size": size,
                "sizeHuman": _fmt_size(size),
                "family": details.get("family", ""),
                "parameterSize": details.get("parameter_size", ""),
                "quantization": details.get("quantization_level", ""),
                "modifiedAt": m.get("modified_at", ""),
                "digest": (m.get("digest") or "")[:16],
                "category": cat_entry["category"] if cat_entry else _guess_category(name),
                "catalogDesc": cat_entry["desc"] if cat_entry else "",
            })
    except Exception as e:
        return {"ok": False, "error": str(e), "installed": [], "ollamaAvailable": False}

    installed_names = {m["name"] for m in installed}
    return {
        "ok": True,
        "installed": installed,
        "installedCount": len(installed),
        "ollamaAvailable": True,
        "host": host,
    }


def api_ollama_catalog(query: dict) -> dict:
    """모델 카탈로그 — 내장 목록 + 설치 상태."""
    q = ((query.get("q", [""])[0] if isinstance(query.get("q"), list) else query.get("q", "")) or "").strip().lower()
    category = ((query.get("category", [""])[0] if isinstance(query.get("category"), list) else query.get("category", "")) or "").strip().lower()

    # 설치된 모델 이름 set
    installed_names: set[str] = set()
    try:
        host = _ollama_host()
        req = urllib.request.Request(f"{host}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        for m in data.get("models", []):
            installed_names.add(m.get("name", ""))
    except Exception:
        pass

    out = []
    for m in OLLAMA_MODEL_CATALOG:
        if category and m["category"] != category:
            continue
        if q and q not in m["name"].lower() and q not in m.get("desc", "").lower() and q not in " ".join(m.get("tags", [])).lower():
            continue
        out.append({
            **m,
            "installed": m["name"] in installed_names or any(n.startswith(m["name"] + ":") for n in installed_names),
        })

    categories = sorted(set(m["category"] for m in OLLAMA_MODEL_CATALOG))
    return {
        "ok": True,
        "models": out,
        "categories": categories,
        "totalCatalog": len(OLLAMA_MODEL_CATALOG),
        "installedCount": len(installed_names),
    }


def api_ollama_pull(body: dict) -> dict:
    """모델 다운로드 시작 (백그라운드). body: {name}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("name") or "").strip()
    if not name or not re.match(r"^[a-zA-Z0-9._:/-]+$", name):
        return {"ok": False, "error": "invalid model name"}

    # ollama CLI 사용 (API로도 가능하지만 CLI가 진행률 출력이 깔끔)
    b = _ollama_bin()
    if not b:
        # CLI 없으면 API로 pull
        return _pull_via_api(name)

    # 백그라운드에서 pull 시작
    pull_id = f"pull-{int(time.time()*1000)}"
    _PULL_STATUS[pull_id] = {"name": name, "status": "pulling", "progress": 0, "error": ""}

    def _run():
        try:
            proc = subprocess.Popen(
                [b, "pull", name],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            )
            for line in proc.stdout:
                line = line.strip()
                if "pulling" in line.lower() or "%" in line:
                    # 진행률 파싱 시도
                    pct_match = re.search(r"(\d+)%", line)
                    if pct_match:
                        _PULL_STATUS[pull_id]["progress"] = int(pct_match.group(1))
                    _PULL_STATUS[pull_id]["lastLine"] = line
            proc.wait()
            if proc.returncode == 0:
                _PULL_STATUS[pull_id]["status"] = "ok"
                _PULL_STATUS[pull_id]["progress"] = 100
            else:
                _PULL_STATUS[pull_id]["status"] = "err"
                _PULL_STATUS[pull_id]["error"] = f"exit {proc.returncode}"
        except Exception as e:
            _PULL_STATUS[pull_id]["status"] = "err"
            _PULL_STATUS[pull_id]["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "pullId": pull_id, "name": name}


def _pull_via_api(name: str) -> dict:
    """Ollama HTTP API로 모델 pull."""
    host = _ollama_host()
    pull_id = f"pull-{int(time.time()*1000)}"
    _PULL_STATUS[pull_id] = {"name": name, "status": "pulling", "progress": 0, "error": ""}

    def _run():
        try:
            body = json.dumps({"name": name, "stream": False}).encode("utf-8")
            req = urllib.request.Request(
                f"{host}/api/pull", data=body,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=600) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            _PULL_STATUS[pull_id]["status"] = "ok"
            _PULL_STATUS[pull_id]["progress"] = 100
        except Exception as e:
            _PULL_STATUS[pull_id]["status"] = "err"
            _PULL_STATUS[pull_id]["error"] = str(e)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "pullId": pull_id, "name": name}


# 다운로드 진행 상태 저장 (메모리)
_PULL_STATUS: dict[str, dict] = {}


def api_ollama_pull_status(query: dict) -> dict:
    """모델 다운로드 진행 상태. GET /api/ollama/pull-status?pullId=..."""
    pid = (query.get("pullId", [""])[0] if isinstance(query.get("pullId"), list) else query.get("pullId", "")) or ""
    if not pid or pid not in _PULL_STATUS:
        return {"ok": False, "error": "unknown pullId"}
    return {"ok": True, **_PULL_STATUS[pid]}


def api_ollama_delete(body: dict) -> dict:
    """모델 삭제. body: {name}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    name = (body.get("name") or "").strip()
    if not name:
        return {"ok": False, "error": "name required"}

    host = _ollama_host()
    try:
        body_bytes = json.dumps({"name": name}).encode("utf-8")
        req = urllib.request.Request(
            f"{host}/api/delete", data=body_bytes,
            headers={"Content-Type": "application/json"},
            method="DELETE",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            pass
        return {"ok": True, "name": name}
    except urllib.error.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8")[:500]
        except Exception:
            pass
        return {"ok": False, "error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def api_ollama_model_info(query: dict) -> dict:
    """모델 상세 정보. GET /api/ollama/info?name=..."""
    name = ((query.get("name", [""])[0] if isinstance(query.get("name"), list) else query.get("name", "")) or "").strip()
    if not name:
        return {"ok": False, "error": "name required"}

    host = _ollama_host()
    try:
        body = json.dumps({"name": name}).encode("utf-8")
        req = urllib.request.Request(
            f"{host}/api/show", data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return {
            "ok": True, "name": name,
            "modelfile": data.get("modelfile", ""),
            "parameters": data.get("parameters", ""),
            "template": data.get("template", ""),
            "details": data.get("details") or {},
            "modelInfo": data.get("model_info") or {},
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ───────── 헬퍼 ─────────

def _fmt_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _guess_category(name: str) -> str:
    lower = name.lower()
    if any(k in lower for k in ("embed", "bge", "nomic", "e5", "minilm", "gte", "arctic-embed")):
        return "embedding"
    if any(k in lower for k in ("code", "coder", "starcoder", "deepseek-coder")):
        return "code"
    if any(k in lower for k in ("llava", "vision", "bakllava")):
        return "vision"
    return "llm"


# ═══════════════════════════════════════════
#  Ollama Serve 자동 시작 + 주소 자동 연결
# ═══════════════════════════════════════════

_OLLAMA_SERVE_PROC: Optional[subprocess.Popen] = None
_OLLAMA_SERVE_LOG: list[str] = []       # 최근 50줄 로그 보관
_OLLAMA_SERVE_STATUS = {
    "running": False,
    "pid": None,
    "host": "",
    "startedAt": 0,
    "error": "",
}


def _is_ollama_reachable(host: str = "") -> bool:
    """Ollama API가 응답하는지 확인."""
    h = host or _ollama_host()
    try:
        req = urllib.request.Request(f"{h}/api/tags")
        with urllib.request.urlopen(req, timeout=3):
            return True
    except Exception:
        return False


def api_ollama_serve_start(body: dict | None = None) -> dict:
    """ollama serve 를 백그라운드 프로세스로 시작.

    이미 실행 중이면 기존 연결 정보 반환.
    시작 후 stdout/stderr 에서 주소를 파싱하여 자동 연결.

    body: {host?: "0.0.0.0:11434"} — 포트/호스트 오버라이드 (선택)
    """
    global _OLLAMA_SERVE_PROC

    # 이미 Ollama가 실행 중인지 먼저 확인
    host = _ollama_host()
    if _is_ollama_reachable(host):
        _OLLAMA_SERVE_STATUS["running"] = True
        _OLLAMA_SERVE_STATUS["host"] = host
        _update_provider_host(host)
        return {
            "ok": True,
            "status": "already_running",
            "host": host,
            "message": f"Ollama 이미 실행 중 ({host})",
            "error_key": "",
        }

    # CLI 확인
    b = _ollama_bin()
    if not b:
        return {
            "ok": False,
            "error": "ollama CLI 가 설치되어 있지 않습니다. https://ollama.com 에서 설치하세요.",
            "error_key": "err_ollama_not_installed",
        }

    # 이전 프로세스 정리
    if _OLLAMA_SERVE_PROC and _OLLAMA_SERVE_PROC.poll() is None:
        try:
            _OLLAMA_SERVE_PROC.terminate()
            _OLLAMA_SERVE_PROC.wait(timeout=5)
        except Exception:
            pass

    # 커스텀 호스트/포트
    env = dict(os.environ)
    custom_host = ""
    if isinstance(body, dict) and body.get("host"):
        custom_host = body["host"].strip()
        env["OLLAMA_HOST"] = custom_host

    # ollama serve 시작
    try:
        _OLLAMA_SERVE_PROC = subprocess.Popen(
            [b, "serve"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # stderr → stdout 합침
            text=True,
            env=env,
            start_new_session=True,  # 부모 프로세스 종료 시에도 유지
        )
    except Exception as e:
        _OLLAMA_SERVE_STATUS["error"] = str(e)
        return {"ok": False, "error": f"ollama serve 시작 실패: {e}", "error_key": "err_ollama_serve_failed"}

    _OLLAMA_SERVE_STATUS["pid"] = _OLLAMA_SERVE_PROC.pid
    _OLLAMA_SERVE_STATUS["startedAt"] = int(time.time() * 1000)
    _OLLAMA_SERVE_STATUS["error"] = ""
    _OLLAMA_SERVE_LOG.clear()

    # 백그라운드에서 stdout 읽으면서 주소 파싱 + 연결 대기
    detected_host = {"value": ""}

    def _read_output():
        proc = _OLLAMA_SERVE_PROC
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            _OLLAMA_SERVE_LOG.append(line)
            if len(_OLLAMA_SERVE_LOG) > 50:
                _OLLAMA_SERVE_LOG.pop(0)
            log.info("[ollama] %s", line)
            # 주소 파싱: "Listening on 127.0.0.1:11434" 또는 "listening on [::]:11434"
            m = re.search(r"[Ll]istening on\s+(\S+)", line)
            if m:
                addr = m.group(1)
                # [::]:11434 → http://localhost:11434
                if addr.startswith("[::]:"):
                    port = addr.split(":")[-1]
                    addr = f"127.0.0.1:{port}"
                if not addr.startswith("http"):
                    addr = f"http://{addr}"
                detected_host["value"] = addr
                _OLLAMA_SERVE_STATUS["host"] = addr
                _OLLAMA_SERVE_STATUS["running"] = True
                _update_provider_host(addr)
                log.info("ollama serve detected at: %s", addr)

    threading.Thread(target=_read_output, daemon=True).start()

    # 최대 10초 대기하면서 연결 확인
    target_host = custom_host or "http://127.0.0.1:11434"
    for _ in range(20):  # 0.5초 × 20 = 10초
        time.sleep(0.5)
        actual = detected_host["value"] or target_host
        if _is_ollama_reachable(actual):
            _OLLAMA_SERVE_STATUS["running"] = True
            _OLLAMA_SERVE_STATUS["host"] = actual
            _update_provider_host(actual)
            return {
                "ok": True,
                "status": "started",
                "host": actual,
                "pid": _OLLAMA_SERVE_PROC.pid,
                "message": f"Ollama 시작됨 ({actual})",
            }

    # 10초 내 연결 안 됨 — 프로세스 상태 확인
    if _OLLAMA_SERVE_PROC.poll() is not None:
        err = "\n".join(_OLLAMA_SERVE_LOG[-5:])
        _OLLAMA_SERVE_STATUS["running"] = False
        _OLLAMA_SERVE_STATUS["error"] = err
        return {
            "ok": False,
            "error": f"ollama serve 가 즉시 종료됨: {err}",
            "error_key": "err_ollama_serve_exited",
            "log": _OLLAMA_SERVE_LOG[-10:],
        }

    # 프로세스는 살아있지만 아직 응답 없음
    return {
        "ok": True,
        "status": "starting",
        "host": target_host,
        "pid": _OLLAMA_SERVE_PROC.pid,
        "message": "Ollama 시작 중... 잠시 후 연결을 다시 확인하세요.",
        "log": _OLLAMA_SERVE_LOG[-10:],
    }


def api_ollama_serve_stop(body: dict | None = None) -> dict:
    """ollama serve 프로세스 종료."""
    global _OLLAMA_SERVE_PROC
    if not _OLLAMA_SERVE_PROC:
        return {"ok": True, "status": "not_running", "message": "실행 중인 ollama serve 가 없습니다."}

    pid = _OLLAMA_SERVE_PROC.pid
    try:
        _OLLAMA_SERVE_PROC.terminate()
        _OLLAMA_SERVE_PROC.wait(timeout=10)
    except Exception as e:
        try:
            _OLLAMA_SERVE_PROC.kill()
        except Exception:
            pass
        return {"ok": True, "status": "killed", "pid": pid, "message": f"강제 종료됨: {e}"}

    _OLLAMA_SERVE_STATUS["running"] = False
    _OLLAMA_SERVE_STATUS["pid"] = None
    _OLLAMA_SERVE_PROC = None
    return {"ok": True, "status": "stopped", "pid": pid, "message": "Ollama 종료됨"}


def api_ollama_serve_status(query: dict | None = None) -> dict:
    """ollama serve 현재 상태."""
    host = _OLLAMA_SERVE_STATUS.get("host") or _ollama_host()
    reachable = _is_ollama_reachable(host)

    # 프로세스 상태 확인
    proc_alive = False
    if _OLLAMA_SERVE_PROC:
        proc_alive = _OLLAMA_SERVE_PROC.poll() is None

    return {
        "ok": True,
        "running": reachable,
        "processAlive": proc_alive,
        "host": host,
        "pid": _OLLAMA_SERVE_STATUS.get("pid"),
        "startedAt": _OLLAMA_SERVE_STATUS.get("startedAt", 0),
        "error": _OLLAMA_SERVE_STATUS.get("error", ""),
        "log": _OLLAMA_SERVE_LOG[-20:],
        "managedByDashboard": proc_alive,
    }


def _update_provider_host(host: str) -> None:
    """감지된 Ollama 호스트를 프로바이더 레지스트리에 반영."""
    try:
        from .ai_providers import get_registry
        reg = get_registry()
        p = reg.get("ollama-api")
        if p and hasattr(p, "_base_url"):
            p._base_url = host
            log.info("ollama-api provider host updated: %s", host)
    except Exception as e:
        log.warning("failed to update ollama-api host: %s", e)
