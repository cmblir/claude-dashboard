# Autonomous queue — 2026-05-02 (cycle 14+: lazyclaw rename + UI/UX consistency)

User: "openclaw → lazyclaw로 변경. UI UX 다른 것들 모두 수정. 큐형태로 자율 진행. 전체 승인."
Direct to main. Continuous push per phase batch.

## N — openclaw → lazyclaw rename ✅ DONE (v2.66.0 + v2.67.0)
- [x] [N1] MODE_TABS key + UI labels (header dropdown, nav desc, mode badges) — badge key k:'L' fixed in v2.67.0
- [x] [N2] localStorage migration (cc.mode openclaw → lazyclaw)
- [x] [N3] server/nav_catalog.py keyword + desc updates
- [x] [N4] README + CHANGELOG + ADR references
- [x] [N5] tools/translations_manual_*.py updates (manual_42 added for i18n residues)
- [x] [N6] Commit + push → feat/v2.67-lazyclaw-badge-key

## O — Auth status email redaction ✅ DONE (v2.66.1)
- [x] [O1] Mask `Claude Team · <email>` panel by default — show domain only
- [x] [O2] Toggle to reveal full email
- [x] [O3] Commit + push

## P — UI/UX consistency baseline ✅ DONE (v2.66.2)
- [x] [P1] Add unified `.lc-card`, `.lc-section-title`, `.lc-meta-row`, `.lc-empty`, `.lc-loading`, `.lc-error` CSS utility classes
- [x] [P2] Apply to recently-built tabs (Orchestrator, Ralph, AR, System)
- [x] [P3] Apply to high-traffic tabs (Overview, Projects, Sessions)
- [x] [P4] Commit + push

## Q — Empty-state + loading helper ✅ DONE (v2.66.3)
- [x] [Q1] Add `_emptyState(msg)` + `_loadingState(msg)` JS helpers
- [x] [Q2] Refactor 5+ tabs to use them
- [x] [Q3] Commit + push

## R — Sidebar polish ✅ DONE (v2.66.4)
- [x] [R1] Smoother collapse animation
- [x] [R2] Active-tab indicator
- [x] [R3] Commit + push

(Cycles continue per autonomous mandate.)
