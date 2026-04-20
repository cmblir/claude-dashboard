"""프로젝트 스코프 API — 목록·디테일·점수·도구 분포 + 프로젝트별 에이전트 관리.

- list_projects : ~/.claude/projects/<slug>/ 스캔
- api_project_detail : 프로젝트별 CLAUDE.md/settings.json/에이전트/세션 집계
- api_project_score_detail / _tool_breakdown : 분석 뷰
- AGENT_ROLE_CATALOG : 16개 역할 프리셋 (프론트엔드가 프리셋 사용)
- api_project_agent_add/delete/save : <cwd>/.claude/agents/*.md 편집
- SUBAGENT_MODEL_CHOICES / api_subagent_set_model : 서브에이전트 모델 핀 고정
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from .agents import _resolve_agent_path
from .claude_md import get_settings
from .config import (
    AGENTS_DIR, CLAUDE_JSON, PROJECTS_DIR, SCORE_MIN_TOOLS,
)
from .db import _db, _db_init
from .utils import (
    _iso_ms, _parse_frontmatter, _parse_tools_field,
    _safe_read, _safe_write, _strip_frontmatter,
)


def _slug_to_cwd_map() -> dict:
    """DB에서 slug(project_dir) → 실제 cwd 매핑."""
    _db_init()
    mapping: dict = {}
    try:
        with _db() as c:
            for r in c.execute(
                "SELECT project_dir, MAX(cwd) AS cwd FROM sessions WHERE cwd != '' GROUP BY project_dir"
            ).fetchall():
                if r["project_dir"] and r["cwd"]:
                    mapping[r["project_dir"]] = r["cwd"]
    except Exception:
        pass
    return mapping


def _resolve_cwd_from_jsonl(meta_dir: Path) -> str:
    """메타 디렉토리 하위 jsonl 첫 줄에서 cwd 복원 (DB 미인덱스 세션용 fallback)."""
    for jsonl in meta_dir.glob("*.jsonl"):
        try:
            text = jsonl.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines()[:30]:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                c_val = msg.get("cwd")
                if isinstance(c_val, str) and c_val:
                    return c_val
        except Exception:
            continue
    return ""


def list_projects() -> dict:
    projects = []
    if not PROJECTS_DIR.exists():
        return {"projects": []}

    slug_map = _slug_to_cwd_map()

    for p in sorted(PROJECTS_DIR.iterdir()):
        if not p.is_dir():
            continue
        slug = p.name
        cwd = slug_map.get(slug) or _resolve_cwd_from_jsonl(p)

        name = Path(cwd).name if cwd else slug
        has_claude_md = False
        if cwd:
            try:
                has_claude_md = (Path(cwd) / "CLAUDE.md").exists()
            except Exception:
                has_claude_md = False

        session_files = list(p.glob("*.jsonl"))
        projects.append({
            "name": name,
            "slug": slug,
            "path": cwd,                 # 실제 cwd (없으면 빈 문자열)
            "metaDir": str(p),           # ~/.claude/projects/<slug>
            "cwdResolved": bool(cwd),
            "hasClaudeMd": has_claude_md,
            "sessionCount": len(session_files),
        })
    return {"projects": projects}


def _scan_repo_local_claude(cwd: str) -> dict:
    """<cwd>/.claude 디렉토리에서 에이전트/커맨드/훅/스킬/settings 전부 스캔."""
    out = {
        "exists": False,
        "claudeMd": None,
        "claudeMdPath": "",
        "agents": [],
        "commands": [],
        "skills": [],
        "hooks": [],
        "settingsLocal": None,
        "settingsLocalPath": "",
    }
    base = Path(cwd) if cwd else None
    if not base or not base.exists():
        return out

    # CLAUDE.md (repo root)
    claude_md = base / "CLAUDE.md"
    if claude_md.exists():
        out["claudeMd"] = _safe_read(claude_md, 20000)
        out["claudeMdPath"] = str(claude_md)

    dot = base / ".claude"
    if not dot.exists() or not dot.is_dir():
        return out
    out["exists"] = True

    # agents
    agents_dir = dot / "agents"
    if agents_dir.exists():
        for p in sorted(agents_dir.glob("*.md")):
            meta = _parse_frontmatter(_safe_read(p, 4000))
            out["agents"].append({
                "id": p.stem,
                "name": meta.get("name", p.stem),
                "description": meta.get("description", ""),
                "model": meta.get("model", "inherit"),
                "tools": _parse_tools_field(meta.get("tools", "")),
                "path": str(p),
            })

    # commands
    cmd_dir = dot / "commands"
    if cmd_dir.exists():
        for p in sorted(cmd_dir.rglob("*.md")):
            meta = _parse_frontmatter(_safe_read(p, 2000))
            rel = p.relative_to(cmd_dir)
            out["commands"].append({
                "id": str(rel).replace("/", ":").replace(".md", ""),
                "name": meta.get("name", p.stem),
                "description": meta.get("description", ""),
                "path": str(p),
            })

    # skills
    skills_dir = dot / "skills"
    if skills_dir.exists():
        for sp in sorted(skills_dir.iterdir()):
            if not sp.is_dir():
                continue
            sm = sp / "SKILL.md"
            meta = _parse_frontmatter(_safe_read(sm)) if sm.exists() else {}
            out["skills"].append({
                "id": sp.name,
                "name": meta.get("name", sp.name),
                "description": meta.get("description", ""),
                "path": str(sp),
            })

    # hooks (dir listing — 자유 형식)
    hooks_dir = dot / "hooks"
    if hooks_dir.exists():
        for p in sorted(hooks_dir.iterdir()):
            if p.is_file():
                out["hooks"].append({"name": p.name, "path": str(p)})

    # settings.local.json
    settings_local = dot / "settings.local.json"
    if settings_local.exists():
        try:
            out["settingsLocal"] = json.loads(_safe_read(settings_local))
        except Exception:
            out["settingsLocal"] = {"_raw": _safe_read(settings_local, 4000)}
        out["settingsLocalPath"] = str(settings_local)

    return out


def api_project_detail(query: dict) -> dict:
    """프로젝트 cwd 기준 스냅샷: 저장소-로컬 .claude + ~/.claude.json 프로젝트 엔트리 + 세션 목록."""
    cwd = (query.get("cwd", [""])[0] or "").strip()
    if not cwd:
        return {"error": "cwd required"}

    # 입력이 슬러그 형태(절대경로/틸드 아님)면 DB의 실제 cwd로 복원
    if not cwd.startswith("/") and not cwd.startswith("~"):
        slug_map = _slug_to_cwd_map()
        resolved = slug_map.get(cwd) or slug_map.get(cwd.replace("/", "-"))
        if not resolved:
            # 메타 디렉토리 jsonl 에서 복원 시도
            meta_dir = PROJECTS_DIR / cwd
            if meta_dir.exists():
                resolved = _resolve_cwd_from_jsonl(meta_dir)
        if not resolved:
            return {"error": f"프로젝트 슬러그 '{cwd}' 의 실제 경로를 찾을 수 없습니다 (세션 재인덱스 필요할 수 있음)"}
        cwd = resolved

    # 안전: 홈 디렉토리 하위만 허용
    expanded = os.path.expanduser(cwd)
    abs_path = os.path.abspath(expanded)
    home = str(Path.home())
    if not (abs_path == home or abs_path.startswith(home + os.sep)):
        return {"error": "path outside home"}

    # 저장소-로컬 설정
    repo = _scan_repo_local_claude(abs_path)

    # ~/.claude.json 내 per-project 엔트리
    project_entry = {}
    if CLAUDE_JSON.exists():
        try:
            data = json.loads(_safe_read(CLAUDE_JSON, 200000))
            projects = data.get("projects") or {}
            entry = projects.get(abs_path) or {}
            # 큰 필드는 잘라서
            project_entry = {
                "allowedTools": entry.get("allowedTools", []),
                "mcpServers": list((entry.get("mcpServers") or {}).keys()),
                "enabledMcpjsonServers": entry.get("enabledMcpjsonServers", []),
                "disabledMcpjsonServers": entry.get("disabledMcpjsonServers", []),
                "hasTrustDialogAccepted": entry.get("hasTrustDialogAccepted"),
                "lastCost": entry.get("lastCost"),
                "lastAPIDuration": entry.get("lastAPIDuration"),
                "lastDuration": entry.get("lastDuration"),
                "lastLinesAdded": entry.get("lastLinesAdded"),
                "lastLinesRemoved": entry.get("lastLinesRemoved"),
                "onboardingSeenCount": entry.get("projectOnboardingSeenCount"),
            }
        except Exception:
            pass

    # 이 cwd 에서 실행된 세션들 (DB)
    _db_init()
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT session_id, score, score_breakdown, started_at, duration_ms, message_count, tool_use_count, agent_call_count, error_count, first_user_prompt, model, subagent_types FROM sessions WHERE cwd=? ORDER BY started_at DESC LIMIT 200",
            (abs_path,)
        ).fetchall()]
    for r in rows:
        try: r["score_breakdown"] = json.loads(r.get("score_breakdown") or "{}")
        except Exception: r["score_breakdown"] = {}
        try: r["subagent_types"] = json.loads(r.get("subagent_types") or "{}")
        except Exception: r["subagent_types"] = {}
    avg_score = int(sum(r["score"] or 0 for r in rows) / len(rows)) if rows else 0

    return {
        "cwd": abs_path,
        "name": Path(abs_path).name,
        "repo": repo,
        "claudeJsonEntry": project_entry,
        "sessions": rows,
        "stats": {
            "sessionCount": len(rows),
            "avgScore": avg_score,
            "totalTools": sum(r["tool_use_count"] or 0 for r in rows),
            "totalErrors": sum(r["error_count"] or 0 for r in rows),
            "totalAgents": sum(r["agent_call_count"] or 0 for r in rows),
        },
    }


def api_project_score_detail(query: dict) -> dict:
    cwd = (query.get("cwd", [""])[0] or "").strip()
    project_dir = (query.get("projectDir", [""])[0] or "").strip()
    if not cwd and not project_dir:
        return {"error": "cwd or projectDir required"}

    _db_init()
    with _db() as c:
        if cwd:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE cwd=? ORDER BY started_at DESC",
                (cwd,)
            ).fetchall()]
        else:
            rows = [dict(r) for r in c.execute(
                "SELECT * FROM sessions WHERE project_dir=? ORDER BY started_at DESC",
                (project_dir,)
            ).fetchall()]
    if not rows and not cwd:
        # project_dir 슬러그에서 cwd 복원 시도 (첫 행의 cwd)
        cwd = ""

    # cwd 가 row에서 추출 가능하면 사용
    cwd_resolved = cwd or (rows[0].get("cwd") if rows and rows[0].get("cwd") else "")

    avg_breakdown = _project_avg_breakdown(rows)
    total_avg = round(sum(avg_breakdown.values()), 1)

    # sessions 요약 (상위/하위)
    rows_sorted = sorted(rows, key=lambda r: r.get("score") or 0, reverse=True)
    best = rows_sorted[:3]
    worst = rows_sorted[-3:][::-1] if len(rows_sorted) > 3 else []
    for r in best + worst:
        try: r["score_breakdown"] = json.loads(r.get("score_breakdown") or "{}")
        except Exception: r["score_breakdown"] = {}

    # 프로젝트-로컬 상태
    repo = _scan_repo_local_claude(cwd_resolved) if cwd_resolved else {}
    settings = get_settings()
    recs = _suggest_files_for_project(cwd_resolved, avg_breakdown, repo, settings) if cwd_resolved else []

    return {
        "cwd": cwd_resolved,
        "projectDir": project_dir,
        "sessionCount": len(rows),
        "totalAvg": total_avg,
        "avgBreakdown": avg_breakdown,
        "formula": SCORE_FORMULA,
        "best": best,
        "worst": worst,
        "recommendations": recs,
        "repoHas": {
            "claudeMd": bool(repo.get("claudeMd")) if repo else False,
            "agents": len((repo or {}).get("agents", [])),
            "skills": len((repo or {}).get("skills", [])),
            "commands": len((repo or {}).get("commands", [])),
            "settingsLocal": bool((repo or {}).get("settingsLocal")),
            "hooks": len((repo or {}).get("hooks", [])),
        },
    }


def api_project_tool_breakdown(query: dict) -> dict:
    """프로젝트 cwd 의 도구 사용 내역 드릴다운."""
    cwd = (query.get("cwd", [""])[0] or "").strip()
    if not cwd:
        return {"error": "cwd required"}
    if not cwd.startswith("/"):
        mapping = _slug_to_cwd_map()
        cwd = mapping.get(cwd, cwd)

    _db_init()
    with _db() as c:
        sess_rows = c.execute(
            "SELECT session_id, score FROM sessions WHERE cwd=?", (cwd,)
        ).fetchall()
        if not sess_rows:
            return {"cwd": cwd, "tools": [], "subagents": [], "total": 0, "sessionCount": 0}
        session_ids = [r["session_id"] for r in sess_rows]
        placeholders = ",".join("?" * len(session_ids))
        tools = [dict(r) for r in c.execute(
            f"""SELECT tool,
                       COUNT(*) AS n,
                       SUM(CASE WHEN had_error=1 THEN 1 ELSE 0 END) AS errors,
                       SUM(CASE WHEN subagent_type != '' THEN 1 ELSE 0 END) AS via_agents
                FROM tool_uses WHERE session_id IN ({placeholders})
                GROUP BY tool ORDER BY n DESC""",
            session_ids,
        ).fetchall()]
        subagents = [dict(r) for r in c.execute(
            f"""SELECT subagent_type AS name, COUNT(*) AS n
                FROM tool_uses
                WHERE session_id IN ({placeholders}) AND subagent_type != ''
                GROUP BY subagent_type ORDER BY n DESC""",
            session_ids,
        ).fetchall()]
    total = sum(t["n"] for t in tools)
    return {
        "cwd": cwd,
        "sessionCount": len(session_ids),
        "total": total,
        "tools": tools,
        "subagents": subagents,
    }


AGENT_ROLE_CATALOG = [
    {
        "id": "backend-dev", "icon": "🖥️", "label": "백엔드 개발자",
        "summary": "REST/GraphQL API, DB 스키마, 비즈니스 로직 구현을 주도.",
        "defaultName": "backend-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 이 프로젝트의 **백엔드 개발자**다. 다음 원칙을 지킨다:\n\n"
            "1. 새 API 추가 시 기존 레이어링(router/use-case/repository) 패턴을 Grep 으로 확인 후 일치시킨다.\n"
            "2. DB 변경은 반드시 마이그레이션 파일을 함께 만든다.\n"
            "3. 비즈니스 로직은 use-case 레이어에 두고 router 는 얇게 유지.\n"
            "4. 외부 API 호출은 반드시 timeout/retry 정책 포함.\n"
            "5. 변경 후 관련 테스트를 실행·통과시킨다.\n\n"
            "### 출력 형식\n- 변경 계획 3-5줄\n- 영향 파일 리스트\n- 추가된/변경된 테스트 케이스\n"
        ),
    },
    {
        "id": "frontend-dev", "icon": "🎨", "label": "프론트엔드 개발자",
        "summary": "React/Next.js/Vue 컴포넌트와 상태 관리, 접근성·성능 고려.",
        "defaultName": "frontend-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 이 프로젝트의 **프론트엔드 개발자**다.\n\n"
            "1. 컴포넌트 생성 전 기존 디자인 토큰/컴포넌트 라이브러리를 Grep 으로 확인.\n"
            "2. 접근성(aria-*, 키보드) 기본. 시각 요소에만 의존 금지.\n"
            "3. 상태 관리는 기존 패턴(zustand/redux/context) 따르기.\n"
            "4. 성능: 큰 리스트는 가상화, 이미지 lazy-loading, 불필요 re-render 제거.\n"
            "5. 스토리북/테스트를 함께 업데이트.\n"
        ),
    },
    {
        "id": "fullstack-dev", "icon": "🧩", "label": "풀스택 개발자",
        "summary": "프론트·백엔드 모두 다루는 얇은 수직 슬라이스 구현.",
        "defaultName": "fullstack-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 풀스택 개발자다. 기능 요청이 오면:\n"
            "1. DB 스키마 → 백엔드 엔드포인트 → 프론트 UI → 테스트 순으로 얇게 먼저 완성.\n"
            "2. 레이어 사이 계약(타입/스키마)을 먼저 정의하고 양쪽에서 참조.\n"
            "3. 완전 구현 전 mock 으로 통합 흐름 확인.\n"
        ),
    },
    {
        "id": "ml-engineer", "icon": "🧠", "label": "머신러닝 엔지니어",
        "summary": "모델 학습·평가·배포 파이프라인, 데이터셋 처리, 지표 추적.",
        "defaultName": "ml-engineer",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 머신러닝 엔지니어다.\n\n"
            "1. 새 모델은 baseline 부터 시작: 기존 평가 지표로 먼저 측정.\n"
            "2. 학습 스크립트는 시드 고정 + config 파일화.\n"
            "3. 데이터셋 변경 시 버전 태그/해시 기록.\n"
            "4. 추론 코드에는 배치 크기·디바이스·dtype 명시.\n"
            "5. 실험 결과는 표 형식으로 보고 (base vs new).\n"
        ),
    },
    {
        "id": "data-scientist", "icon": "📊", "label": "데이터 사이언티스트",
        "summary": "EDA, 가설 검증, 비즈니스 지표 분석, 대시보드 작성.",
        "defaultName": "data-scientist",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 데이터 사이언티스트다. 분석 요청 시:\n"
            "1. 먼저 데이터 shape/결측/이상치 요약.\n"
            "2. 가설 → 검정 방법 → 결과 → 해석 순으로 정리.\n"
            "3. 시각화는 핵심 지표 최대 3개까지.\n"
            "4. SQL 쿼리는 재현 가능하도록 완전 형태로 기록.\n"
        ),
    },
    {
        "id": "devops-sre", "icon": "⚙️", "label": "DevOps / SRE",
        "summary": "CI/CD, 인프라 자동화, 모니터링, 온콜 런북.",
        "defaultName": "devops-sre",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 DevOps/SRE 역할이다.\n\n"
            "1. 인프라 변경은 IaC(terraform/pulumi)로만, 콘솔 직접 변경 금지.\n"
            "2. 새 서비스는 health check + metrics endpoint 필수.\n"
            "3. 배포 파이프라인은 롤백 경로를 먼저 확인.\n"
            "4. 경보는 심각도 기준/런북 링크와 함께 정의.\n"
        ),
    },
    {
        "id": "security-reviewer", "icon": "🔒", "label": "보안 리뷰어",
        "summary": "OWASP 관점 코드 리뷰, 비밀 누출, 인증·인가, 의존성 취약점.",
        "defaultName": "security-reviewer",
        "tools": ["Read", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 보안 리뷰 전담이다. 변경 사항에서 다음을 점검:\n\n"
            "- 인증/인가 우회 가능성\n- SQL/Command Injection\n- SSRF / 경로 탈출\n"
            "- 하드코딩된 secrets\n- 안전하지 않은 crypto 사용\n- 신뢰 경계에서의 입력 검증 누락\n\n"
            "심각도(Critical/High/Medium/Low) 표시 후 PoC/재현 경로 포함해 보고.\n"
        ),
    },
    {
        "id": "qa-engineer", "icon": "🧪", "label": "QA 엔지니어",
        "summary": "테스트 설계, E2E 자동화, 회귀 방지, 품질 게이트.",
        "defaultName": "qa-engineer",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 QA 엔지니어다. 새 기능이 들어오면:\n"
            "1. 해피 패스 + 엣지 케이스 + 에러 경로 3종 테스트.\n"
            "2. Given-When-Then 주석으로 의도 명시.\n"
            "3. 외부 I/O 는 mock, 순수 로직은 단위 테스트.\n"
            "4. flaky 테스트는 격리 후 근본 원인 리포트.\n"
        ),
    },
    {
        "id": "architect", "icon": "🏛️", "label": "아키텍트",
        "summary": "상위 설계, 모듈 경계, 트레이드오프 분석, ADR 작성.",
        "defaultName": "architect",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 시스템 아키텍트다. 새 기능/리팩터링 제안이 오면:\n"
            "1. 기존 모듈 경계·의존 방향을 먼저 Grep 으로 파악.\n"
            "2. 2-3개 대안 비교: 장/단점/유지비용.\n"
            "3. 선택 근거와 함께 ADR 형식으로 요약.\n"
            "4. 변경이 큰 경우 단계별 마이그레이션 경로 제시.\n"
        ),
    },
    {
        "id": "code-reviewer", "icon": "🔍", "label": "코드 리뷰어",
        "summary": "변경된 코드의 정확성·가독성·유지보수성 점검.",
        "defaultName": "code-reviewer",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 코드 리뷰어다.\n\n"
            "체크리스트: 의도 명확성 / 네이밍 / 에러 처리 / 예외 경로 / 테스트 커버리지 / 리팩터 기회 / 문서 업데이트.\n"
            "각 지적은 severity (blocker/suggestion/nit) 명시.\n"
        ),
    },
    {
        "id": "db-expert", "icon": "🗄️", "label": "데이터베이스 전문가",
        "summary": "스키마 설계, 인덱싱, 쿼리 튜닝, 마이그레이션.",
        "defaultName": "db-expert",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 DB 전문가다.\n\n"
            "1. 새 쿼리는 EXPLAIN 으로 plan 확인 후 필요 시 인덱스 추가.\n"
            "2. 마이그레이션은 forward/backward 모두 테스트.\n"
            "3. 대량 변경은 락 시간 추정 후 배치로 분할.\n"
        ),
    },
    {
        "id": "performance", "icon": "⚡", "label": "성능 엔지니어",
        "summary": "프로파일링, 병목 분석, 알고리즘·메모리·IO 최적화.",
        "defaultName": "performance",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 성능 엔지니어다.\n\n"
            "1. 최적화 전에 먼저 벤치마크로 현재 값 측정.\n"
            "2. 병목 후보를 데이터로 증명한 뒤 수정.\n"
            "3. 수정 후 동일 조건 재측정 + 개선율 수치 제시.\n"
        ),
    },
    {
        "id": "mobile-dev", "icon": "📱", "label": "모바일 개발자",
        "summary": "iOS(SwiftUI) / Android(Kotlin) / Flutter 공통 패턴.",
        "defaultName": "mobile-dev",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob", "Bash"],
        "model": "inherit",
        "content": (
            "너는 모바일 개발자다.\n\n"
            "1. 네트워크 호출은 반드시 상태(idle/loading/error/success) 관리.\n"
            "2. 접근성: VoiceOver/TalkBack 레이블 / Dynamic Type / 컬러 대비.\n"
            "3. 오프라인 대비: 캐시 + 재시도.\n"
        ),
    },
    {
        "id": "tech-writer", "icon": "✍️", "label": "기술 문서 작성자",
        "summary": "API 레퍼런스, 온보딩 가이드, ADR, 릴리즈 노트.",
        "defaultName": "tech-writer",
        "tools": ["Read", "Edit", "Write", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 기술 문서 작성자다.\n\n"
            "독자 관점에서 '처음 오는 개발자가 30분 안에 돌릴 수 있는가' 를 기준.\n"
            "각 섹션은 예제 코드 + 실패 시 해결 팁 포함.\n"
        ),
    },
    {
        "id": "pm", "icon": "📋", "label": "프로젝트 매니저",
        "summary": "요구사항 분석, 스프린트 플래닝, 이슈 관리, 보고.",
        "defaultName": "pm",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 프로젝트 매니저다.\n\n"
            "새 요구사항이 오면:\n- 목적/성공기준/비기능요건을 먼저 추출\n- 관련 이슈/PR 을 검색해 중복·선행 조건 확인\n- 작업을 1-3일 크기로 쪼개 리스트화\n"
        ),
    },
    {
        "id": "ux-designer", "icon": "🎨", "label": "UX/UI 디자이너",
        "summary": "사용자 플로우, 정보구조, 마이크로인터랙션, 접근성.",
        "defaultName": "ux-designer",
        "tools": ["Read", "Grep", "Glob"],
        "model": "inherit",
        "content": (
            "너는 UX/UI 디자이너 역할이다. 변경이 UI 관련이면:\n"
            "- 3가지 대안 스케치 → 트레이드오프 비교\n- 상태별(empty/loading/error/success) 명시\n- 접근성 체크리스트 통과 여부 확인\n"
        ),
    },
]

def _resolve_cwd_input(cwd: str) -> Optional[str]:
    """cwd 문자열(절대경로 or 슬러그) → 실제 홈 하위 절대경로."""
    if not cwd:
        return None
    if not cwd.startswith("/") and not cwd.startswith("~"):
        cwd = _slug_to_cwd_map().get(cwd, cwd)
    abs_path = os.path.abspath(os.path.expanduser(cwd))
    home = str(Path.home())
    if not (abs_path == home or abs_path.startswith(home + os.sep)):
        return None
    if not Path(abs_path).is_dir():
        return None
    return abs_path


def api_agent_roles() -> dict:
    return {"roles": AGENT_ROLE_CATALOG}


def api_project_agents_list(query: dict) -> dict:
    cwd_in = (query.get("cwd", [""])[0] or "").strip()
    cwd = _resolve_cwd_input(cwd_in)
    if not cwd:
        return {"error": "cwd required"}
    agents_dir = Path(cwd) / ".claude" / "agents"
    if not agents_dir.exists():
        return {"cwd": cwd, "agents": [], "dirExists": False}
    out = []
    for p in sorted(agents_dir.glob("*.md")):
        raw = _safe_read(p)
        meta = _parse_frontmatter(raw)
        out.append({
            "id": p.stem,
            "name": meta.get("name", p.stem),
            "description": meta.get("description", ""),
            "model": meta.get("model", "inherit"),
            "tools": _parse_tools_field(meta.get("tools", "")),
            "path": str(p),
            "raw": raw,
            "content": _strip_frontmatter(raw),
        })
    return {"cwd": cwd, "agents": out, "dirExists": True}


def _build_role_md(role: dict, override_name: Optional[str] = None, override_desc: Optional[str] = None) -> str:
    name = (override_name or role["defaultName"]).strip()
    desc = (override_desc or role.get("summary", "")).strip()
    tools = role.get("tools") or []
    frontmatter = (
        f"---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        f"model: {role.get('model','inherit')}\n"
        f"tools: {', '.join(tools)}\n"
        f"---\n\n"
    )
    return frontmatter + role["content"]


def api_project_agent_add(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = _resolve_cwd_input(body.get("cwd", ""))
    if not cwd:
        return {"ok": False, "error": "cwd not resolvable or outside home"}
    role_id = body.get("roleId") or ""
    role = next((r for r in AGENT_ROLE_CATALOG if r["id"] == role_id), None)
    if not role:
        return {"ok": False, "error": f"unknown roleId: {role_id}"}
    name = (body.get("name") or role["defaultName"]).strip()
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,63}$", name):
        return {"ok": False, "error": "에이전트 이름은 소문자/숫자/-/_ 만 허용"}
    desc_override = body.get("description")
    target = Path(cwd) / ".claude" / "agents" / f"{name}.md"
    if target.exists() and not body.get("overwrite"):
        return {"ok": False, "error": f"이미 존재: {target.name} (overwrite=true 로 덮어쓰기)"}
    md = _build_role_md(role, override_name=name, override_desc=desc_override)
    ok = _safe_write(target, md)
    return {"ok": ok, "path": str(target), "name": name}


def api_project_agent_delete(body: dict) -> dict:
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = _resolve_cwd_input(body.get("cwd", ""))
    if not cwd:
        return {"ok": False, "error": "cwd not resolvable"}
    name = body.get("name") or ""
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return {"ok": False, "error": "invalid name"}
    target = Path(cwd) / ".claude" / "agents" / f"{name}.md"
    if not target.exists():
        return {"ok": False, "error": "not found"}
    try:
        target.unlink()
    except Exception as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True}


def api_project_agent_save(body: dict) -> dict:
    """raw 통째 저장 (기존 편집)."""
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    cwd = _resolve_cwd_input(body.get("cwd", ""))
    if not cwd:
        return {"ok": False, "error": "cwd not resolvable"}
    name = body.get("name") or ""
    raw = body.get("raw") or ""
    if not re.match(r"^[a-zA-Z0-9_-]+$", name):
        return {"ok": False, "error": "invalid name"}
    target = Path(cwd) / ".claude" / "agents" / f"{name}.md"
    ok = _safe_write(target, raw)
    return {"ok": ok, "path": str(target)}

SUBAGENT_MODEL_CHOICES = [
    {"id": "inherit",              "label": "inherit (메인 Claude 따라감)", "note": "세션의 메인 모델과 동일 — 기본값"},
    {"id": "haiku",                "label": "Haiku (가장 빠름/저렴)",       "note": "Haiku 4.5 alias"},
    {"id": "sonnet",               "label": "Sonnet (균형형)",              "note": "Sonnet 4.6 alias"},
    {"id": "opus",                 "label": "Opus (최강/느림)",             "note": "Opus 4.7 alias"},
    {"id": "claude-haiku-4-5",     "label": "claude-haiku-4-5 (핀)",        "note": "특정 버전 고정"},
    {"id": "claude-sonnet-4-6",    "label": "claude-sonnet-4-6 (핀)",       "note": "특정 버전 고정"},
    {"id": "claude-opus-4-7",      "label": "claude-opus-4-7 (핀)",         "note": "1M context"},
    {"id": "claude-opus-4-6",      "label": "claude-opus-4-6 (핀)",         "note": "Fast mode 기본"},
]

def api_subagent_model_choices() -> dict:
    return {"choices": SUBAGENT_MODEL_CHOICES}

def _patch_frontmatter_key(raw: str, key: str, value: str) -> str:
    """markdown frontmatter의 특정 키를 업서트 (---...--- 블록 없으면 생성)."""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw or "", re.DOTALL)
    if not m:
        # 새 frontmatter 추가
        return f"---\n{key}: {value}\n---\n\n{raw}"
    block = m.group(1)
    rest = raw[m.end():]
    lines = block.splitlines()
    replaced = False
    new_lines = []
    for line in lines:
        if re.match(rf"^\s*{re.escape(key)}\s*:", line):
            new_lines.append(f"{key}: {value}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"{key}: {value}")
    return f"---\n" + "\n".join(new_lines) + f"\n---\n" + rest


def api_subagent_set_model(body: dict) -> dict:
    """
    서브에이전트 파일의 frontmatter `model` 값만 패치.
    body: { scope: 'project'|'global'|'plugin', agentId: <...>, cwd?: <path for project>, model: <value> }
    """
    if not isinstance(body, dict):
        return {"ok": False, "error": "bad body"}
    scope = body.get("scope") or "project"
    agent_id = body.get("agentId") or ""
    model = body.get("model") or "inherit"
    if not isinstance(model, str) or len(model) > 80 or not re.match(r"^[a-zA-Z0-9_.-]+$", model):
        return {"ok": False, "error": "invalid model id"}

    if scope == "project":
        cwd = _resolve_cwd_input(body.get("cwd", ""))
        if not cwd:
            return {"ok": False, "error": "cwd required for project scope"}
        if not re.match(r"^[a-zA-Z0-9_-]+$", agent_id):
            return {"ok": False, "error": "invalid agent name"}
        target = Path(cwd) / ".claude" / "agents" / f"{agent_id}.md"
    elif scope == "global":
        if not re.match(r"^[a-zA-Z0-9_-]+$", agent_id):
            return {"ok": False, "error": "invalid agent name"}
        target = AGENTS_DIR / f"{agent_id}.md"
    elif scope == "plugin":
        p = _resolve_agent_path(agent_id)
        if not p:
            return {"ok": False, "error": "plugin agent path not resolvable"}
        target = p
    else:
        return {"ok": False, "error": "unknown scope"}

    if not target.exists():
        return {"ok": False, "error": f"not found: {target.name}"}

    raw = _safe_read(target)
    patched = _patch_frontmatter_key(raw, "model", model)
    ok = _safe_write(target, patched)
    return {"ok": ok, "model": model, "path": str(target)}


