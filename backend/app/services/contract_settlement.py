"""合作合同结算口径与续签判断：全系统只保留这一份实现。

合同列表、合同详情、费用录入三处都通过 settlement_conclusion 拿结论，
判断只依赖合同登记的费用标准与合同期限，任何地方不得再各自编写一套。
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any


def _parse_deadline(raw: Any) -> date | None:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_fee(raw: Any) -> float | None:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def settlement_conclusion(contract: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """按费用标准与合同期限统一算结算口径与续签结论。

    返回字段：
    - 合同到期：合同期限是否已过（期限缺失时为 None）
    - 结算费用标准：期限内为合同登记的费用标准；已到期则为 None，需续签后重新约定
    - 结算口径：给合同列表、合同详情、费用录入共用的文字结论
    - 可续签：合同已到期、可以走续签
    """
    today = today or date.today()
    fee = _parse_fee(contract.get("费用标准"))
    deadline = _parse_deadline(contract.get("合同期限"))
    if deadline is None:
        return {
            "合同到期": None,
            "结算费用标准": None,
            "结算口径": "合同期限缺失或无法识别，需补全后再结算",
            "可续签": False,
        }
    if deadline < today:
        return {
            "合同到期": True,
            "结算费用标准": None,
            "结算口径": "合同已到期，原费用标准不再用于新结算，续签后按新约定执行",
            "可续签": True,
        }
    if fee is None:
        return {
            "合同到期": False,
            "结算费用标准": None,
            "结算口径": "合同在期限内，但费用标准缺失，需补全后再结算",
            "可续签": False,
        }
    return {
        "合同到期": False,
        "结算费用标准": fee,
        "结算口径": "合同在期限内，按合同登记的费用标准结算",
        "可续签": False,
    }
