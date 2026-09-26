"""合作合同结算口径与续签判断的统一实现。"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import re
from typing import Any

from app.store import store

CONTRACT_MODULE = "contract2"
CONCLUSION_FIELD = "结算结论"
MATCH_FIELDS = ("合同编号", "关联任务", "凭证编号")
RENEWAL_SOON_DAYS = 30

_EXPIRY_RE = re.compile(
    r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*(?:[-/.月]\s*(\d{1,2})\s*日?)?"
)
_DURATION_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(年|个月|月|日|天)"
)


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _date_from_parts(year: str, month: str, day: str | None) -> date | None:
    try:
        return date(int(year), int(month), int(day or 1))
    except ValueError:
        return None


def parse_contract_term(term: Any, signed_at: Any = None) -> date | None:
    """把合同期限解析成到期日；无法识别时返回 None。"""
    raw = _text(term)
    if not raw:
        return None

    matches = list(_EXPIRY_RE.finditer(raw))
    if matches:
        match = matches[-1]
        return _date_from_parts(match.group(1), match.group(2), match.group(3))

    duration = _DURATION_RE.search(raw)
    if duration:
        start_text = _text(signed_at)
        start_date = None
        if start_text:
            start_match = _EXPIRY_RE.search(start_text)
            if start_match:
                start_date = _date_from_parts(
                    start_match.group(1), start_match.group(2), start_match.group(3)
                )
        if start_date is None:
            start_date = date.today()

        amount = float(duration.group(1))
        unit = duration.group(2)
        if unit == "年":
            year = start_date.year + int(amount)
            remainder = amount - int(amount)
            month = start_date.month + round(remainder * 12)
            while month > 12:
                year += 1
                month -= 12
            try:
                return date(year, month, start_date.day)
            except ValueError:
                return date(year, month + 1, 1) - timedelta(days=1)
        if unit in ("个月", "月"):
            total_months = start_date.year * 12 + start_date.month - 1 + int(round(amount))
            year, month = divmod(total_months, 12)
            month += 1
            try:
                return date(year, month, start_date.day)
            except ValueError:
                return date(year, month + 1, 1) - timedelta(days=1)
        return start_date + timedelta(days=int(round(amount)))

    return None


def parse_fee_standard(value: Any) -> float | None:
    """保留合同原费用标准的数值口径，字符串里的数字也按同一规则解析。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"-?\d+(?:\.\d+)?", _text(value).replace(",", ""))
    return float(match.group(0)) if match else None


def find_contract(contract_no: Any) -> dict[str, Any] | None:
    """按合同编号查合作合同，不改变仓库里的原数据。"""
    target = _text(contract_no)
    if not target:
        return None
    for contract in store.rows(CONTRACT_MODULE):
        if _text(contract.get("合同编号")) == target:
            return contract
    return None


def resolve_contract_no(source: dict[str, Any], values: dict[str, Any] | None = None) -> str:
    """统一费用录入记录与本次提交里的合同编号来源。"""
    candidates: list[Any] = []
    if values:
        candidates.extend(values.get(field) for field in MATCH_FIELDS)
    candidates.extend(source.get(field) for field in MATCH_FIELDS)

    for candidate in candidates:
        text = _text(candidate)
        if text and find_contract(text) is not None:
            return text
    return ""


def evaluate_contract(contract: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """按合同费用标准和合同期限，一次算出费用结算与续签结论。"""
    today = today or date.today()
    contract_no = _text(contract.get("合同编号"))
    raw_fee_standard = contract.get("费用标准")
    fee_standard = parse_fee_standard(raw_fee_standard)
    expiry_date = parse_contract_term(contract.get("合同期限"), contract.get("签约日期"))

    if expiry_date is None:
        renewable = False
        days_to_expiry: int | None = None
        renewal_status = "合同期限不明确，暂不能续签"
    else:
        days_to_expiry = (expiry_date - today).days
        renewable = days_to_expiry >= 0
        if days_to_expiry < 0:
            renewal_status = "已超过合同期限，不能续签"
        elif days_to_expiry <= RENEWAL_SOON_DAYS:
            renewal_status = "合同即将到期，可续签"
        else:
            renewal_status = "合同有效期内，可续签"

    if fee_standard is None:
        settlement_status = "费用标准缺失，暂不能按合同结算"
    else:
        settlement_status = "按合同费用标准结算"

    return {
        "合同编号": contract_no,
        "费用标准": raw_fee_standard,
        "结算口径": raw_fee_standard if fee_standard is not None else None,
        "费用标准数值": fee_standard,
        "合同到期日": expiry_date.isoformat() if expiry_date else None,
        "距到期天数": days_to_expiry,
        "是否可续签": renewable,
        "续签判断": renewal_status,
        "结算判断": settlement_status,
    }


def evaluate_contract_no(
    contract_no: Any, *, today: date | None = None
) -> dict[str, Any] | None:
    contract = find_contract(contract_no)
    return evaluate_contract(contract, today=today) if contract is not None else None


def with_contract_conclusion(
    entry: dict[str, Any],
    *,
    values: dict[str, Any] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """给接口返回值追加统一结论；原页面已有字段保持不变。"""
    result = deepcopy(entry)
    contract_no = resolve_contract_no(entry, values)
    if not contract_no:
        return result
    conclusion = evaluate_contract_no(contract_no, today=today)
    if conclusion is not None:
        result[CONCLUSION_FIELD] = conclusion
    return result
