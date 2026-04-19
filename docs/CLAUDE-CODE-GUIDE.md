# 📘 Claude Code 로 이 대시보드 쓰기 / 확장하기

이 문서는 **Claude Code 사용자** 가 이 대시보드 템플릿을 자기 환경에서 쓰고, 필요하면 새 카드 / endpoint / 데이터 소스를 직접 추가하는 방법을 설명합니다.

> **전제**: 이 폴더 안에는 빌드된 `dist/` 와 단일 파일 `server.py` 만 있습니다. **원본 React 소스는 없습니다.** 모든 확장은 (a) `server.py` 백엔드 추가, (b) 미니파이된 `dist/assets/index-DYwNDC3K.js` 직접 패치, (c) `dist/index.html` CSS 오버라이드 — 이 세 가지로 합니다.

---

## 0. 기본 사용 (작업 시작)

### Claude Code 에서 폴더 열기

```bash
cd ~/Desktop/claude-workspace-dashboard-template
claude
```

또는 Anti-Gravity / VSCode 확장에서 이 폴더를 작업 폴더로 열기.

### 대시보드 켜기

```bash
./start.sh
# 또는
python3 server.py
```

브라우저: **http://localhost:8080**

이제 화면 보면서 작업하면 됨. 데이터는 30 초마다 자동 갱신 (브리핑 탭).

---

## 1. 자주 쓰는 작업 패턴

### A. 새 에이전트를 추가했는데 화면에 한글로 안 떠

1. `~/.claude/agents/<your-agent>.md` 만들기
2. 화면 새로고침 → 영어 이름으로 보임
3. 한글 라벨 추가하려면 `dist/assets/index-DYwNDC3K.js` 안의 `Fl=` dict 에 매핑 추가:

Claude Code 에 이렇게 요청:
> `dist/assets/index-DYwNDC3K.js` 파일에서 `Fl={architect:"아키텍트"...}` 패턴 찾아서, 그 dict 에 `"<your-agent>":"한글이름"` 항목 추가해줘. 그리고 `node -c dist/assets/index-DYwNDC3K.js` 로 syntax 검증해줘.

### B. 새 스킬 한글 매핑

같은 패턴 — `dist/assets/index-DYwNDC3K.js` 의 `bn=` dict 에 추가:

> `bn={brainstorming:"브레인스토밍"...}` 패턴 찾아서 `"<your-skill>":"한글이름"` 항목 추가해줘.

### C. 새 카드 / 새 endpoint 추가

화면에 새 데이터를 보여주고 싶으면 두 단계:

**1) 백엔드: server.py 에 endpoint 추가**

```python
def get_my_thing() -> dict:
    """예: ~/.claude/my-data.json 읽어 응답."""
    p = Path.home() / ".claude" / "my-data.json"
    if not p.exists():
        return {"items": []}
    try:
        return {"items": json.loads(_safe_read(p))}
    except Exception:
        return {"items": []}

# ROUTES_GET 에 등록
ROUTES_GET = {
    ...
    "/api/my-thing": get_my_thing,
}
```

**2) 화면: 미니파이 JS 패치**

이 방식은 권장 안 함 (어렵고 깨지기 쉬움). 대신 **기존 카드의 데이터 소스를 우리 새 endpoint 로 교체** 하는 게 현실적:

> server.py 에 새 endpoint `/api/my-thing` 만들고, 화면의 "예약된 작업" 카드가 그걸 사용하도록 `/api/briefing/schedule` 응답에 우리 데이터를 끼워넣어줘.

### D. UI 시각 폴리시 변경

`dist/index.html` 의 `<style>` 블록만 수정. React inline-style 이라 모든 룰에 `!important` 필요. attribute selector 사용:

```css
div[style*="rgb(24, 24, 27)"] {
  border-color: #ff00aa !important;
}
```

Claude Code 에 요청:
> `dist/index.html` 의 `<style>` 블록에 카드 hover 색상을 핑크로 바꾸는 룰 추가해줘.

### E. 폴더 버튼 클릭 시 다른 동작

`server.py` 의 `open_folder_action` 함수 수정. 예를 들어 Finder 대신 VSCode 로 열기:

```python
subprocess.Popen(["code", abs_path], ...)  # macOS Spotlight 에 등록된 code 명령
```

---

## 2. 흔한 함정 + 안전 룰

### 🛑 절대 하면 안 되는 것

- **`dist/index.html`, `dist/assets/index-DYwNDC3K.js` 통째로 덮어쓰지 말기** — 우리 한글 매핑 + CSS 폴리시 패치가 사라짐
- **`server.py` 의 read-only mock 동작 함부로 풀지 말기** — PUT/POST/DELETE 가 진짜로 ~/.claude 를 수정하면 의도치 않은 사고 가능
- **8080 외 포트 변경 시** — `start.sh` 와 `server.py` 의 `port = 8080` 둘 다 바꿔야 함

### ✅ 안전한 패턴

- 백엔드 변경: `server.py` 만 수정 (단일 파일이라 diff 추적 쉬움)
- 시각 변경: `dist/index.html` 의 `<style>` 블록만 수정
- 영어→한글: `dist/assets/index-DYwNDC3K.js` 의 `Fl` / `bn` dict 만 패치 (sed-friendly)
- 변경 후 항상 `node -c dist/assets/index-DYwNDC3K.js` 로 syntax 검증
- 변경 후 항상 `python3 -c "import server"` 로 server.py 검증

### 🔧 디버깅

화면이 깨지면:

```bash
# 1. 백엔드 살아있는지
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/

# 2. 모든 endpoint 응답 확인
for ep in claude-md system/status skills agents hooks plugins connectors projects \
          briefing/overview briefing/devices briefing/activity briefing/schedule \
          briefing/projects-summary briefing/pending-approvals guide/recommended-settings; do
  curl -s -o /dev/null -w "%{http_code}  /api/$ep\n" http://localhost:8080/api/$ep
done

# 3. 브라우저 콘솔 에러 확인
# DevTools → Console
```

Claude Code 에 다음과 같이 요청:
> 8080 살아있는지 확인하고, 모든 API endpoint 의 HTTP 응답 코드 + 사이즈를 표로 보여줘.

---

## 3. Claude Code 슬래시 커맨드 활용

### 자주 쓰는 커맨드

- `/build-fix` — 빌드 / syntax 에러 자동 수정
- `/simplify` — 코드 단순화
- `/code-review` — 변경 사항 리뷰
- `/commit` — 커밋 생성

### 예시 워크플로우

새 카드 추가 → 검증 → 커밋:

```
/plan 새 "최근 방문 프로젝트 Top 10" 카드 추가하려고 해.
      ~/.claude/history.jsonl 에서 가장 자주 등장한 프로젝트 10개를
      /api/briefing/top-projects 라는 새 endpoint 로 만들고,
      화면의 "최근 프로젝트 작업 요약" 카드를 그걸 사용하도록 변경.
```

플랜 승인 후:

```
이제 적용해줘. 적용 후 curl 로 endpoint 검증하고 화면에서 동작 확인.
```

검증 후:

```
/commit
```

---

## 4. 데이터 소스 추가 가이드

### ~/.claude/ 외부 데이터를 보고 싶다면

`server.py` 에 새 함수 작성. 예: `~/Desktop/projects-status.json` 읽기:

```python
EXTERNAL_DATA = Path.home() / "Desktop" / "projects-status.json"

def get_external_status() -> dict:
    if not EXTERNAL_DATA.exists():
        return {}
    try:
        return json.loads(_safe_read(EXTERNAL_DATA))
    except Exception:
        return {}

ROUTES_GET["/api/external/status"] = get_external_status
```

### 보안 고려

외부 파일 읽을 때:
- **사용자 홈 디렉토리 안만 허용** (path traversal 차단)
- 큰 파일은 `_safe_read(path, limit=10000)` 처럼 limit
- JSON parse 실패 → silent fail (`{}` 반환)

---

## 5. 주요 endpoint 리스트 (현재 16개)

| Endpoint | 데이터 소스 | 응답 형태 |
|---|---|---|
| `GET /api/claude-md` | `~/.claude/CLAUDE.md` | `{sections, raw}` |
| `GET /api/system/status` | `settings.json` + `sessions/*.json` | `{hooks, permissions, sessions, settings}` |
| `GET /api/skills` | `~/.claude/skills/*` | array |
| `GET /api/agents` | `~/.claude/agents/*.md` | `{agents:[...]}` |
| `GET /api/hooks` | `settings.json hooks` | `{hooks, permissions}` |
| `GET /api/plugins` | `installed_plugins.json` | array |
| `GET /api/connectors` | `~/.claude.json mcpServers` | `{platform, local}` |
| `GET /api/projects` | `~/.claude/projects/*` | `{projects:[...]}` |
| `GET /api/settings` | `settings.json` | dict |
| `GET /api/briefing/overview` | history + sessions + tasks + projects | counts |
| `GET /api/briefing/devices` | `history.jsonl` (cwd 기반 분류) | `{devices:[...]}` |
| `GET /api/briefing/activity` | `history.jsonl` (오늘 timestamp filter) | `{today}` |
| `GET /api/briefing/schedule` | `scheduled-tasks/` + `tasks/` | `{scheduled, tasks}` |
| `GET /api/briefing/projects-summary` | `history.jsonl` (per project) | `{summaries}` |
| `GET /api/briefing/pending-approvals` | `projects/*/{sessionId}.jsonl` 마지막 tool_use | `{pending}` |
| `GET /api/guide/recommended-settings` | 정적 4개 프로필 | `{profiles}` |
| `POST /api/open-folder` | macOS `open` 명령 | `{ok, path}` |

PUT / POST / DELETE 의 다른 경로는 모두 read-only mock (200 OK).

---

## 6. 자주 묻는 것 (FAQ)

**Q. 진짜로 ~/.claude 를 편집하고 싶다.**
A. `server.py` 의 `do_PUT` / `do_POST` / `do_DELETE` 를 수정해서 실제 파일 write 하도록. 단 안전 가드 (path 검증, backup 생성 등) 반드시 추가. 예제는 `open_folder_action` 함수 참고 (path traversal 차단 패턴).

**Q. 다른 디바이스의 ~/.claude 도 보고 싶다.**
A. Syncthing 으로 `~/.claude` 동기화 + `.stignore` 에서 `/sessions`, `history.jsonl` 제외 풀기. 단 충돌 위험 있음.

**Q. 다크 테마 말고 라이트 테마.**
A. `dist/index.html` 의 `<style>` 블록에 light mode 변수 추가 + `body { background: white; color: #0f172a; }` . React inline style 이 우선이라 모든 카드를 잡으려면 attribute selector + `!important` 많이 필요.

**Q. 모바일에서 보고 싶다.**
A. `python3 server.py` 가 `127.0.0.1` 만 listen. `server.py` 의 `HTTPServer(("127.0.0.1", port), ...)` → `("0.0.0.0", port)` 로 변경 후 같은 네트워크 모바일 브라우저에서 `http://<맥-ip>:8080`. **CAUTION**: 같은 네트워크의 다른 사람도 접근 가능 — 신뢰할 수 있는 네트워크에서만.

**Q. HTTPS 가 필요하다.**
A. nginx / caddy 로 reverse proxy 하거나, Python `http.server.SimpleHTTPRequestHandler` 대신 `http.server` + `ssl.wrap_socket`. 로컬 사용엔 보통 불필요.

---

## 7. 트러블 발생 시 Claude Code 한 줄 명령

| 상황 | 명령 |
|---|---|
| 카드 빈 상태 | `브라우저 열어서 콘솔 에러 보고 어떤 endpoint 에서 깨졌는지 알려줘` |
| 한글 안 뜸 | `dist/assets/index-DYwNDC3K.js 의 Fl dict 에 빠진 매핑 추가해줘` |
| 새 카드 | `~/.claude/<폴더> 데이터를 보여주는 새 카드 추가해줘. 우선 데이터 구조 파악부터` |
| 폴더 버튼 안 됨 | `server.py 의 open_folder_action 디버그해줘` |
| 권한 표시 잘못 | `~/.claude/settings.json 의 permissions 와 우리 응답 비교해줘` |
| 빌드 검증 | `/build-fix` |

---

**끝**. 즐거운 워크스페이스 정리 되기를 🎯
