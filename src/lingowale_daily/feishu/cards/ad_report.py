"""投放日报卡片构建器 — 小红书买量投放数据 + 买量设备留存。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from lingowale_daily.feishu.cards import register
from lingowale_daily.posthog.normalize import Metrics


def _section_header(title: str) -> dict:
    return {"tag": "markdown", "content": f"**{title}**"}


class AdReportCard:
    name = "ad_report"

    def build(self, data: Metrics, note: str | None) -> tuple[str, dict]:
        """返回 ('__raw__', card_json_dict)。"""
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        elements: list[dict] = []

        # ── 一、投放概览 ──
        ad_daily = data.get("ad_daily", [])
        elements.append(_section_header("一、投放概览"))
        elements.append({"tag": "markdown", "content": "账户整体数据（近5个有投放日，倒序）"})
        if ad_daily:
            elements.append(_ad_table(ad_daily))
        else:
            elements.append({"tag": "markdown", "content": "暂无投放数据"})

        # ── 二、买量设备留存 ──
        retention = data.get("retention", [])
        if retention:
            elements.append({"tag": "hr"})
            elements.append(_section_header("二、买量设备留存"))
            elements.append({"tag": "markdown", "content": "小红书买量首次激活设备留存率（最近8天队列）"})
            elements.append(_retention_table(retention))

        # ── 三、值得关注 ──
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
                "template": "orange",
                "title": {"tag": "plain_text", "content": f"语鲸投放日报 | {yesterday}"},
            },
            "body": {"elements": elements},
        }
        return "__raw__", card


def _ad_table(ad_daily: list[dict]) -> dict:
    """投放数据表格 — markdown 表。"""
    header = "| 日期 | 消耗(¥) | 展现 | 点击 | 点击率 |"
    separator = "|:---:|:---:|:---:|:---:|:---:|"
    rows: list[str] = []

    for row in ad_daily:
        stat_date = str(row.get("stat_date", ""))
        if len(stat_date) > 5:
            stat_date = stat_date[5:]  # "2026-06-17" → "06-17"
        fee = float(row.get("total_fee", 0) or 0)
        impression = int(row.get("total_impression", 0) or 0)
        click = int(row.get("total_click", 0) or 0)
        ctr = f"{click / impression * 100:.2f}%" if impression > 0 else "-"

        rows.append(
            f"| {stat_date} | ¥{fee:,.1f} | {impression:,} | {click:,} | {ctr} |"
        )

    table_md = "\n".join([header, separator] + rows)
    return {"tag": "markdown", "content": table_md}


def _retention_table(retention: list[dict]) -> dict:
    """买量设备留存表格。"""
    if not retention:
        return {"tag": "markdown", "content": "暂无留存数据"}

    header = "| 激活日期 | 激活数 | D+1 | D+3 | D+7 |"
    separator = "|:---:|:---:|:---:|:---:|:---:|"
    rows: list[str] = []

    for row in retention:
        date_str = str(row.get("date", ""))
        if len(date_str) > 5:
            date_str = date_str[5:]
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


register(AdReportCard())
