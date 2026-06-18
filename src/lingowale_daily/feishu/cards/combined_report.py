"""合并日报卡片 — 增长 + 付费 + 投放 合为一张卡片，用折叠面板分区。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from lingowale_daily.feishu.cards import register
from lingowale_daily.posthog.normalize import Metrics

# ── 增长指标 ──

_METRIC_LABELS = {
    "new_devices": "新激活设备",
    "new_signups": "新注册用户",
    "active_devices": "活跃设备",
    "active_users": "活跃用户",
}

_VALUE_KEYS = {
    "new_devices": "new_devices",
    "new_signups": "new_signups",
    "active_devices": "dau",
    "active_users": "active_users",
}

# ── 付费 ──

_PLAN_LABELS = {"plus": "Plus", "pro": "Pro"}
_PLAN_ORDER = ["plus月费", "plus年费", "pro月费", "pro年费"]


class CombinedReportCard:
    name = "combined_report"

    def build(self, data: Metrics, note: str | None) -> tuple[str, dict]:
        """返回 ('__raw__', card_json_dict)。"""
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        elements: list[dict] = []

        # ━━ 模块 1: 增长指标（折叠面板）━━
        growth_elements = self._build_growth(data, yesterday)
        elements.append(_collapsible("增长指标", growth_elements, expanded=True))

        # ━━ 模块 2: 投放（折叠面板）━━
        ad_elements = self._build_ad(data, yesterday)
        elements.append(_collapsible("投放", ad_elements))

        # ━━ 模块 3: 付费（折叠面板）━━
        payment_elements = self._build_payment(data, yesterday)
        elements.append(_collapsible("付费", payment_elements))

        # ━━ AI 点评 ━━
        if note:
            elements.append({"tag": "hr"})
            elements.append({"tag": "markdown", "content": "**值得关注**"})
            elements.append({
                "tag": "div",
                "text": {"tag": "plain_text", "content": note},
            })

        card = {
            "schema": "2.0",
            "header": {
                "template": "blue",
                "title": {"tag": "plain_text", "content": f"语鲸数据日报 | {yesterday}"},
            },
            "body": {"elements": elements},
        }
        return "__raw__", card

    # ── 增长 ──

    def _build_growth(self, data: Metrics, yesterday: str) -> list[dict]:
        elements: list[dict] = []
        north_star = data.get("north_star", {})

        # KPI 网格
        elements.append({"tag": "markdown", "content": f"T-1（{yesterday}）核心数据"})
        elements.append(_north_star_kpi_grid(north_star))

        # 激活组成
        ad_activated = data.get("ad_activated_yesterday", 0)
        new_devices_rows = north_star.get("new_devices", [])
        total_new = 0
        if len(new_devices_rows) >= 2:
            total_new = int(new_devices_rows[-2].get("new_devices", 0) or 0)
        organic = total_new - ad_activated
        if total_new > 0:
            elements.append({"tag": "markdown", "content": f"激活组成：自然 **{organic}** + 投放 **{ad_activated}** = **{total_new}**"})

        # 厂商饼图
        manufacturer_dist = data.get("manufacturer_dist", [])
        if manufacturer_dist:
            elements.append(_manufacturer_pie(manufacturer_dist))

        # 留存
        retention = data.get("retention", [])
        if retention:
            elements.append({"tag": "markdown", "content": "**设备留存**（首次激活，最近8天队列）"})
            elements.append(_retention_table(retention))

        elements.append({"tag": "markdown", "content": "[详情见 PostHog →](https://posthog.deeplang.tech/project/1/dashboard/5)"})

        return elements

    def _build_payment(self, data: Metrics, yesterday: str) -> list[dict]:
        elements: list[dict] = []
        payment = data.get("payment", {})

        # 新增付费
        new_subs = payment.get("new_subs", [])
        elements.append({"tag": "markdown", "content": f"T-1（{yesterday}）新增付费用户（不含试用）"})
        if new_subs:
            elements.append(_new_subs_chart(new_subs))
        else:
            elements.append({"tag": "markdown", "content": "昨日无新增付费"})

        # 会员分布 + MRR
        distribution = payment.get("distribution", [])
        if distribution:
            elements.append(_distribution_chart(distribution))
        mrr_arpu = payment.get("mrr_arpu", [])
        if mrr_arpu:
            elements.append(_mrr_arpu_grid(mrr_arpu))

        elements.append({"tag": "markdown", "content": "[详情见 PostHog →](https://posthog.deeplang.tech/project/1/dashboard/24)"})

        return elements

    def _build_ad(self, data: Metrics, yesterday: str) -> list[dict]:
        elements: list[dict] = []

        # 投放概览
        ad_daily = data.get("ad_daily", [])
        elements.append({"tag": "markdown", "content": "账户整体数据（近5个有投放日，倒序）"})
        if ad_daily:
            elements.append(_ad_table(ad_daily))
        else:
            elements.append({"tag": "markdown", "content": "暂无投放数据"})

        # 买量留存
        ad_retention = data.get("ad_retention", [])
        if ad_retention:
            elements.append({"tag": "markdown", "content": "**买量设备留存**（小红书买量，最近8天队列）"})
            elements.append(_retention_table(ad_retention))

        return elements


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  组件函数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _collapsible(title: str, elements: list[dict], *, expanded: bool = False) -> dict:
    """飞书折叠面板。"""
    return {
        "tag": "collapsible_panel",
        "expanded": expanded,
        "header": {
            "title": {
                "tag": "plain_text",
                "content": title,
            },
        },
        "border": {"color": "grey"},
        "elements": elements,
    }


def _north_star_kpi_grid(north_star: dict[str, list[dict]]) -> dict:
    """KPI 网格。"""
    columns: list[dict] = []
    for metric_key, label in _METRIC_LABELS.items():
        rows = north_star.get(metric_key, [])
        value_key = _VALUE_KEYS[metric_key]

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
    """激活设备厂商分布饼图。"""
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
    """留存 markdown 表格。"""
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


def _new_subs_chart(new_subs: list[dict]) -> dict:
    """新增付费柱状图。"""
    plan_counts: dict[str, int] = {}
    for row in new_subs:
        plan = row.get("plan", "unknown")
        plan_counts[plan] = int(row.get("count", 0))

    values: list[dict] = []
    for plan in _PLAN_ORDER:
        values.append({"plan": plan, "count": plan_counts.get(plan, 0)})

    chart_spec: dict[str, Any] = {
        "type": "bar",
        "title": {"text": "昨日新增付费"},
        "data": {"values": values},
        "xField": "plan",
        "yField": "count",
        "label": {"visible": True},
    }
    return {
        "tag": "chart",
        "aspect_ratio": "16:9",
        "chart_spec": chart_spec,
    }


def _distribution_chart(distribution: list[dict]) -> dict:
    """会员分布饼图（不含试用）。"""
    values: list[dict] = []
    total = 0
    for row in distribution:
        status = row.get("plan_status", "")
        if status == "trial":
            continue
        plan = _PLAN_LABELS.get(row.get("plan", ""), row.get("plan", "unknown"))
        cycle = row.get("billing_cycle", "")
        label = f"{plan}-{cycle}"
        count = int(row.get("member_count", 0))
        total += count
        values.append({"type": label, "value": count})

    if not values:
        return {"tag": "markdown", "content": "当前无付费会员"}

    chart_spec: dict[str, Any] = {
        "type": "pie",
        "title": {"text": f"付费会员分布 当前({total}人)"},
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


def _mrr_arpu_grid(mrr_arpu: list[dict]) -> dict:
    """MRR / ARPU 网格。"""
    if not mrr_arpu:
        return {"tag": "markdown", "content": "MRR/ARPU: -"}
    row = mrr_arpu[0]
    mrr = row.get("mrr", 0)
    arpu = row.get("arpu", 0)
    paid = row.get("paid_users", 0)
    mau = row.get("mau_user", 0)

    mrr_str = f"¥{float(mrr):,.0f}" if mrr else "-"
    arpu_str = f"¥{float(arpu):.2f}" if arpu else "-"

    columns_data = [
        {"label": "MRR", "value": mrr_str},
        {"label": "ARPU", "value": arpu_str},
        {"label": "付费用户", "value": f"{int(paid)}"},
        {"label": "MAU", "value": f"{int(mau):,}"},
    ]

    return {
        "tag": "column_set",
        "flex_mode": "stretch",
        "background_style": "grey",
        "columns": [
            {
                "tag": "column",
                "width": "weighted",
                "weight": 1,
                "elements": [
                    {"tag": "markdown", "content": f"{col['label']}\n**{col['value']}**", "text_align": "center"},
                ],
            }
            for col in columns_data
        ],
    }


def _ad_table(ad_daily: list[dict]) -> dict:
    """投放数据表格。"""
    header = "| 日期 | 消耗(¥) | 展现 | 点击 | 点击率 |"
    separator = "|:---:|:---:|:---:|:---:|:---:|"
    rows: list[str] = []

    for row in ad_daily:
        stat_date = str(row.get("stat_date", ""))
        if len(stat_date) > 5:
            stat_date = stat_date[5:]
        fee = float(row.get("total_fee", 0) or 0)
        impression = int(row.get("total_impression", 0) or 0)
        click = int(row.get("total_click", 0) or 0)
        ctr = f"{click / impression * 100:.2f}%" if impression > 0 else "-"

        rows.append(
            f"| {stat_date} | ¥{fee:,.1f} | {impression:,} | {click:,} | {ctr} |"
        )

    table_md = "\n".join([header, separator] + rows)
    return {"tag": "markdown", "content": table_md}


register(CombinedReportCard())
