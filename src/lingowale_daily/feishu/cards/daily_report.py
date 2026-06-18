"""日报/周报卡片构建器 — 增长运营卡片。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from lingowale_daily.feishu.cards import register
from lingowale_daily.posthog.normalize import Metrics

# 中文名映射
_METRIC_LABELS = {
    "new_devices": "新激活设备",
    "new_signups": "新注册用户",
    "active_devices": "活跃设备(DAU)",
    "active_users": "活跃用户",
}

_VALUE_KEYS = {
    "new_devices": "new_devices",
    "new_signups": "new_signups",
    "active_devices": "dau",
    "active_users": "active_users",
}


class DailyReportCard:
    name = "daily_report"

    def build(self, data: Metrics, note: str | None) -> tuple[str, dict]:
        """返回 ('__raw__', card_json_dict)。"""
        report_type = data.get("report_type", "daily")
        title = "语鲸增长日报" if report_type == "daily" else "语鲸增长周报"
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

        elements: list[dict] = []

        # ── 模块 1: 增长指标 ──
        elements.append(_section_header("一、增长指标"))
        elements.append({"tag": "markdown", "content": f"T-1（{yesterday}）核心数据"})
        elements.append(_north_star_kpi_grid(data.get("north_star", {})))

        # 激活设备组成
        ad_activated = data.get("ad_activated_yesterday", 0)
        north_star = data.get("north_star", {})
        new_devices_rows = north_star.get("new_devices", [])
        total_new = 0
        if len(new_devices_rows) >= 2:
            total_new = int(new_devices_rows[-2].get("new_devices", 0) or 0)
        organic = total_new - ad_activated
        if total_new > 0:
            elements.append({"tag": "markdown", "content": f"激活组成：自然 **{organic}** + 投放 **{ad_activated}** = {total_new}"})

        # 厂商分布饼图
        manufacturer_dist = data.get("manufacturer_dist", [])
        if manufacturer_dist:
            elements.append(_manufacturer_pie(manufacturer_dist))

        # ── 模块 2: 留存 ──
        retention = data.get("retention", [])
        if retention:
            elements.append({"tag": "hr"})
            elements.append(_section_header("二、设备留存"))
            elements.append({"tag": "markdown", "content": "首次激活设备留存率（最近8天队列）"})
            elements.append(_retention_table(retention))

        # ── AI 点评 ──
        if note:
            elements.append({"tag": "hr"})
            elements.append(_section_header("三、值得关注"))
            elements.append({
                "tag": "div",
                "text": {"tag": "plain_text", "content": note},
            })

        card = {
            "schema": "2.0",
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": f"{title} | {yesterday}"},
            },
            "body": {"elements": elements},
        }
        return "__raw__", card


def _section_header(title: str) -> dict:
    return {
        "tag": "markdown",
        "content": f"**{title}**",
    }


def _north_star_chart(north_star: dict[str, list[dict]]) -> dict:
    """多系列折线图：4 条指标趋势合并在一个图里。"""
    values: list[dict] = []
    for metric_key, label in _METRIC_LABELS.items():
        rows = north_star.get(metric_key, [])
        value_key = _VALUE_KEYS[metric_key]
        for row in rows:
            day = str(row.get("day", ""))
            if len(day) > 5:
                day = day[5:]  # "2026-06-17" → "06-17"
            val = row.get(value_key, 0)
            values.append({"date": day, "value": int(val) if val else 0, "type": label})

    chart_spec: dict[str, Any] = {
        "type": "line",
        "data": {"values": values},
        "xField": "date",
        "yField": "value",
        "seriesField": "type",
        "legends": {"visible": True, "orient": "bottom"},
        "point": {"visible": False},
        "line": {"style": {"lineWidth": 2}},
    }
    return {
        "tag": "chart",
        "aspect_ratio": "16:9",
        "chart_spec": chart_spec,
    }


def _north_star_kpi_grid(north_star: dict[str, list[dict]]) -> dict:
    """北极星指标 KPI 网格 — 用 column_set 做大数字展示。"""
    columns: list[dict] = []
    for metric_key, label in _METRIC_LABELS.items():
        rows = north_star.get(metric_key, [])
        value_key = _VALUE_KEYS[metric_key]

        # 昨天=倒数第二行（最后一行是今天不完整数据）
        if len(rows) >= 3:
            yesterday_val = int(rows[-2].get(value_key, 0) or 0)
            prev_val = int(rows[-3].get(value_key, 0) or 0)
            if prev_val > 0:
                change = round((yesterday_val - prev_val) / prev_val * 100, 1)
                arrow = "↑" if change >= 0 else "↓"
                change_str = f"{arrow}{abs(change)}%"
            else:
                change_str = ""
        elif len(rows) >= 2:
            yesterday_val = int(rows[-2].get(value_key, 0) or 0)
            change_str = ""
        else:
            yesterday_val = 0
            change_str = "-"

        col_content = f"{label}\n**{yesterday_val:,}**"
        if change_str:
            col_content += f"\n{change_str}"

        columns.append({
            "tag": "column",
            "width": "weighted",
            "weight": 1,
            "elements": [
                {"tag": "markdown", "content": col_content, "text_align": "center"},
            ],
        })

    return {
        "tag": "column_set",
        "flex_mode": "stretch",
        "background_style": "grey",
        "columns": columns,
    }


def _manufacturer_pie(manufacturer_dist: list[dict]) -> dict:
    """激活设备厂商分布饼图，前8名单独列出，其余归入"其他"。"""
    sorted_rows = sorted(manufacturer_dist, key=lambda r: int(r.get("cnt", 0) or 0), reverse=True)
    values: list[dict] = []
    other = 0
    for i, row in enumerate(sorted_rows):
        name = row.get("manufacturer") or "未知"
        cnt = int(row.get("cnt", 0) or 0)
        if cnt <= 0:
            continue
        if i < 8:
            values.append({"type": name, "value": cnt})
        else:
            other += cnt
    if other > 0:
        values.append({"type": "其他", "value": other})

    total = sum(v["value"] for v in values)
    chart_spec: dict[str, Any] = {
        "type": "pie",
        "title": {"text": f"昨日激活设备厂商分布({total}台)"},
        "data": {"values": values},
        "valueField": "value",
        "categoryField": "type",
        "outerRadius": 0.9,
        "innerRadius": 0.3,
        "label": {"visible": True},
        "legends": {"visible": True, "orient": "bottom"},
    }
    return {
        "tag": "chart",
        "aspect_ratio": "4:3",
        "chart_spec": chart_spec,
    }


def _retention_table(retention: list[dict]) -> dict:
    """留存表格 — 用 markdown 表格展示最近 5 天设备留存。"""
    if not retention:
        return {"tag": "markdown", "content": "暂无留存数据"}

    header = "| 激活日期 | 激活数 | D+1 | D+3 | D+7 |"
    separator = "|:---:|:---:|:---:|:---:|:---:|"
    rows: list[str] = []

    for row in retention:
        date_str = str(row.get("date", ""))
        if len(date_str) > 5:
            date_str = date_str[5:]  # "2026-06-17" → "06-17"
        activated = int(row.get("activated_devices", 0) or 0)
        d1 = row.get("day_1")
        d3 = row.get("day_3")
        d7 = row.get("day_7")

        def fmt(v):
            if v is None:
                return "-"
            return f"{float(v):.1f}%"

        rows.append(f"| {date_str} | {activated} | {fmt(d1)} | {fmt(d3)} | {fmt(d7)} |")

    table_md = "\n".join([header, separator] + rows)
    return {"tag": "markdown", "content": table_md}


register(DailyReportCard())
