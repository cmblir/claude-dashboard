"""v2.50.0 — Workflow telemetry + cost-recommendations panel strings.

Imported by translations_manual.py.

Covers user-visible strings introduced by:
  - 실행 텔레메트리 panel inside VIEWS.workflows
  - 비용 절감 추천 panel inside VIEWS.costsTimeline
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    # cost-recommendations panel
    "비용 절감 추천": "Cost-saving recommendations",
    "추천 새로고침": "Refresh recommendations",
    "예상 절감": "Estimated savings",
    "Haiku 전환": "Switch to Haiku",
    "프롬프트 캐싱": "Prompt caching",
    "로컬 모델": "Local model",
    "모델 업그레이드": "Model upgrade",
    "일 총": "day total",
    # telemetry panel (existing block follows)
    "실행 텔레메트리": "Execution telemetry",
    "최근 실행 건강 상태 (성공률 · p50/p95/p99 · 비용)": "Recent execution health (success rate · p50/p95/p99 · cost)",
    "기간": "Window",
    "1시간": "1 hour",
    "24시간": "24 hours",
    "7일": "7 days",
    "30일": "30 days",
    "전체 실행": "Total runs",
    "전체 성공률": "Overall success rate",
    "p50 (초)": "p50 (sec)",
    "p95 (초)": "p95 (sec)",
    "p99 (초)": "p99 (sec)",
    "워크플로우": "Workflow",
    "총 실행": "Total",
    "성공": "Success",
    "실패 수": "Failed",
    "취소 수": "Cancelled",
    "성공률 %": "Success %",
    "비용 (USD)": "Cost (USD)",
    "텔레메트리 데이터를 불러올 수 없습니다": "Could not load telemetry data",
    "최근 기간 내 실행 기록이 없습니다": "No runs in the selected window",
    "기타 (집계)": "Others (aggregated)",
}

NEW_ZH: dict[str, str] = {
    # cost-recommendations panel
    "비용 절감 추천": "成本优化建议",
    "추천 새로고침": "刷新建议",
    "예상 절감": "预估节省",
    "Haiku 전환": "切换到 Haiku",
    "프롬프트 캐싱": "提示词缓存",
    "로컬 모델": "本地模型",
    "모델 업그레이드": "模型升级",
    "일 총": "日合计",
    # telemetry panel
    "실행 텔레메트리": "执行遥测",
    "최근 실행 건강 상태 (성공률 · p50/p95/p99 · 비용)": "近期执行健康状态（成功率 · p50/p95/p99 · 费用）",
    "기간": "时段",
    "1시간": "1 小时",
    "24시간": "24 小时",
    "7일": "7 天",
    "30일": "30 天",
    "전체 실행": "总执行",
    "전체 성공률": "整体成功率",
    "p50 (초)": "p50 (秒)",
    "p95 (초)": "p95 (秒)",
    "p99 (초)": "p99 (秒)",
    "워크플로우": "工作流",
    "총 실행": "总计",
    "성공": "成功",
    "실패 수": "失败",
    "취소 수": "已取消",
    "성공률 %": "成功率 %",
    "비용 (USD)": "费用 (USD)",
    "텔레메트리 데이터를 불러올 수 없습니다": "无法加载遥测数据",
    "최근 기간 내 실행 기록이 없습니다": "所选时段内无执行记录",
    "기타 (집계)": "其他（汇总）",
}
