"""将 PostHog 原始结果统一化为 Metrics dict。"""

from __future__ import annotations

from datetime import date
from typing import Any

# 统一输出结构
Metrics = dict[str, Any]


def to_metrics(raw: dict, *, label_map: dict[str, str] | None = None) -> Metrics:
    """将 trends insight 结果转为统一 Metrics。

    label_map: 可选，把 insight 里的 series label 映射为中文显示名。
    """
    report_date = date.today().isoformat()
    items: list[dict] = []

    result_series = raw.get("result", [])
    for series in result_series:
        key = series.get("action", {}).get("id", series.get("label", "unknown"))
        label = series.get("label", str(key))
        if label_map and label in label_map:
            label = label_map[label]

        data = series.get("data", [])
        value = data[-1] if data else 0
        prev = data[-2] if len(data) >= 2 else None

        items.append({"key": str(key), "label": label, "value": value, "prev": prev})

    return {"report_date": report_date, "items": items}


def hogql_rows_to_dict(rows: list[list], columns: list[str]) -> list[dict]:
    """将 HogQL 行列结果转为 dict 列表。"""
    return [dict(zip(columns, row)) for row in rows]
