"""合作合同业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.services.contract_settlement import settlement_conclusion
from app.store import store

MODULE = "contract2"
REQUIRED_FIELDS = ["合同编号", "签约双方", "合同类型"]
STATUS_ORDER = ["待签约", "执行中", "已到期", "已终止"]
ACTION_RULES = {"签约生效": "执行中", "到期提醒": "已到期", "终止合同": "已终止"}
NEGATIVE_ACTIONS = []


def _with_conclusion(row: dict[str, Any]) -> dict[str, Any]:
    """在返回拷贝上附加统一结算结论，存储里的原始合同数据保持不动。"""
    entry = dict(row)
    entry.update(settlement_conclusion(row))
    return entry


class Contract2Service:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("合同编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_with_conclusion(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return _with_conclusion(row) if row is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"运输合同 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于合作合同可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"运输合同已{action}"
