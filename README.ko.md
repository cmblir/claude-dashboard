# 🧭 Claude Control Center

> **멀티 AI 오케스트레이션 대시보드** — Claude, GPT, Gemini, Ollama, Codex를 하나의 인터페이스에서 관리하세요.

[![English](https://img.shields.io/badge/🇺🇸_English-blue)](./README.md) [![中文](https://img.shields.io/badge/🇨🇳_中文-red)](./README.zh.md)

`~/.claude/` 디렉토리 전체(에이전트, 스킬, 훅, 플러그인, MCP, 세션, 프로젝트)를 관리하고 **n8n 스타일 워크플로우 엔진**으로 멀티 AI 프로바이더 오케스트레이션을 제공하는 로컬 대시보드입니다.

> 로컬 전용, 외부 호출 없음 — Python 표준 라이브러리 서버 + 단일 HTML 파일.

---

## ✨ 핵심 기능

### 🧠 멀티 AI 프로바이더 오케스트레이션
- **8개 빌트인 프로바이더**: Claude CLI, Ollama, Gemini CLI, Codex + OpenAI API, Gemini API, Anthropic API, Ollama API
- **커스텀 CLI 프로바이더**: 임의의 CLI 도구를 AI 프로바이더로 등록
- **Capability 시스템**: chat / embed / code / vision / reasoning
- **폴백 체인**: 실패 시 다음 프로바이더로 자동 전환 (편집 가능)
- **Rate Limiter**: 프로바이더별 토큰 버킷 알고리즘
- **멀티 AI 비교**: 동일 프롬프트를 여러 AI에 동시 전송하여 결과 비교

### 🦙 Ollama 모델 허브 (Open WebUI 스타일)
- **23개 모델 카탈로그**: LLM / Code / Embedding / Vision 4개 카테고리
- **원클릭 다운로드** + 진행률 바 + 삭제 + 상세 정보
- **자동 시작**: 대시보드와 함께 `ollama serve` 자동 실행
- **엔진 설정**: 기본 채팅 모델 + 임베딩 모델 선택
- **Modelfile 편집**: 커스텀 모델 생성

### 🔀 워크플로우 엔진 (n8n 스타일)
- **16개 노드 타입**: start, session, subagent, aggregate, branch, output, http, transform, variable, subworkflow, embedding, loop, retry, error_handler, merge, delay
- **병렬 실행**: 같은 depth 노드를 ThreadPoolExecutor로 동시 실행
- **SSE 실시간 스트림**: 노드별 진행률 실시간 업데이트
- **Webhook 트리거**: 외부 HTTP로 워크플로우 실행 (`POST /api/workflows/webhook/{id}`)
- **Cron 스케줄러**: 자동 반복 실행
- **Export/Import**: JSON으로 워크플로우 공유
- **버전 히스토리**: 최근 20개 버전 보관 + 복원
- **빌트인 템플릿 8종**: 멀티 AI 비교, RAG 파이프라인, 코드 리뷰, 데이터 ETL, 재시도 워크플로우 등
- **인터랙티브 튜토리얼 18장면**: 단계별 사용법 가이드
- **캔버스 기능**: 미니맵, 노드 검색, Ctrl+C/V/Z, 키보드 단축키, 노드 그룹핑

### 📊 분석 & 모니터링
- **세션 스코어링** (0-100): 참여도, 생산성, 위임, 다양성, 안정성
- **비용 추적**: 프로바이더별 일별 비용 차트 + 스택 바
- **사용량 알림**: 일일 비용/토큰 임계치 초과 알림
- **프로바이더 헬스**: 실시간 상태 + 포트 정보
- **워크플로우 통계**: 성공률, 평균 소요시간, 프로바이더 분포

### 🌍 다국어 지원
- **3개 언어**: 한국어(ko), 영어(en), 중국어(zh)
- **2,893개 번역 키** (언어당)
- **동적 번역**: MutationObserver 기반 실시간 DOM 번역
- **error_key 시스템**: 백엔드 에러 메시지 다국어 지원

### 🎨 UX
- **5개 테마**: Dark, Light, Midnight, Forest, Sunset
- **모바일 반응형**: 사이드바 접기, 반응형 그리드
- **접근성**: ARIA 레이블, 포커스 트랩, 키보드 네비게이션
- **브라우저 알림**: 워크플로우 완료, 사용량 초과 알림
- **성능 최적화**: API 캐싱, 디바운스 렌더링, RAF 배치 처리

---

## 🚀 빠른 시작

```bash
# 클론
git clone https://github.com/cmblir/claude-dashboard.git
cd claude-dashboard

# 실행 (Python 3.10+ 필요, 의존성 없음)
python3 server.py

# 브라우저에서 열기
open http://localhost:8080
```

### 필수 조건
- **Python 3.10+** (표준 라이브러리만 사용, pip 설치 불필요)
- **Claude Code CLI** (`npm i -g @anthropic-ai/claude-code`)
- **Ollama** (선택, 로컬 LLM용) — 대시보드가 자동 시작

### 환경 변수
```bash
HOST=127.0.0.1          # 바인드 주소 (기본: 127.0.0.1)
PORT=8080               # 포트 (기본: 8080)
OLLAMA_HOST=http://localhost:11434  # Ollama 서버
OPENAI_API_KEY=sk-...   # OpenAI API (선택)
GEMINI_API_KEY=AIza...   # Gemini API (선택)
ANTHROPIC_API_KEY=sk-... # Anthropic API (선택)
```

---

## 📐 아키텍처

```
claude-dashboard/
├── server.py              # 엔트리포인트 (포트 충돌 자동 해결 + ollama 자동 시작)
├── server/
│   ├── ai_providers.py    # 8개 프로바이더 + CustomCliProvider + RateLimiter
│   ├── ai_keys.py         # API 키 관리 + 비용 추적 + 사용량 알림
│   ├── ollama_hub.py      # 모델 카탈로그 (23종) + pull/delete/create/serve
│   ├── workflows.py       # DAG 엔진 (16노드, 병렬, SSE, cron, webhook)
│   ├── errors.py          # i18n 에러 키 시스템 (49키)
│   ├── routes.py          # 138개 API 라우트 (GET 75 + POST 63)
│   ├── sessions.py        # 세션 인덱싱 + 스코어링
│   ├── nav_catalog.py     # 탭 카탈로그 + 다국어 설명
│   └── ...                # 총 20개 모듈
├── dist/
│   ├── index.html         # 단일 파일 프론트엔드 (~13,250줄)
│   └── locales/
│       ├── ko.json        # 2,893키
│       ├── en.json        # 2,893키
│       └── zh.json        # 2,893키
└── tools/                 # i18n 감사, 번역 스크립트
```

---

## 🔢 통계 (v2.1.0)

| 지표 | 값 |
|------|-----|
| 노드 타입 | 16개 |
| AI 프로바이더 | 8 빌트인 + 커스텀 무제한 |
| API 라우트 | 138 (GET 75 + POST 63) |
| i18n 키 | 2,893 × 3개 언어 |
| Ollama 카탈로그 | 23개 모델 |
| 빌트인 템플릿 | 8종 |
| 테마 | 5종 |
| 튜토리얼 장면 | 18개 |

---

## 📝 라이선스

MIT

---

## 🤝 기여

이슈와 PR은 [github.com/cmblir/claude-dashboard](https://github.com/cmblir/claude-dashboard)에서 환영합니다.
