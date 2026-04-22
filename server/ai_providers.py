"""멀티 AI 프로바이더 추상 레이어.

CLI 기반 (claude, ollama, gemini CLI, codex) + API 기반 (OpenAI, Gemini, Anthropic)
을 통합하는 인터페이스. 워크플로우 노드의 `assignee` 가 `provider:model` 형태일 때
적절한 프로바이더를 선택·실행한다.

설계 원칙:
  1. 기존 `claude -p` 동작 완전 호환 (ClaudeCliProvider 가 기본)
  2. CLI 우선 — 로컬 CLI 가 있으면 API 대신 CLI 사용 가능
  3. 프로바이더별 모델 카탈로그 + 가격표 내장
  4. 폴백 체인 — 1차 실패 시 대안 프로바이더 자동 전환
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from .logger import log


# ───────── CLI 탐지 헬퍼 ─────────
# LaunchAgent · GUI 실행 등 PATH 가 제한된 환경에서도 CLI 를 탐지하기 위해
# 홈브류/전역 npm/ nvm/ asdf/ pyenv 등 통상 설치 경로를 fallback 으로 검색한다.
_CLI_SEARCH_PATHS: list[str] = [
    "/opt/homebrew/bin",            # Apple Silicon Homebrew
    "/usr/local/bin",               # Intel Homebrew · 일반 /usr/local 설치
    "/usr/bin", "/bin", "/sbin", "/usr/sbin",
    str(Path.home() / ".local/bin"),
    str(Path.home() / "bin"),
    str(Path.home() / ".bun/bin"),
    str(Path.home() / ".cargo/bin"),
    str(Path.home() / ".deno/bin"),
    "/opt/homebrew/sbin",
]


def _which(name: str) -> str:
    """PATH 기반 탐지 → 실패 시 통상 설치 경로 fallback."""
    found = shutil.which(name)
    if found:
        return found
    # PATH 가 비정상적으로 좁혀져 있을 때를 대비한 보강 경로 검색
    extra_path = os.pathsep.join(_CLI_SEARCH_PATHS)
    merged = (os.environ.get("PATH", "") + os.pathsep + extra_path).strip(os.pathsep)
    found = shutil.which(name, path=merged)
    if found:
        return found
    # nvm / asdf — 버전 디렉터리 전수 탐색
    for base in (
        Path.home() / ".nvm" / "versions" / "node",
        Path.home() / ".asdf" / "installs" / "nodejs",
        Path.home() / ".volta" / "bin",
    ):
        if not base.exists():
            continue
        # nvm / asdf: 각 버전 디렉터리의 bin/<name> 검사
        if base.name == "bin":
            candidate = base / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
            continue
        try:
            for ver in sorted(base.iterdir(), reverse=True):
                cand = ver / "bin" / name
                if cand.is_file() and os.access(cand, os.X_OK):
                    return str(cand)
        except Exception:
            pass
    return ""


# ───────── 응답 공통 데이터클래스 ─────────

@dataclass
class AIResponse:
    """모든 프로바이더가 반환하는 통일된 응답 형식."""
    status: str = "ok"              # "ok" | "err"
    output: str = ""                # 생성된 텍스트
    error: str = ""                 # 에러 메시지
    provider: str = ""              # "claude-cli", "ollama", "openai-api", ...
    model: str = ""                 # 실제 사용된 모델 id
    session_id: str = ""            # CLI 모드에서 세션 추적용
    tokens_in: int = 0
    tokens_out: int = 0
    tokens_total: int = 0
    duration_ms: int = 0
    cost_usd: float = 0.0          # 추정 비용 (가격표 기반)
    raw: dict = field(default_factory=dict)  # 프로바이더별 원본 응답

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EmbeddingResponse:
    """임베딩 프로바이더가 반환하는 통일된 응답 형식."""
    status: str = "ok"              # "ok" | "err"
    embeddings: list = field(default_factory=list)  # [[float, ...], ...]
    error: str = ""
    provider: str = ""
    model: str = ""
    dimensions: int = 0             # 벡터 차원
    tokens_used: int = 0
    duration_ms: int = 0
    cost_usd: float = 0.0
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # embeddings 는 크기가 클 수 있으므로 요약만
        if d["embeddings"]:
            d["embeddingCount"] = len(d["embeddings"])
            d["dimensions"] = len(d["embeddings"][0]) if d["embeddings"] else 0
            d["embeddings"] = f"[{len(d['embeddings'])} vectors]"
        return d


# ───────── 모델 정보 데이터클래스 ─────────

# 모델 capability 상수
CAP_CHAT = "chat"          # 대화/생성
CAP_EMBED = "embed"        # 임베딩
CAP_CODE = "code"          # 코드 생성 특화
CAP_VISION = "vision"      # 이미지 입력
CAP_REASONING = "reasoning" # 추론 모드 (o3 등)


@dataclass
class ModelInfo:
    """프로바이더별 모델 메타데이터."""
    id: str
    label: str
    context_window: int = 0         # 토큰
    price_in: float = 0.0           # USD per 1M tokens
    price_out: float = 0.0
    price_cache_read: float = 0.0
    price_cache_create: float = 0.0
    supports_system_prompt: bool = True
    supports_streaming: bool = True
    supports_tools: bool = False
    capabilities: list = field(default_factory=lambda: [CAP_CHAT])  # ["chat", "embed", "code", ...]
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ───────── 프로바이더 기본 인터페이스 ─────────

class BaseProvider(ABC):
    """모든 AI 프로바이더의 추상 베이스 클래스."""

    # 서브클래스가 설정하는 메타데이터
    provider_id: str = ""           # "claude-cli", "ollama", "openai-api", ...
    provider_name: str = ""         # 표시명
    provider_type: str = ""         # "cli" | "api"
    homepage: str = ""
    icon: str = ""                  # 이모지 또는 아이콘 키
    capabilities: list = [CAP_CHAT] # 기본: 채팅만. 서브클래스가 오버라이드

    @abstractmethod
    def is_available(self) -> bool:
        """프로바이더 사용 가능 여부 (CLI 설치됨 / API 키 설정됨)."""

    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """사용 가능한 모델 목록."""

    def list_models_by_capability(self, cap: str) -> list[ModelInfo]:
        """특정 capability 를 가진 모델만 필터."""
        return [m for m in self.list_models() if cap in (m.capabilities or [CAP_CHAT])]

    @abstractmethod
    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        """프롬프트 실행 → 응답 반환."""

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "",
        timeout: int = 60,
    ) -> EmbeddingResponse:
        """텍스트 임베딩 생성. 지원하지 않는 프로바이더는 기본 에러 반환."""
        return EmbeddingResponse(
            status="err",
            error=f"provider '{self.provider_id}' does not support embeddings",
            provider=self.provider_id,
        )

    def supports(self, cap: str) -> bool:
        """이 프로바이더가 특정 capability 를 지원하는지."""
        return cap in self.capabilities

    def health_check(self) -> dict:
        """프로바이더 상태 확인."""
        try:
            available = self.is_available()
            models = self.list_models() if available else []
            return {
                "provider": self.provider_id,
                "available": available,
                "modelCount": len(models),
                "models": [m.id for m in models[:10]],
                "capabilities": self.capabilities,
            }
        except Exception as e:
            return {"provider": self.provider_id, "available": False, "error": str(e)}

    def estimate_cost(self, model: str, tokens_in: int, tokens_out: int,
                      cache_read: int = 0, cache_create: int = 0) -> float:
        """모델별 비용 추정 (USD)."""
        models = {m.id: m for m in self.list_models()}
        m = models.get(model)
        if not m:
            return 0.0
        return (
            tokens_in * m.price_in
            + tokens_out * m.price_out
            + cache_read * m.price_cache_read
            + cache_create * m.price_cache_create
        ) / 1_000_000

    def to_dict(self) -> dict:
        """프론트엔드 표시용 메타데이터."""
        return {
            "id": self.provider_id,
            "name": self.provider_name,
            "type": self.provider_type,
            "homepage": self.homepage,
            "icon": self.icon,
            "available": self.is_available(),
            "capabilities": self.capabilities,
        }


# ═══════════════════════════════════════════
#  CLI 기반 프로바이더들
# ═══════════════════════════════════════════

class ClaudeCliProvider(BaseProvider):
    """Claude Code CLI (`claude -p`) — 기존 동작과 100% 호환."""

    provider_id = "claude-cli"
    provider_name = "Claude (CLI)"
    provider_type = "cli"
    homepage = "https://docs.anthropic.com/en/docs/claude-code"
    icon = "🟠"

    _MODELS = [
        ModelInfo("claude-opus-4-7", "Opus 4.7 (1M)", 1_000_000,
                  15.0, 75.0, 1.5, 18.75, note="최강 성능"),
        ModelInfo("claude-opus-4-6", "Opus 4.6", 1_000_000,
                  15.0, 75.0, 1.5, 18.75, note="Fast mode 기본"),
        ModelInfo("claude-sonnet-4-6", "Sonnet 4.6", 200_000,
                  3.0, 15.0, 0.3, 3.75, note="균형형"),
        ModelInfo("claude-haiku-4-5", "Haiku 4.5", 200_000,
                  0.8, 4.0, 0.08, 1.0, note="가장 빠름/저렴"),
    ]

    # 별칭 매핑 — 워크플로우에서 짧은 이름 사용 가능
    _ALIASES = {
        "opus": "claude-opus-4-7",
        "opus-4.7": "claude-opus-4-7",
        "opus-4.6": "claude-opus-4-6",
        "sonnet": "claude-sonnet-4-6",
        "sonnet-4.6": "claude-sonnet-4-6",
        "haiku": "claude-haiku-4-5",
        "haiku-4.5": "claude-haiku-4-5",
    }

    def _bin(self) -> str:
        return _which("claude")

    def is_available(self) -> bool:
        return bool(self._bin())

    def list_models(self) -> list[ModelInfo]:
        return list(self._MODELS)

    def _resolve_model(self, model: str) -> str:
        if not model:
            return ""
        return self._ALIASES.get(model.lower(), model)

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        extra = extra or {}
        t0 = int(time.time() * 1000)
        claude_bin = self._bin()
        if not claude_bin:
            return AIResponse(
                status="err", error="claude CLI not found in PATH",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        resolved_model = self._resolve_model(model)
        cwd_safe = cwd or str(Path.home())

        cmd = [claude_bin, "-p", prompt, "--output-format", "json"]
        if resolved_model:
            cmd += ["--model", resolved_model]
        if system_prompt:
            cmd += ["--system-prompt", system_prompt]
        # 추가 CLI 옵션 (워크플로우 하네스에서 전달)
        for opt_key in ("appendSystemPrompt", "allowedTools", "disallowedTools", "resumeSessionId"):
            val = (extra.get(opt_key) or "").strip()
            if val:
                flag = {
                    "appendSystemPrompt": "--append-system-prompt",
                    "allowedTools": "--allowed-tools",
                    "disallowedTools": "--disallowed-tools",
                    "resumeSessionId": "--resume",
                }[opt_key]
                cmd += [flag, val]

        try:
            r = subprocess.run(
                cmd, cwd=cwd_safe, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return AIResponse(
                status="err", error=f"timeout after {timeout}s",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        if r.returncode != 0:
            return AIResponse(
                status="err",
                error=(r.stderr or "").strip()[:1000] or f"exit {r.returncode}",
                provider=self.provider_id, duration_ms=duration,
            )

        stdout = r.stdout or ""
        output = stdout
        session_id = ""
        raw_parsed = {}
        try:
            parsed = json.loads(stdout)
            if isinstance(parsed, dict):
                raw_parsed = parsed
                output = parsed.get("result") or parsed.get("content") or stdout
                session_id = parsed.get("session_id") or parsed.get("sessionId") or ""
        except Exception:
            pass

        return AIResponse(
            status="ok", output=output, provider=self.provider_id,
            model=resolved_model or "default", session_id=session_id,
            duration_ms=duration, raw=raw_parsed,
        )


class OllamaProvider(BaseProvider):
    """Ollama (로컬) — HTTP API 사용 (ollama run 은 인터랙티브라 서버에서 사용 불가).

    CLI 설치 여부로 available 판단하되, 실제 실행은 HTTP API (/api/generate).
    설치된 모델 자동 감지 + 첫 번째 모델을 기본값으로 사용.
    """

    provider_id = "ollama"
    provider_name = "Ollama (로컬)"
    provider_type = "cli"
    homepage = "https://ollama.com"
    icon = "🦙"

    def _host(self) -> str:
        return (os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")

    def _bin(self) -> str:
        return _which("ollama")

    def is_available(self) -> bool:
        # CLI 설치됨 + API 응답 가능
        if not self._bin():
            return False
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._host()}/api/tags")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    def _first_installed_model(self) -> str:
        """설치된 첫 번째 chat 모델 반환 (embedding 제외)."""
        models = self.list_models()
        for m in models:
            if CAP_EMBED not in (m.capabilities or []):
                return m.id
        return models[0].id if models else ""

    def list_models(self) -> list[ModelInfo]:
        """HTTP API 로 설치된 모델 조회."""
        try:
            import urllib.request
            req = urllib.request.Request(f"{self._host()}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = []
            embed_hints = {"embed", "bge", "nomic", "e5", "minilm", "gte", "arctic-embed"}
            for m in data.get("models", []):
                name = m.get("name", "")
                is_embed = any(h in name.lower() for h in embed_hints)
                caps = [CAP_EMBED] if is_embed else [CAP_CHAT]
                out.append(ModelInfo(
                    id=name, label=name, note="로컬 — 무료",
                    capabilities=caps,
                ))
            return out
        except Exception:
            return []

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        """Ollama HTTP API (/api/generate) 로 실행 — 인터랙티브 문제 없음."""
        import urllib.request
        import urllib.error

        t0 = int(time.time() * 1000)
        if not model:
            model = self._first_installed_model()
        if not model:
            return AIResponse(
                status="err", error="설치된 Ollama 모델이 없습니다. 모델 허브에서 다운로드하세요.",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        body_obj = {"model": model, "prompt": prompt, "stream": False}
        if system_prompt:
            body_obj["system"] = system_prompt

        body = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            f"{self._host()}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            return AIResponse(
                status="err", error=f"HTTP {e.code}: {err_body}",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        output = data.get("response", "")
        ti = data.get("prompt_eval_count", 0)
        to_ = data.get("eval_count", 0)

        return AIResponse(
            status="ok", output=output,
            provider=self.provider_id, model=model,
            tokens_in=ti, tokens_out=to_, tokens_total=ti + to_,
            duration_ms=duration, raw=data,
        )


class GeminiCliProvider(BaseProvider):
    """Gemini CLI (gemini) — Google 의 CLI 도구."""

    provider_id = "gemini-cli"
    provider_name = "Gemini (CLI)"
    provider_type = "cli"
    homepage = "https://github.com/google-gemini/gemini-cli"
    icon = "💎"

    def _bin(self) -> str:
        return _which("gemini")

    def is_available(self) -> bool:
        return bool(self._bin())

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo("gemini-2.5-pro", "Gemini 2.5 Pro", 1_000_000,
                      1.25, 10.0, note="Google 최강 모델"),
            ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash", 1_000_000,
                      0.15, 0.60, note="빠르고 저렴"),
            ModelInfo("gemini-2.0-flash", "Gemini 2.0 Flash", 1_000_000,
                      0.10, 0.40, note="경량"),
        ]

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        t0 = int(time.time() * 1000)
        b = self._bin()
        if not b:
            return AIResponse(
                status="err", error="gemini CLI not found in PATH",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        # gemini CLI: gemini -p "prompt" 형태 (설치 상태에 따라 다를 수 있음)
        cmd = [b, "-p", full_prompt]
        if model:
            cmd += ["--model", model]

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                cwd=cwd or None,
                stdin=subprocess.DEVNULL,  # 인터랙티브 모드 방지
            )
        except subprocess.TimeoutExpired:
            return AIResponse(
                status="err", error=f"timeout after {timeout}s",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        if r.returncode != 0:
            return AIResponse(
                status="err",
                error=(r.stderr or "").strip()[:1000] or f"exit {r.returncode}",
                provider=self.provider_id, model=model, duration_ms=duration,
            )

        return AIResponse(
            status="ok", output=(r.stdout or "").strip(),
            provider=self.provider_id, model=model or "gemini-2.5-pro",
            duration_ms=duration,
        )


class CodexProvider(BaseProvider):
    """OpenAI Codex CLI — 코드 생성 특화."""

    provider_id = "codex"
    provider_name = "Codex (CLI)"
    provider_type = "cli"
    homepage = "https://github.com/openai/codex"
    icon = "🧬"

    def _bin(self) -> str:
        return _which("codex")

    def is_available(self) -> bool:
        return bool(self._bin())

    def list_models(self) -> list[ModelInfo]:
        return [
            ModelInfo("o4-mini", "o4-mini", 200_000,
                      1.10, 4.40, note="Codex 기본 모델"),
            ModelInfo("o3", "o3", 200_000,
                      2.0, 8.0, note="고성능 추론"),
            ModelInfo("gpt-4.1", "GPT-4.1", 1_000_000,
                      2.0, 8.0, note="긴 컨텍스트"),
        ]

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        t0 = int(time.time() * 1000)
        b = self._bin()
        if not b:
            return AIResponse(
                status="err", error="codex CLI not found in PATH",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        full_prompt = prompt
        if system_prompt:
            full_prompt = f"{system_prompt}\n\n{prompt}"

        cmd = [b, "-q", full_prompt]  # -q = quiet (non-interactive)
        if model:
            cmd += ["--model", model]

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                cwd=cwd or None,
            )
        except subprocess.TimeoutExpired:
            return AIResponse(
                status="err", error=f"timeout after {timeout}s",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        if r.returncode != 0:
            return AIResponse(
                status="err",
                error=(r.stderr or "").strip()[:1000] or f"exit {r.returncode}",
                provider=self.provider_id, model=model, duration_ms=duration,
            )

        return AIResponse(
            status="ok", output=(r.stdout or "").strip(),
            provider=self.provider_id, model=model or "o4-mini",
            duration_ms=duration,
        )


class CustomCliProvider(BaseProvider):
    """사용자 정의 CLI 프로바이더 — 임의의 CLI 도구를 등록.

    워크플로우 노드의 assignee 에서 `custom-id:model` 형태로 사용 가능.
    config 에 capabilities 를 지정하면 해당 기능만 노출 (기본: [chat]).
    embedCommand 가 별도로 있으면 embed() 도 지원.
    """

    provider_type = "cli"
    icon = "⚙️"

    def __init__(self, config: dict):
        """config: {id, name, command, argsTemplate, models, homepage?,
                    capabilities?, embedCommand?, embedArgsTemplate?}

        argsTemplate 에서 사용 가능한 플레이스홀더:
          {prompt}  — 사용자 프롬프트
          {system}  — 시스템 프롬프트
          {model}   — 모델 id
          {cwd}     — 작업 디렉토리
          {input}   — 입력 텍스트 (embed 용)
        """
        self.provider_id = config.get("id", "custom")
        self.provider_name = config.get("name", "Custom CLI")
        self.homepage = config.get("homepage", "")
        self._command = config.get("command", "")
        self._args_template = config.get("argsTemplate", "{prompt}")
        self._models_raw = config.get("models", [])
        self._timeout_default = int(config.get("timeout", 300))
        # capabilities: 사용자가 지정 가능 (chat, embed, code 등)
        raw_caps = config.get("capabilities") or ["chat"]
        self.capabilities = [str(c) for c in raw_caps if isinstance(c, str)][:5]
        # embedding 전용 명령어 (별도 CLI 명령이 필요한 경우)
        self._embed_command = config.get("embedCommand", "")
        self._embed_args_template = config.get("embedArgsTemplate", "{input}")

    def _bin(self) -> str:
        return _which(self._command)

    def is_available(self) -> bool:
        return bool(self._bin())

    def list_models(self) -> list[ModelInfo]:
        out = []
        for m in self._models_raw:
            if isinstance(m, str):
                out.append(ModelInfo(id=m, label=m, capabilities=list(self.capabilities)))
            elif isinstance(m, dict):
                caps = m.get("capabilities", self.capabilities)
                out.append(ModelInfo(
                    id=m.get("id", ""), label=m.get("label", m.get("id", "")),
                    context_window=int(m.get("contextWindow", 0)),
                    price_in=float(m.get("priceIn", 0)),
                    price_out=float(m.get("priceOut", 0)),
                    note=m.get("note", ""),
                    capabilities=[str(c) for c in caps] if isinstance(caps, list) else list(self.capabilities),
                ))
        return out

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 0,
        extra: dict | None = None,
    ) -> AIResponse:
        t0 = int(time.time() * 1000)
        b = self._bin()
        if not b:
            return AIResponse(
                status="err", error=f"{self._command} not found in PATH",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        tmpl = self._args_template
        args_str = tmpl.replace("{prompt}", prompt)
        args_str = args_str.replace("{system}", system_prompt or "")
        args_str = args_str.replace("{model}", model or "")
        args_str = args_str.replace("{cwd}", cwd or str(Path.home()))

        # 간단한 shlex-like split (따옴표 미지원 — 단순 공백 분리)
        cmd = [b] + [a for a in args_str.split() if a]
        to = timeout or self._timeout_default

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=to,
                cwd=cwd or None,
            )
        except subprocess.TimeoutExpired:
            return AIResponse(
                status="err", error=f"timeout after {to}s",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        if r.returncode != 0:
            return AIResponse(
                status="err",
                error=(r.stderr or "").strip()[:1000] or f"exit {r.returncode}",
                provider=self.provider_id, model=model, duration_ms=duration,
            )

        return AIResponse(
            status="ok", output=(r.stdout or "").strip(),
            provider=self.provider_id, model=model, duration_ms=duration,
        )

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "",
        timeout: int = 60,
    ) -> EmbeddingResponse:
        """커스텀 프로바이더 임베딩 — embedCommand 가 설정된 경우에만."""
        t0 = int(time.time() * 1000)
        cmd_name = self._embed_command or self._command
        b = _which(cmd_name)
        if not b:
            return EmbeddingResponse(
                status="err", error=f"{cmd_name} not found in PATH",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        tmpl = self._embed_args_template or "{input}"
        input_text = "\n".join(texts)
        args_str = tmpl.replace("{input}", input_text)
        args_str = args_str.replace("{model}", model or "")
        cmd = [b] + [a for a in args_str.split() if a]

        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
        except Exception as e:
            return EmbeddingResponse(
                status="err", error=str(e),
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        if r.returncode != 0:
            return EmbeddingResponse(
                status="err", error=(r.stderr or "").strip()[:500],
                provider=self.provider_id, duration_ms=duration,
            )

        # stdout 에서 JSON 배열 파싱 시도
        output = (r.stdout or "").strip()
        embeddings = []
        try:
            parsed = json.loads(output)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], (list, float, int)):
                if isinstance(parsed[0], (float, int)):
                    embeddings = [parsed]  # 단일 벡터
                else:
                    embeddings = parsed
        except Exception:
            pass

        dims = len(embeddings[0]) if embeddings else 0
        return EmbeddingResponse(
            status="ok", embeddings=embeddings,
            provider=self.provider_id, model=model,
            dimensions=dims, duration_ms=duration,
        )


# ═══════════════════════════════════════════
#  API 기반 프로바이더들
# ═══════════════════════════════════════════

class OpenAIApiProvider(BaseProvider):
    """OpenAI API — HTTP 직접 호출 (requests 미사용, urllib)."""

    provider_id = "openai-api"
    provider_name = "OpenAI (API)"
    provider_type = "api"
    homepage = "https://platform.openai.com"
    icon = "🤖"
    capabilities = [CAP_CHAT, CAP_EMBED, CAP_CODE, CAP_VISION, CAP_REASONING]

    _MODELS = [
        ModelInfo("gpt-4.1", "GPT-4.1", 1_000_000,
                  2.0, 8.0, note="최신 플래그십", capabilities=[CAP_CHAT, CAP_CODE]),
        ModelInfo("gpt-4.1-mini", "GPT-4.1 Mini", 1_000_000,
                  0.40, 1.60, note="저렴한 대안", capabilities=[CAP_CHAT, CAP_CODE]),
        ModelInfo("gpt-4.1-nano", "GPT-4.1 Nano", 1_000_000,
                  0.10, 0.40, note="가장 저렴"),
        ModelInfo("gpt-4o", "GPT-4o", 128_000,
                  2.50, 10.0, note="멀티모달"),
        ModelInfo("gpt-4o-mini", "GPT-4o Mini", 128_000,
                  0.15, 0.60, note="빠르고 저렴"),
        ModelInfo("o4-mini", "o4-mini", 200_000,
                  1.10, 4.40, note="추론 모델"),
        ModelInfo("o3", "o3", 200_000,
                  2.0, 8.0, note="고성능 추론"),
        ModelInfo("o3-mini", "o3-mini", 200_000,
                  1.10, 4.40, note="추론 경량", capabilities=[CAP_CHAT, CAP_REASONING]),
        # ── Embedding 모델 ──
        ModelInfo("text-embedding-3-large", "Embedding 3 Large", 8_191,
                  0.13, 0.0, note="3072 dims, 최고 품질", capabilities=[CAP_EMBED]),
        ModelInfo("text-embedding-3-small", "Embedding 3 Small", 8_191,
                  0.02, 0.0, note="1536 dims, 저렴", capabilities=[CAP_EMBED]),
        ModelInfo("text-embedding-ada-002", "Embedding Ada 002", 8_191,
                  0.10, 0.0, note="1536 dims, legacy", capabilities=[CAP_EMBED]),
    ]

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[ModelInfo]:
        return list(self._MODELS)

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        import urllib.request
        import urllib.error

        t0 = int(time.time() * 1000)
        if not self._api_key:
            return AIResponse(
                status="err", error="OPENAI_API_KEY not set",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        model = model or "gpt-4.1-mini"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body = json.dumps({
            "model": model,
            "messages": messages,
            "max_tokens": int((extra or {}).get("max_tokens", 4096)),
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            return AIResponse(
                status="err", error=f"HTTP {e.code}: {err_body}",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        output = ""
        choices = data.get("choices", [])
        if choices:
            output = (choices[0].get("message") or {}).get("content", "")

        usage = data.get("usage") or {}
        ti = usage.get("prompt_tokens", 0)
        to_ = usage.get("completion_tokens", 0)
        cost = self.estimate_cost(model, ti, to_)

        return AIResponse(
            status="ok", output=output,
            provider=self.provider_id, model=model,
            tokens_in=ti, tokens_out=to_, tokens_total=ti + to_,
            cost_usd=cost, duration_ms=duration, raw=data,
        )

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "",
        timeout: int = 60,
    ) -> EmbeddingResponse:
        """OpenAI Embeddings API 호출."""
        import urllib.request
        import urllib.error

        t0 = int(time.time() * 1000)
        if not self._api_key:
            return EmbeddingResponse(
                status="err", error="OPENAI_API_KEY not set",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        model = model or "text-embedding-3-small"
        body = json.dumps({"input": texts, "model": model}).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/embeddings",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            return EmbeddingResponse(
                status="err", error=f"HTTP {e.code}: {err_body}",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return EmbeddingResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        embeddings = [d["embedding"] for d in data.get("data", [])]
        dims = len(embeddings[0]) if embeddings else 0
        usage = data.get("usage") or {}
        tokens = usage.get("total_tokens", 0)
        cost = self.estimate_cost(model, tokens, 0)

        return EmbeddingResponse(
            status="ok", embeddings=embeddings,
            provider=self.provider_id, model=model,
            dimensions=dims, tokens_used=tokens,
            cost_usd=cost, duration_ms=duration, raw=data,
        )


class GeminiApiProvider(BaseProvider):
    """Google Gemini API — HTTP 직접 호출."""

    provider_id = "gemini-api"
    provider_name = "Gemini (API)"
    provider_type = "api"
    homepage = "https://ai.google.dev"
    icon = "💎"

    _MODELS = [
        ModelInfo("gemini-2.5-pro", "Gemini 2.5 Pro", 1_000_000,
                  1.25, 10.0, note="Google 최강"),
        ModelInfo("gemini-2.5-flash", "Gemini 2.5 Flash", 1_000_000,
                  0.15, 0.60, note="빠르고 저렴"),
        ModelInfo("gemini-2.0-flash", "Gemini 2.0 Flash", 1_000_000,
                  0.10, 0.40, note="경량"),
    ]

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "") or os.environ.get("GOOGLE_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[ModelInfo]:
        return list(self._MODELS)

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        import urllib.request
        import urllib.error

        t0 = int(time.time() * 1000)
        if not self._api_key:
            return AIResponse(
                status="err", error="GEMINI_API_KEY not set",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        model = model or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={self._api_key}"

        body_obj: dict = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        if system_prompt:
            body_obj["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        body = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            return AIResponse(
                status="err", error=f"HTTP {e.code}: {err_body}",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        output = ""
        candidates = data.get("candidates", [])
        if candidates:
            parts = (candidates[0].get("content") or {}).get("parts", [])
            if parts:
                output = parts[0].get("text", "")

        usage = data.get("usageMetadata") or {}
        ti = usage.get("promptTokenCount", 0)
        to_ = usage.get("candidatesTokenCount", 0)
        cost = self.estimate_cost(model, ti, to_)

        return AIResponse(
            status="ok", output=output,
            provider=self.provider_id, model=model,
            tokens_in=ti, tokens_out=to_, tokens_total=ti + to_,
            cost_usd=cost, duration_ms=duration, raw=data,
        )


class AnthropicApiProvider(BaseProvider):
    """Anthropic Messages API — claude CLI 없이 직접 API 호출."""

    provider_id = "anthropic-api"
    provider_name = "Claude (API)"
    provider_type = "api"
    homepage = "https://docs.anthropic.com/en/api"
    icon = "🟠"

    _MODELS = ClaudeCliProvider._MODELS  # 같은 모델 카탈로그 공유

    def __init__(self, api_key: str = ""):
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[ModelInfo]:
        return list(self._MODELS)

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        import urllib.request
        import urllib.error

        t0 = int(time.time() * 1000)
        if not self._api_key:
            return AIResponse(
                status="err", error="ANTHROPIC_API_KEY not set",
                provider=self.provider_id, duration_ms=int(time.time() * 1000) - t0,
            )

        resolved = ClaudeCliProvider._ALIASES.get((model or "").lower(), model) or "claude-sonnet-4-6"
        body_obj: dict = {
            "model": resolved,
            "max_tokens": int((extra or {}).get("max_tokens", 4096)),
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_prompt:
            body_obj["system"] = system_prompt

        body = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
            },
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            return AIResponse(
                status="err", error=f"HTTP {e.code}: {err_body}",
                provider=self.provider_id, model=resolved,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=resolved,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        output = ""
        for block in data.get("content", []):
            if isinstance(block, dict) and block.get("type") == "text":
                output += block.get("text", "")

        usage = data.get("usage") or {}
        ti = usage.get("input_tokens", 0)
        to_ = usage.get("output_tokens", 0)
        cost = self.estimate_cost(resolved, ti, to_)

        return AIResponse(
            status="ok", output=output,
            provider=self.provider_id, model=resolved,
            tokens_in=ti, tokens_out=to_, tokens_total=ti + to_,
            cost_usd=cost, duration_ms=duration, raw=data,
        )


class OllamaApiProvider(BaseProvider):
    """Ollama HTTP API — CLI 대신 REST API 직접 호출 (원격 서버 지원).

    chat + embedding 모두 지원. embedding 모델(bge-m3, nomic-embed-text 등)은
    자동 감지되어 list_models 에서 capability=[CAP_EMBED] 로 태깅된다.
    """

    provider_id = "ollama-api"
    provider_name = "Ollama (API)"
    provider_type = "api"
    homepage = "https://ollama.com"
    icon = "🦙"
    capabilities = [CAP_CHAT, CAP_EMBED]

    # 모델 이름에 이 키워드가 포함되면 embedding 모델로 인식
    _EMBED_HINTS = {"embed", "bge", "nomic-embed", "e5", "gte", "instructor",
                    "mxbai-embed", "snowflake-arctic-embed", "all-minilm"}

    def __init__(self, base_url: str = "", api_key: str = ""):
        self._base_url = (
            base_url
            or os.environ.get("OLLAMA_HOST", "")
            or "http://localhost:11434"
        ).rstrip("/")
        self._api_key = api_key  # Ollama 는 보통 키 불필요

    def is_available(self) -> bool:
        import urllib.request
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3):
                return True
        except Exception:
            return False

    def _is_embed_model(self, name: str) -> bool:
        lower = name.lower()
        return any(h in lower for h in self._EMBED_HINTS)

    def list_models(self) -> list[ModelInfo]:
        import urllib.request
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            out = []
            for m in data.get("models", []):
                name = m.get("name", "")
                is_embed = self._is_embed_model(name)
                caps = [CAP_EMBED] if is_embed else [CAP_CHAT]
                note = "임베딩 모델 — 무료" if is_embed else "로컬 — 무료"
                out.append(ModelInfo(
                    id=name, label=name, note=note, capabilities=caps,
                ))
            return out
        except Exception:
            return []

    def execute(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        model: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
    ) -> AIResponse:
        import urllib.request
        import urllib.error

        t0 = int(time.time() * 1000)
        if not model:
            # 설치된 첫 번째 chat 모델 사용 (embedding 제외)
            models = self.list_models()
            chat_models = [m for m in models if CAP_EMBED not in (m.capabilities or [])]
            model = chat_models[0].id if chat_models else (models[0].id if models else "llama3.1")
        body_obj = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if system_prompt:
            body_obj["system"] = system_prompt

        body = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return AIResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        output = data.get("response", "")
        ti = data.get("prompt_eval_count", 0)
        to_ = data.get("eval_count", 0)

        return AIResponse(
            status="ok", output=output,
            provider=self.provider_id, model=model,
            tokens_in=ti, tokens_out=to_, tokens_total=ti + to_,
            duration_ms=duration, raw=data,
        )

    def embed(
        self,
        texts: list[str],
        *,
        model: str = "",
        timeout: int = 60,
    ) -> EmbeddingResponse:
        """Ollama /api/embed 엔드포인트로 임베딩 생성.

        model 예시: bge-m3, nomic-embed-text, mxbai-embed-large
        """
        import urllib.request
        import urllib.error

        t0 = int(time.time() * 1000)
        model = model or "bge-m3"  # 기본 임베딩 모델

        body_obj = {"model": model, "input": texts}
        body = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base_url}/api/embed",
            data=body,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")[:500]
            except Exception:
                pass
            return EmbeddingResponse(
                status="err", error=f"HTTP {e.code}: {err_body}",
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )
        except Exception as e:
            return EmbeddingResponse(
                status="err", error=str(e),
                provider=self.provider_id, model=model,
                duration_ms=int(time.time() * 1000) - t0,
            )

        duration = int(time.time() * 1000) - t0
        embeddings = data.get("embeddings", [])
        dims = len(embeddings[0]) if embeddings else 0

        return EmbeddingResponse(
            status="ok", embeddings=embeddings,
            provider=self.provider_id, model=model,
            dimensions=dims, duration_ms=duration,
            tokens_used=data.get("prompt_eval_count", 0),
            raw={"model": model, "count": len(embeddings), "dimensions": dims},
        )


# ═══════════════════════════════════════════
#  프로바이더 레지스트리 (싱글턴)
# ═══════════════════════════════════════════

class ProviderRegistry:
    """모든 프로바이더를 등록·조회·실행하는 중앙 레지스트리.

    사용법:
        registry = get_registry()
        resp = registry.execute("claude-cli", "opus", prompt="Hello")
    """

    def __init__(self):
        self._providers: dict[str, BaseProvider] = {}
        self._fallback_chain: list[str] = []
        self._initialized = False

    def register(self, provider: BaseProvider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str) -> Optional[BaseProvider]:
        return self._providers.get(provider_id)

    def all_providers(self) -> list[BaseProvider]:
        return list(self._providers.values())

    def available_providers(self) -> list[BaseProvider]:
        return [p for p in self._providers.values() if p.is_available()]

    def set_fallback_chain(self, chain: list[str]) -> None:
        """실패 시 시도할 프로바이더 순서."""
        self._fallback_chain = chain

    def resolve_assignee(self, assignee: str) -> tuple[str, str]:
        """assignee 문자열 → (provider_id, model).

        지원 형식:
          "opus-4.7"         → ("claude-cli", "claude-opus-4-7")
          "claude:opus"      → ("claude-cli", "claude-opus-4-7")
          "openai:gpt-4.1"   → ("openai-api", "gpt-4.1")
          "gemini:2.5-pro"   → ("gemini-cli" or "gemini-api", "gemini-2.5-pro")
          "ollama:llama3.1"  → ("ollama" or "ollama-api", "llama3.1")
          "codex:o4-mini"    → ("codex", "o4-mini")
          "custom-id:model"  → ("custom-id", "model")
        """
        if not assignee or assignee.strip() == "":
            return ("claude-cli", "")

        # provider:model 형태
        if ":" in assignee:
            parts = assignee.split(":", 1)
            provider_hint = parts[0].strip().lower()
            model = parts[1].strip() if len(parts) > 1 else ""

            # 프로바이더 별칭 → 실제 id
            PROVIDER_ALIASES = {
                "claude": "claude-cli",
                "claude-cli": "claude-cli",
                "claude-api": "anthropic-api",
                "anthropic": "anthropic-api",
                "openai": "openai-api",
                "gpt": "openai-api",
                "gemini": "gemini-cli",  # CLI 우선
                "gemini-cli": "gemini-cli",
                "gemini-api": "gemini-api",
                "google": "gemini-api",
                "ollama": "ollama",
                "ollama-api": "ollama-api",
                "codex": "codex",
            }
            pid = PROVIDER_ALIASES.get(provider_hint, provider_hint)

            # gemini: CLI 설치 안 됐으면 API 폴백
            if pid == "gemini-cli":
                p = self.get(pid)
                if not p or not p.is_available():
                    pid = "gemini-api"

            # ollama: CLI 설치 안 됐으면 API 폴백
            if pid == "ollama":
                p = self.get(pid)
                if not p or not p.is_available():
                    pid = "ollama-api"

            return (pid, model)

        # 프로바이더 없이 모델만 — Claude 별칭 확인
        if assignee.lower() in ClaudeCliProvider._ALIASES:
            return ("claude-cli", ClaudeCliProvider._ALIASES[assignee.lower()])

        # 알려진 프로바이더 id 인지 확인
        if assignee in self._providers:
            return (assignee, "")

        # 기본: Claude CLI 에 모델명으로 전달
        return ("claude-cli", assignee)

    def execute(
        self,
        provider_id: str,
        model: str,
        prompt: str,
        *,
        system_prompt: str = "",
        cwd: str = "",
        timeout: int = 300,
        extra: dict | None = None,
        fallback: bool = True,
    ) -> AIResponse:
        """프로바이더 실행 + 폴백 체인."""
        # 1차 시도
        p = self.get(provider_id)
        if p and p.is_available():
            resp = p.execute(
                prompt, system_prompt=system_prompt, model=model,
                cwd=cwd, timeout=timeout, extra=extra,
            )
            if resp.status == "ok":
                return resp
            # 에러지만 폴백 미사용이면 바로 반환
            if not fallback:
                return resp
            log.warning("provider %s failed: %s — trying fallback", provider_id, resp.error)

        # 폴백 체인
        if fallback and self._fallback_chain:
            for fid in self._fallback_chain:
                if fid == provider_id:
                    continue
                fp = self.get(fid)
                if not fp or not fp.is_available():
                    continue
                log.info("fallback to provider: %s", fid)
                resp = fp.execute(
                    prompt, system_prompt=system_prompt, model=model,
                    cwd=cwd, timeout=timeout, extra=extra,
                )
                if resp.status == "ok":
                    return resp

        # 모든 시도 실패
        if not p:
            return AIResponse(
                status="err",
                error=f"provider '{provider_id}' not registered",
                provider=provider_id,
            )
        if not p.is_available():
            return AIResponse(
                status="err",
                error=f"provider '{provider_id}' not available (CLI not installed or API key missing)",
                provider=provider_id,
            )
        return AIResponse(
            status="err", error="all providers failed", provider=provider_id,
        )

    def to_dict(self) -> dict:
        """전체 프로바이더 상태 요약."""
        return {
            "providers": [p.to_dict() for p in self._providers.values()],
            "available": [p.provider_id for p in self.available_providers()],
            "fallbackChain": self._fallback_chain,
        }


# ───────── 글로벌 레지스트리 (lazy init) ─────────

_REGISTRY: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """프로바이더 레지스트리 싱글턴. 첫 호출 시 빌트인 프로바이더 등록."""
    global _REGISTRY
    if _REGISTRY is not None:
        return _REGISTRY

    reg = ProviderRegistry()

    # 빌트인 CLI 프로바이더
    reg.register(ClaudeCliProvider())
    reg.register(OllamaProvider())
    reg.register(GeminiCliProvider())
    reg.register(CodexProvider())

    # 빌트인 API 프로바이더
    reg.register(OpenAIApiProvider())
    reg.register(GeminiApiProvider())
    reg.register(AnthropicApiProvider())
    reg.register(OllamaApiProvider())

    # 사용자 정의 프로바이더 로드 (ai_keys.py 에서 설정 파일 읽기)
    try:
        from .ai_keys import load_custom_providers
        for custom in load_custom_providers():
            reg.register(custom)
    except Exception as e:
        log.warning("custom providers load failed: %s", e)

    # API 키 로드 (설정 파일에서)
    try:
        from .ai_keys import load_api_keys
        keys = load_api_keys()
        for pid, key_or_cfg in keys.items():
            p = reg.get(pid)
            if p and hasattr(p, "_api_key") and isinstance(key_or_cfg, str):
                p._api_key = key_or_cfg
            elif p and isinstance(key_or_cfg, dict):
                if hasattr(p, "_api_key"):
                    p._api_key = key_or_cfg.get("apiKey", "")
                if hasattr(p, "_base_url"):
                    p._base_url = key_or_cfg.get("baseUrl", p._base_url)
    except Exception as e:
        log.warning("api keys load failed: %s", e)

    # 기본 폴백 체인: Claude CLI → Anthropic API → OpenAI API
    reg.set_fallback_chain(["claude-cli", "anthropic-api", "openai-api", "gemini-api"])

    _REGISTRY = reg
    return reg


def reset_registry() -> None:
    """레지스트리 재초기화 (설정 변경 후 호출)."""
    global _REGISTRY
    _REGISTRY = None


# ───────── 편의 함수 ─────────

# ───────── Rate Limiter (토큰 버킷) ─────────

class _RateLimiter:
    """프로바이더별 요청 빈도 제한 (토큰 버킷 알고리즘)."""

    def __init__(self):
        self._buckets: dict[str, dict] = {}  # {provider_id: {tokens, max, refill_rate, last_refill}}
        self._lock = threading.Lock()

    def configure(self, provider_id: str, max_rpm: int = 60) -> None:
        """분당 최대 요청 수 설정."""
        with self._lock:
            self._buckets[provider_id] = {
                "tokens": float(max_rpm),
                "max": float(max_rpm),
                "refill_rate": max_rpm / 60.0,  # 초당 리필
                "last_refill": time.time(),
            }

    def acquire(self, provider_id: str, timeout: float = 30.0) -> bool:
        """토큰 1개 획득. 가능하면 True, 타임아웃 내 불가하면 False."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                bucket = self._buckets.get(provider_id)
                if not bucket:
                    return True  # 미설정이면 무제한
                now = time.time()
                elapsed = now - bucket["last_refill"]
                bucket["tokens"] = min(bucket["max"], bucket["tokens"] + elapsed * bucket["refill_rate"])
                bucket["last_refill"] = now
                if bucket["tokens"] >= 1.0:
                    bucket["tokens"] -= 1.0
                    return True
            time.sleep(0.1)
        return False

    def get_status(self) -> dict:
        """현재 rate limit 상태."""
        with self._lock:
            out = {}
            for pid, b in self._buckets.items():
                out[pid] = {"tokens": round(b["tokens"], 1), "max": b["max"],
                            "rpm": int(b["max"])}
            return out


_rate_limiter = _RateLimiter()


def get_rate_limiter() -> _RateLimiter:
    return _rate_limiter


def execute_with_assignee(
    assignee: str,
    prompt: str,
    *,
    system_prompt: str = "",
    cwd: str = "",
    timeout: int = 300,
    extra: dict | None = None,
    fallback: bool = True,
) -> AIResponse:
    """워크플로우 노드에서 직접 호출하는 편의 함수.

    assignee 예시: "claude:opus", "openai:gpt-4.1", "ollama:llama3.1", "codex:o4-mini"
    """
    reg = get_registry()
    pid, model = reg.resolve_assignee(assignee)
    return reg.execute(
        pid, model, prompt,
        system_prompt=system_prompt, cwd=cwd,
        timeout=timeout, extra=extra, fallback=fallback,
    )


def embed_with_provider(
    provider_id: str,
    texts: list[str],
    *,
    model: str = "",
    timeout: int = 60,
) -> EmbeddingResponse:
    """워크플로우 embedding 노드에서 호출하는 편의 함수."""
    reg = get_registry()
    p = reg.get(provider_id)
    if not p:
        return EmbeddingResponse(status="err", error=f"provider not found: {provider_id}")
    if not p.supports(CAP_EMBED):
        return EmbeddingResponse(status="err", error=f"provider '{provider_id}' does not support embeddings")
    return p.embed(texts, model=model, timeout=timeout)


def list_providers_by_capability(cap: str) -> list[dict]:
    """특정 capability 를 가진 프로바이더 + 모델 목록."""
    reg = get_registry()
    out = []
    for p in reg.available_providers():
        if not p.supports(cap):
            continue
        models = p.list_models_by_capability(cap)
        if models:
            out.append({
                "id": p.provider_id,
                "name": p.provider_name,
                "icon": p.icon,
                "type": p.provider_type,
                "models": [m.to_dict() for m in models],
            })
    return out
