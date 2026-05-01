# Autonomous queue — 2026-05-02 (cycle 14+: lazyclaw rename + UI/UX consistency)

User: "openclaw → lazyclaw로 변경. UI UX 다른 것들 모두 수정. 큐형태로 자율 진행. 전체 승인."
Direct to main. Continuous push per phase batch.

## N — openclaw → lazyclaw rename
- [N1] MODE_TABS key + UI labels (header dropdown, nav desc, mode badges)
- [N2] localStorage migration (cc.mode openclaw → lazyclaw)
- [N3] server/nav_catalog.py keyword + desc updates
- [N4] README + CHANGELOG + ADR references
- [N5] tools/translations_manual_*.py updates
- [N6] Commit + push

## O — Auth status email redaction
- [O1] Mask `Claude Team · <email>` panel by default — show domain only
- [O2] Toggle to reveal full email
- [O3] Commit + push

## P — UI/UX consistency baseline
- [P1] Add unified `.lc-card`, `.lc-section-title`, `.lc-meta-row`,
  `.lc-empty`, `.lc-loading`, `.lc-error` CSS utility classes
- [P2] Apply to recently-built tabs (Orchestrator, Ralph, AR, System)
- [P3] Apply to high-traffic tabs (Overview, Projects, Sessions)
- [P4] Commit + push

## Q — Empty-state + loading helper
- [Q1] Add `_emptyState(msg)` + `_loadingState(msg)` JS helpers
- [Q2] Refactor 5+ tabs to use them
- [Q3] Commit + push

## R — Sidebar polish
- [R1] Smoother collapse animation
- [R2] Active-tab indicator
- [R3] Commit + push

(Cycles continue per autonomous mandate.)
