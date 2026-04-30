"""v2.54.0 — housekeeping panel UI strings.

Korean source -> English / Chinese for the new disk-usage / prune card
embedded inside the backup-restore tab. Loaded by
``tools/translations_manual.py`` and emitted into ``dist/locales/{en,zh}.json``
by the build pipeline.
"""
from __future__ import annotations

NEW_EN: dict[str, str] = {
    "정리": "Cleanup",
    "오래된 백업 정리": "Prune old backups",
    "유휴 AR 바인딩 정리": "Prune idle AR bindings",
    "디스크 사용량": "Disk usage",
    "디스크 사용량 불러오는 중…": "Loading disk usage…",
    "디스크 사용량 불러오기 실패": "Failed to load disk usage",
    "보관 기간 (일)": "Retention (days)",
    "최근 N개 보존": "Keep latest N",
    "미리보기": "Preview",
    "미리보기 실패": "Preview failed",
    "확정": "Confirm",
    "확정하시겠습니까?": "Proceed?",
    "정리 완료": "Cleanup complete",
    "정리 실패": "Cleanup failed",
    "정리할 백업 없음": "No backups to prune",
    "정리할 AR 바인딩 없음": "No idle AR bindings to prune",
    "항목 삭제 예정": "items will be deleted",
    "항목": "items",
    "대시보드 데이터": "Dashboard data",
    "AR 바인딩": "AR bindings",
}

NEW_ZH: dict[str, str] = {
    "정리": "清理",
    "오래된 백업 정리": "清理旧备份",
    "유휴 AR 바인딩 정리": "清理闲置 AR 绑定",
    "디스크 사용량": "磁盘使用量",
    "디스크 사용량 불러오는 중…": "正在加载磁盘使用量…",
    "디스크 사용량 불러오기 실패": "加载磁盘使用量失败",
    "보관 기간 (일)": "保留期 (天)",
    "최근 N개 보존": "保留最近 N 个",
    "미리보기": "预览",
    "미리보기 실패": "预览失败",
    "확정": "确认",
    "확정하시겠습니까?": "是否继续？",
    "정리 완료": "清理完成",
    "정리 실패": "清理失败",
    "정리할 백업 없음": "无需清理的备份",
    "정리할 AR 바인딩 없음": "无需清理的 AR 绑定",
    "항목 삭제 예정": "项将被删除",
    "항목": "项",
    "대시보드 데이터": "仪表盘数据",
    "AR 바인딩": "AR 绑定",
}
