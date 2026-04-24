"""AI 프로바이더 설정 · API 키 · 커스텀 프로바이더 관리.

`~/.claude-dashboard-ai-providers.json` 에 프로바이더별 설정 저장:
  - API 키 (각 프로바이더별)
  - 커스텀 CLI 프로바이더 정의
  - 폴백 체인 순서
  - 프로바이더별 기본 모델 오버라이드

이 모듈은 ai_providers.py 에서 import 되어 레지스트리 초기화에 사용된다.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .config import _env_path
from .logger import log
from .utils import _safe_read, _safe_write


# ───────── 설정 파일 경로 ─────────

PROVIDERS_CONFIG_PATH = _env_path(
    "CLAUDE_DASHBOARD_AI_PROVIDERS",
    Path.home() / ".claude-dashboard-ai-providers.json",
)


# ───────── 로드/저장 ─────────

def _load_config() -> dict:
    """프로바이더 설정 파일 로드. 없으면 기본 구조 반환."""
    if not PROVIDERS_CONFIG_PATH.exists():
        return _default_config()
    try:
        data = json.loads(_safe_read(PROVIDERS_CONFIG_PATH))
        if not isinstance(data, dict):
            return _default_config()
        data.setdefault("version", 1)
        data.setdefault("apiKeys", {})
        data.setdefault("customProviders", [])
        data.setdefault("fallbackChain", [])
        data.setdefault("defaultModels", {})
        data.setdefault("providerSettings", {})
        return data
    except Exception as e:
        log.warning("ai providers config load failed: %s", e)
        return _default_config()


def _save_config(data: dict) -> bool:
    """설정 파일 저장 (atomic write)."""
    try:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        return _safe_write(PROVIDERS_CONFIG_PATH, text)
    except Exception as e:
        log.error("ai providers config save failed: %s", e)
        return False


def _default_config() -> dict:
    return {
        "version": 1,
        "apiKeys": {},
        "customProviders": [],
        "fallbackChain": ["claude-cli", "anthropic-api", "openai-api", "gemini-api"],
        "defaultModels": {},
        "providerSettings": {},
    }


# ───────── API 키 관리 ─────────

def load_api_keys() -> dict:
    """프로바이더별 API 키/설정 반환.

    반환값: {provider_id: api_key_string | {apiKey, baseUrl, ...}}
    환경 변수 > 설정 파일 우선순위.
    """
    cfg = _load_config()
    keys: dict = {}

    # 설정 파일의 키
    for pid, val in cfg.get("apiKeys", {}).items():
        if isinstance(val, str) and val:
            keys[pid] = val
        elif isinstance(val, dict) and val.get("apiKey"):
            keys[pid] = val

    # 환경 변수 오버라이드
    ENV_MAP = {
        "openai-api": "OPENAI_API_KEY",
        "gemini-api": "GEMINI_API_KEY",
        "anthropic-api": "ANTHROPIC_API_KEY",
    }
    for pid, env_key in ENV_MAP.items():
        env_val = os.environ.get(env_key, "")
        if env_val:
            keys[pid] = env_val

    return keys


def save_api_key(provider_id: str, api_key: str) -> dict:
    """단일 프로바이더의 API 키 저장."""
    if not isinstance(provider_id, str) or not provider_id.strip():
        return {"ok": False, "error": "provider_id required"}
    if not re.match(r"^[a-zA-Z0-9_.-]+$", provider_id):
        return {"ok": False, "error": "invalid provider_id"}

    cfg = _load_config()
    if api_key:
        cfg["apiKeys"][provider_id] = api_key
    else:
        cfg["apiKeys"].pop(provider_id, None)

    ok = _save_config(cfg)
    if ok:
        # 레지스트리 재초기화
        try:
            from .ai_providers import reset_registry
            reset_registry()
        except Exception:
            pass
    return {"ok": ok, "providerId": provider_id}


def save_api_key_with_config(provider_id: str, config: dict) -> dict:
    """API 키 + 추가 설정(baseUrl 등) 저장."""
    if not isinstance(provider_id, str) or not provider_id.strip():
        return {"ok": False, "error": "provider_id required"}
    if not isinstance(config, dict):
        return {"ok": False, "error": "config must be object"}

    cfg = _load_config()
    cfg["apiKeys"][provider_id] = {
        "apiKey": (config.get("apiKey") or "").strip(),
        "baseUrl": (config.get("baseUrl") or "").strip(),
    }
    ok = _save_config(cfg)
    if ok:
        try:
            from .ai_providers import reset_registry
            reset_registry()
        except Exception:
            pass
    return {"ok": ok, "providerId": provider_id}


def delete_api_key(provider_id: str) -> dict:
    """API 키 삭제."""
    cfg = _load_config()
    if provider_id in cfg.get("apiKeys", {}):
        del cfg["apiKeys"][provider_id]
        _save_config(cfg)
        try:
            from .ai_providers import reset_registry
            reset_registry()
        except Exception:
            pass
    return {"ok": True, "providerId": provider_id}


# ───────── 커스텀 프로바이더 관리 ─────────

def load_custom_providers() -> list:
    """커스텀 CLI 프로바이더 인스턴스 리스트 반환."""
    from .ai_providers import CustomCliProvider

    cfg = _load_config()
    out = []
    for entry in cfg.get("customProviders", []):
        if not isinstance(entry, dict):
            continue
        if not entry.get("id") or not entry.get("command"):
            continue
        try:
            out.append(CustomCliProvider(entry))
        except Exception as e:
            log.warning("custom provider load failed: %s — %s", entry.get("id"), e)
    return out


def save_custom_provider(body: dict) -> dict:
    """커스텀 CLI 프로바이더 추가/수정.

    body: {
        id: "my-ai",
        name: "My AI Tool",
        command: "my-ai-cli",
        argsTemplate: "-p {prompt} --model {model}",
        models: ["model-a", "model-b"],
        homepage: "https://...",
        timeout: 300,
    }
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}

    pid = (body.get("id") or "").strip()
    if not re.match(r"^[a-z][a-z0-9_-]{1,40}$", pid):
        return {"ok": False, "error": "id 는 소문자/숫자/-/_ 만 (2~41자)"}

    command = (body.get("command") or "").strip()
    if not command:
        return {"ok": False, "error": "command required"}

    # 빌트인 프로바이더 id 와 충돌 방지
    RESERVED = {"claude-cli", "ollama", "gemini-cli", "codex", "openai-api",
                "gemini-api", "anthropic-api", "ollama-api"}
    if pid in RESERVED:
        return {"ok": False, "error": f"'{pid}' 는 빌트인 프로바이더 — 다른 id 사용"}

    # capabilities: ["chat"], ["embed"], ["chat","embed","code"] 등
    raw_caps = body.get("capabilities") or ["chat"]
    if isinstance(raw_caps, str):
        raw_caps = [c.strip() for c in raw_caps.split(",") if c.strip()]
    VALID_CAPS = {"chat", "embed", "code", "vision", "reasoning"}
    caps = [c for c in raw_caps if isinstance(c, str) and c in VALID_CAPS][:5] or ["chat"]

    entry = {
        "id": pid,
        "name": (body.get("name") or pid).strip()[:80],
        "command": command[:200],
        "argsTemplate": (body.get("argsTemplate") or "{prompt}").strip()[:500],
        "models": _sanitize_models(body.get("models")),
        "homepage": (body.get("homepage") or "").strip()[:200],
        "timeout": max(10, min(3600, int(body.get("timeout") or 300))),
        "capabilities": caps,
        "embedCommand": (body.get("embedCommand") or "").strip()[:200],
        "embedArgsTemplate": (body.get("embedArgsTemplate") or "{input}").strip()[:500],
    }

    cfg = _load_config()
    customs = cfg.get("customProviders", [])
    # 기존 항목 업데이트 or 새로 추가
    replaced = False
    for i, c in enumerate(customs):
        if isinstance(c, dict) and c.get("id") == pid:
            customs[i] = entry
            replaced = True
            break
    if not replaced:
        customs.append(entry)
    cfg["customProviders"] = customs

    ok = _save_config(cfg)
    if ok:
        try:
            from .ai_providers import reset_registry
            reset_registry()
        except Exception:
            pass
    return {"ok": ok, "id": pid, "created": not replaced}


def delete_custom_provider(provider_id: str) -> dict:
    """커스텀 프로바이더 삭제."""
    cfg = _load_config()
    customs = cfg.get("customProviders", [])
    before = len(customs)
    customs = [c for c in customs if not (isinstance(c, dict) and c.get("id") == provider_id)]
    if len(customs) == before:
        return {"ok": False, "error": "not found"}
    cfg["customProviders"] = customs
    _save_config(cfg)
    try:
        from .ai_providers import reset_registry
        reset_registry()
    except Exception:
        pass
    return {"ok": True, "id": provider_id}


def _sanitize_models(raw: Any) -> list:
    """모델 목록 sanitize."""
    if not raw:
        return []
    if isinstance(raw, str):
        return [m.strip() for m in raw.split(",") if m.strip()][:20]
    if isinstance(raw, list):
        out = []
        for m in raw[:20]:
            if isinstance(m, str):
                out.append(m.strip()[:80])
            elif isinstance(m, dict):
                out.append({
                    "id": (m.get("id") or "").strip()[:80],
                    "label": (m.get("label") or m.get("id") or "").strip()[:80],
                    "contextWindow": int(m.get("contextWindow") or 0),
                    "priceIn": float(m.get("priceIn") or 0),
                    "priceOut": float(m.get("priceOut") or 0),
                    "note": (m.get("note") or "").strip()[:200],
                })
        return out
    return []


# ───────── 폴백 체인 관리 ─────────

def get_fallback_chain() -> list[str]:
    cfg = _load_config()
    return cfg.get("fallbackChain", [])


def set_fallback_chain(chain: list[str]) -> dict:
    """폴백 체인 순서 설정."""
    if not isinstance(chain, list):
        return {"ok": False, "error": "chain must be list"}
    sanitized = [str(c).strip()[:40] for c in chain if isinstance(c, str) and c.strip()][:10]
    cfg = _load_config()
    cfg["fallbackChain"] = sanitized
    ok = _save_config(cfg)
    if ok:
        try:
            from .ai_providers import get_registry
            get_registry().set_fallback_chain(sanitized)
        except Exception:
            pass
    return {"ok": ok, "chain": sanitized}


# ───────── 기본 모델 관리 ─────────

def get_default_models() -> dict:
    """프로바이더별 기본 모델 매핑."""
    cfg = _load_config()
    return cfg.get("defaultModels", {})


def set_default_model(provider_id: str, model: str) -> dict:
    cfg = _load_config()
    defaults = cfg.get("defaultModels", {})
    if model:
        defaults[provider_id] = model
    else:
        defaults.pop(provider_id, None)
    cfg["defaultModels"] = defaults
    _save_config(cfg)
    return {"ok": True, "providerId": provider_id, "model": model}


def api_set_default_model(body: dict) -> dict:
    """POST /api/ai-providers/default-model — body: {providerId, model}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    pid = (body.get("providerId") or "").strip()
    model = (body.get("model") or "").strip()
    if not pid:
        return {"ok": False, "error": "providerId required"}
    return set_default_model(pid, model)


# ───────── Ollama 엔진 설정 ─────────

def api_ollama_settings_get() -> dict:
    """Ollama 기본 채팅 모델 + 임베딩 모델 설정 조회."""
    cfg = _load_config()
    ollama_cfg = cfg.get("ollamaSettings") or {}

    # 설치된 모델 목록 가져오기
    installed_chat = []
    installed_embed = []
    try:
        from .ai_providers import get_registry
        reg = get_registry()
        for pid in ("ollama", "ollama-api"):
            p = reg.get(pid)
            if p and p.is_available():
                for m in p.list_models():
                    caps = m.capabilities or ["chat"]
                    entry = {"id": m.id, "label": m.label or m.id, "note": m.note}
                    if "embed" in caps:
                        if not any(x["id"] == m.id for x in installed_embed):
                            installed_embed.append(entry)
                    else:
                        if not any(x["id"] == m.id for x in installed_chat):
                            installed_chat.append(entry)
                break  # 하나만 조회하면 됨
    except Exception:
        pass

    return {
        "ok": True,
        "chatModel": ollama_cfg.get("chatModel", ""),
        "embedModel": ollama_cfg.get("embedModel", ""),
        "installedChat": installed_chat,
        "installedEmbed": installed_embed,
    }


def api_ollama_settings_save(body: dict) -> dict:
    """Ollama 기본 채팅/임베딩 모델 저장. body: {chatModel?, embedModel?}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}

    cfg = _load_config()
    ollama_cfg = cfg.get("ollamaSettings") or {}
    chat_model = (body.get("chatModel") or "").strip()
    embed_model = (body.get("embedModel") or "").strip()

    if chat_model:
        ollama_cfg["chatModel"] = chat_model
    else:
        ollama_cfg.pop("chatModel", None)
    if embed_model:
        ollama_cfg["embedModel"] = embed_model
    else:
        ollama_cfg.pop("embedModel", None)

    cfg["ollamaSettings"] = ollama_cfg
    ok = _save_config(cfg)

    # 프로바이더 레지스트리에 반영
    if ok:
        try:
            from .ai_providers import get_registry
            reg = get_registry()
            # ollama/ollama-api 의 기본 모델 업데이트
            if chat_model:
                set_default_model("ollama", chat_model)
                set_default_model("ollama-api", chat_model)
        except Exception:
            pass

    return {"ok": ok, "chatModel": chat_model, "embedModel": embed_model}


# ───────── API 엔드포인트 핸들러 ─────────

def api_providers_list() -> dict:
    """전체 프로바이더 목록 + 상태.

    v2.33.5 — is_available + list_models 를 ThreadPoolExecutor 로 병렬 프로빙.
    8 빌트인 + custom 에서 CLI subprocess 체크가 누적되면 직렬은 5-6초.
    병렬이면 가장 느린 프로브 하나의 시간 (~1초) 으로 수렴.
    """
    from concurrent.futures import ThreadPoolExecutor
    from .ai_providers import get_registry
    reg = get_registry()

    all_p = list(reg.all_providers())

    def _probe(p):
        try:
            available = p.is_available()
            models = p.list_models() if available else []
        except Exception:  # noqa: BLE001
            available, models = False, []
        return {
            "id": p.provider_id,
            "name": p.provider_name,
            "type": p.provider_type,
            "homepage": p.homepage,
            "icon": p.icon,
            "available": available,
            "capabilities": getattr(p, "capabilities", ["chat"]),
            "modelCount": len(models),
            "models": [m.to_dict() for m in models],
        }

    max_workers = min(16, max(4, len(all_p)))
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        providers = list(ex.map(_probe, all_p))

    cfg = _load_config()
    # API 키 마스킹
    masked_keys = {}
    for pid, val in cfg.get("apiKeys", {}).items():
        key = val if isinstance(val, str) else (val.get("apiKey") or "" if isinstance(val, dict) else "")
        if key:
            masked_keys[pid] = key[:6] + "…" + key[-4:] if len(key) > 12 else "••••"
        else:
            masked_keys[pid] = ""

    return {
        "providers": providers,
        "apiKeys": masked_keys,
        "customProviders": cfg.get("customProviders", []),
        "fallbackChain": cfg.get("fallbackChain", []),
        "defaultModels": cfg.get("defaultModels", {}),
    }


def api_provider_test(body: dict) -> dict:
    """프로바이더 연결 테스트. body: {providerId, model?, prompt?}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}

    from .ai_providers import get_registry
    reg = get_registry()

    pid = (body.get("providerId") or "").strip()
    model = (body.get("model") or "").strip()
    prompt = (body.get("prompt") or "Say 'Hello! I am working.' in one sentence.").strip()

    p = reg.get(pid)
    if not p:
        return {"ok": False, "error": f"unknown provider: {pid}"}

    resp = p.execute(prompt, model=model, timeout=30)
    return {
        "ok": resp.status == "ok",
        "response": resp.to_dict(),
    }


def api_provider_compare(body: dict) -> dict:
    """멀티 AI 비교 — 동일 프롬프트를 여러 프로바이더에 병렬 전송.

    body: {prompt, systemPrompt?, providers: [{providerId, model?}], timeout?}
    반환: {ok, results: [{providerId, model, status, output, duration_ms, tokens_in, tokens_out, cost_usd, error?}]}
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .ai_providers import get_registry

    reg = get_registry()
    prompt = (body.get("prompt") or "").strip()
    sys_prompt = (body.get("systemPrompt") or "").strip()
    targets = body.get("providers") or []
    timeout = min(120, max(10, int(body.get("timeout") or 60)))

    if not prompt:
        return {"ok": False, "error": "prompt required"}
    if not targets or not isinstance(targets, list):
        return {"ok": False, "error": "providers list required"}

    def _run_one(target: dict) -> dict:
        pid = (target.get("providerId") or "").strip()
        model = (target.get("model") or "").strip()
        p = reg.get(pid)
        if not p:
            return {"providerId": pid, "status": "err", "error": f"unknown: {pid}"}
        if not p.is_available():
            return {"providerId": pid, "status": "err", "error": "not available"}
        resp = p.execute(prompt, system_prompt=sys_prompt, model=model, timeout=timeout)
        return {
            "providerId": pid,
            "model": resp.model,
            "status": resp.status,
            "output": (resp.output or "")[:4000],
            "duration_ms": resp.duration_ms,
            "tokens_in": resp.tokens_in,
            "tokens_out": resp.tokens_out,
            "cost_usd": resp.cost_usd,
            "error": resp.error if resp.status == "err" else "",
        }

    results = []
    max_w = min(6, len(targets))
    with ThreadPoolExecutor(max_workers=max_w) as pool:
        futures = {pool.submit(_run_one, t): t for t in targets[:10]}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                t = futures[future]
                results.append({"providerId": t.get("providerId", "?"), "status": "err", "error": str(e)})

    return {"ok": True, "results": results, "prompt": prompt[:200]}


def api_provider_save_key(body: dict) -> dict:
    """API 키 저장. body: {providerId, apiKey, baseUrl?}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    pid = (body.get("providerId") or "").strip()
    key = (body.get("apiKey") or "").strip()
    base_url = (body.get("baseUrl") or "").strip()

    if base_url:
        return save_api_key_with_config(pid, {"apiKey": key, "baseUrl": base_url})
    return save_api_key(pid, key)


def api_provider_delete_key(body: dict) -> dict:
    """API 키 삭제. body: {providerId}"""
    pid = (body or {}).get("providerId", "") if isinstance(body, dict) else ""
    return delete_api_key(pid)


def api_custom_provider_save(body: dict) -> dict:
    """커스텀 프로바이더 저장."""
    return save_custom_provider(body)


def api_custom_provider_delete(body: dict) -> dict:
    """커스텀 프로바이더 삭제. body: {id}"""
    pid = (body or {}).get("id", "") if isinstance(body, dict) else ""
    return delete_custom_provider(pid)


def api_provider_health() -> dict:
    """모든 프로바이더 health check 병렬 실행 — 포트/엔드포인트 정보 포함."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from .ai_providers import get_registry
    import os, shutil

    reg = get_registry()
    results = []

    def _check(p):
        h = p.health_check()
        # endpoint/port 정보 추가
        h["name"] = p.provider_name
        h["icon"] = p.icon
        h["type"] = p.provider_type
        if hasattr(p, "_base_url"):
            h["endpoint"] = p._base_url
        elif hasattr(p, "_host") and callable(p._host):
            h["endpoint"] = p._host()
        elif p.provider_id == "claude-cli":
            cli = shutil.which("claude") or ""
            h["endpoint"] = cli if cli else ""
        elif hasattr(p, "_bin") and callable(p._bin):
            h["endpoint"] = p._bin() or ""
        elif p.provider_type == "api":
            h["endpoint"] = p.homepage
        return h

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_check, p): p for p in reg.all_providers()}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                p = futures[future]
                results.append({"provider": p.provider_id, "name": p.provider_name,
                                "icon": p.icon, "available": False, "error": str(e)})

    results.sort(key=lambda r: (not r.get("available", False), r.get("provider", "")))
    available = sum(1 for r in results if r.get("available"))
    return {"ok": True, "results": results, "total": len(results), "available": available}


def api_usage_alert_check() -> dict:
    """사용량 임계치 초과 확인.

    설정 파일의 alerts 필드에서 임계치를 읽고, 현재 비용 집계와 비교.
    """
    cfg = _load_config()
    alerts = cfg.get("alerts") or {}
    max_cost = float(alerts.get("maxDailyCostUsd") or 0)
    max_tokens = int(alerts.get("maxDailyTokens") or 0)
    if not max_cost and not max_tokens:
        return {"ok": True, "alerts": [], "configured": False}

    # 오늘 비용 집계
    from .db import _db, _db_init
    from datetime import datetime
    _db_init()
    today = datetime.now().strftime("%Y-%m-%d")
    with _db() as c:
        row = c.execute(
            "SELECT COALESCE(SUM(cost_usd),0) AS cost, COALESCE(SUM(tokens_total),0) AS tokens,"
            " COUNT(*) AS calls FROM workflow_costs WHERE ts >= ?",
            (int(datetime.strptime(today, "%Y-%m-%d").timestamp() * 1000),)
        ).fetchone()

    fired = []
    if max_cost > 0 and row["cost"] >= max_cost:
        fired.append({"type": "cost", "threshold": max_cost, "current": round(row["cost"], 4),
                       "message": f"일일 비용 ${row['cost']:.4f} ≥ ${max_cost} 초과"})
    if max_tokens > 0 and row["tokens"] >= max_tokens:
        fired.append({"type": "tokens", "threshold": max_tokens, "current": row["tokens"],
                       "message": f"일일 토큰 {row['tokens']:,} ≥ {max_tokens:,} 초과"})
    return {"ok": True, "alerts": fired, "configured": True,
            "today": {"cost": round(row["cost"], 4), "tokens": row["tokens"], "calls": row["calls"]}}


def api_usage_alert_set(body: dict) -> dict:
    """사용량 알림 임계치 설정. body: {maxDailyCostUsd?, maxDailyTokens?}"""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cfg = _load_config()
    cfg["alerts"] = {
        "maxDailyCostUsd": max(0, float(body.get("maxDailyCostUsd") or 0)),
        "maxDailyTokens": max(0, int(body.get("maxDailyTokens") or 0)),
    }
    ok = _save_config(cfg)
    return {"ok": ok, "alerts": cfg["alerts"]}


def api_fallback_chain_save(body: dict) -> dict:
    """폴백 체인 저장. body: {chain: [...]}"""
    chain = (body or {}).get("chain", []) if isinstance(body, dict) else []
    return set_fallback_chain(chain)


def api_workflow_costs_summary() -> dict:
    """워크플로우 프로바이더별 비용 집계."""
    from .db import _db, _db_init
    from collections import defaultdict

    _db_init()
    with _db() as c:
        # 전체 집계
        totals = c.execute(
            "SELECT COALESCE(SUM(tokens_in),0) AS ti, COALESCE(SUM(tokens_out),0) AS to_,"
            " COALESCE(SUM(tokens_total),0) AS tt, COALESCE(SUM(cost_usd),0) AS cost,"
            " COUNT(*) AS n FROM workflow_costs"
        ).fetchone()

        # 프로바이더별
        by_provider = [dict(r) for r in c.execute(
            "SELECT provider, model, COUNT(*) AS calls,"
            " SUM(tokens_in) AS tokens_in, SUM(tokens_out) AS tokens_out,"
            " SUM(tokens_total) AS tokens_total, SUM(cost_usd) AS cost_usd,"
            " SUM(duration_ms) AS duration_ms"
            " FROM workflow_costs GROUP BY provider, model"
            " ORDER BY cost_usd DESC"
        ).fetchall()]

        # 최근 30일 일별
        import time
        thirty = int((time.time() - 30 * 86400) * 1000)
        daily_rows = c.execute(
            "SELECT ts, provider, tokens_total, cost_usd"
            " FROM workflow_costs WHERE ts >= ?", (thirty,)
        ).fetchall()

    # 일자별 bucket
    from datetime import datetime
    daily: dict = defaultdict(lambda: {"calls": 0, "tokens": 0, "cost": 0.0})
    for r in daily_rows:
        if not r["ts"]:
            continue
        d = datetime.fromtimestamp(r["ts"] / 1000).strftime("%Y-%m-%d")
        daily[d]["calls"] += 1
        daily[d]["tokens"] += r["tokens_total"] or 0
        daily[d]["cost"] += r["cost_usd"] or 0
    timeline = [{"date": d, **v} for d, v in sorted(daily.items())][-30:]

    return {
        "totals": {
            "tokensIn": totals["ti"], "tokensOut": totals["to_"],
            "tokensTotal": totals["tt"], "costUsd": round(totals["cost"], 4),
            "calls": totals["n"],
        },
        "byProvider": by_provider,
        "timeline": timeline,
    }
