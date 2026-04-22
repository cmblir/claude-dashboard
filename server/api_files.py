"""Anthropic Files API 관리 — 업로드 · 목록 · 조회 · 삭제 + 메시지 reference.

파일 업로드는 프론트에서 base64 로 보내고, 서버가 multipart/form-data 로
Anthropic API 에 프록시. 대용량 파일은 권장하지 않음.
"""
from __future__ import annotations

import base64
import json
import time
import uuid
from typing import Any

from .ai_keys import load_api_keys
from .logger import log

_BASE = "https://api.anthropic.com/v1/files"
_TIMEOUT = 120

# Files API 는 베타 — 변경 가능성 있음.
_BETA_HEADER = "files-api-2025-04-14"


def _anthropic_key() -> str:
    keys = load_api_keys()
    val = keys.get("anthropic-api")
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        return val.get("apiKey") or ""
    return ""


def _json_request(method: str, url: str, api_key: str, body: dict | None = None) -> tuple[int, Any]:
    import urllib.request
    import urllib.error

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": _BETA_HEADER,
    }
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": {"message": f"HTTP {e.code}"}}
    except Exception as e:
        return 0, {"error": {"message": str(e)}}


def _multipart_upload(
    url: str, api_key: str, filename: str, data_bytes: bytes, mime: str,
) -> tuple[int, Any]:
    """stdlib 로 multipart/form-data POST. single field 'file'."""
    import urllib.request
    import urllib.error

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    lines: list[bytes] = []
    lines.append(f"--{boundary}".encode("ascii"))
    lines.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8")
    )
    lines.append(f"Content-Type: {mime or 'application/octet-stream'}".encode("ascii"))
    lines.append(b"")
    lines.append(data_bytes)
    lines.append(f"--{boundary}--".encode("ascii"))
    lines.append(b"")
    body = b"\r\n".join(lines)

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": _BETA_HEADER,
    }
    req = urllib.request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw}
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"error": {"message": f"HTTP {e.code}"}}
    except Exception as e:
        return 0, {"error": {"message": str(e)}}


def api_files_list(_query: dict | None = None) -> dict:
    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True, "data": []}
    status, data = _json_request("GET", _BASE, api_key)
    if status != 200:
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
        return {"ok": False, "error": msg or f"HTTP {status}"}
    return {"ok": True, "data": data.get("data") or []}


def api_files_upload(body: dict) -> dict:
    """{filename, mime, base64} 를 받아 Anthropic Files API 에 업로드."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}
    filename = (body.get("filename") or "upload").strip()
    mime = (body.get("mime") or "application/octet-stream").strip()
    b64 = body.get("base64") or ""
    if not isinstance(b64, str) or not b64:
        return {"ok": False, "error": "base64 required"}

    try:
        data_bytes = base64.b64decode(b64)
    except Exception as e:
        return {"ok": False, "error": f"base64 decode failed: {e}"}
    if len(data_bytes) > 30 * 1024 * 1024:
        return {"ok": False, "error": "최대 30MB"}

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}

    t0 = int(time.time() * 1000)
    status, data = _multipart_upload(_BASE, api_key, filename, data_bytes, mime)
    duration = int(time.time() * 1000) - t0

    if status not in (200, 201):
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
        return {"ok": False, "error": msg or f"HTTP {status}", "durationMs": duration}
    return {
        "ok": True,
        "fileId": data.get("id"),
        "filename": data.get("filename"),
        "sizeBytes": data.get("size_bytes"),
        "mimeType": data.get("mime_type"),
        "createdAt": data.get("created_at"),
        "durationMs": duration,
        "raw": data,
    }


def api_files_delete(body: dict) -> dict:
    file_id = (body or {}).get("id") if isinstance(body, dict) else ""
    if not file_id:
        return {"ok": False, "error": "id required"}
    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}
    status, data = _json_request("DELETE", f"{_BASE}/{file_id}", api_key)
    if status not in (200, 204):
        msg = (data.get("error") or {}).get("message") if isinstance(data, dict) else ""
        return {"ok": False, "error": msg or f"HTTP {status}"}
    return {"ok": True, "fileId": file_id}


def api_files_test(body: dict) -> dict:
    """업로드한 파일 id 를 Messages API 에 reference 해서 간단 테스트.

    body: {model, prompt, fileId}
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "body must be object"}

    model = (body.get("model") or "claude-sonnet-4-6").strip()
    prompt = (body.get("prompt") or "").strip()
    file_id = (body.get("fileId") or "").strip()

    if not file_id:
        return {"ok": False, "error": "fileId required"}
    if not prompt:
        return {"ok": False, "error": "prompt required"}

    api_key = _anthropic_key()
    if not api_key:
        return {"ok": False, "needKey": True}

    import urllib.request
    import urllib.error

    body_obj = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "document", "source": {"type": "file", "file_id": file_id}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body_obj).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "anthropic-beta": _BETA_HEADER,
        },
    )
    t0 = int(time.time() * 1000)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            ej = json.loads(e.read().decode("utf-8"))
            msg = (ej.get("error") or {}).get("message") or f"HTTP {e.code}"
        except Exception:
            msg = f"HTTP {e.code}"
        return {"ok": False, "error": msg, "durationMs": int(time.time()*1000)-t0}
    except Exception as e:
        return {"ok": False, "error": str(e), "durationMs": int(time.time()*1000)-t0}

    duration = int(time.time() * 1000) - t0
    text = ""
    for b in (data.get("content") or []):
        if isinstance(b, dict) and b.get("type") == "text":
            text += b.get("text", "")
    return {
        "ok": True,
        "model": model,
        "output": text,
        "durationMs": duration,
        "usage": data.get("usage") or {},
    }
