"""付费卡片构建器 — 新增付费 + 会员分布 + MRR/ARPU。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from lingowale_daily.feishu.cards import register
from lingowale_daily.posthog.normalize import Metrics

_PLAN_LABELS = {
    "plus": "Plus",
    "pro": "Pro",
}


def _section_header(title: str) -> dict:
    return {"tag": "markdown", "content": f"**{title}**"}


class PaymentReportCard:
    name = "payment_report"

    def build(self, data: Metrics, note: str | None) -> tuple[str, dict]:
        """返回 ('__raw__', card_json_dict)。"""
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        payment = data.get("payment", {})

        elements: list[dict] = []

        # ── 新增付费 ──
        new_subs = payment.get("new_subs", [])
        elements.append(_section_header("一、新增付费"))
        elements.append({"tag": "markdown", "content": f"T-1（{yesterday}）新增付费用户（不含试用）"})
        if new_subs:
            elements.append(_new_subs_chart(new_subs))
        else:
            elements.append({"tag": "markdown", "content": "昨日无新增付费"})

        # ── 会员分布 + MRR ──
        elements.append({"tag": "hr"})
        elements.append(_section_header("二、会员概况"))
        distribution = payment.get("distribution", [])
        if distribution:
            elements.append(_distribution_chart(distribution))
        mrr_arpu = payment.get("mrr_arpu", [])
        if mrr_arpu:
            elements.append(_mrr_arpu_grid(mrr_arpu))

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
                "template": "green",
                "title": {"tag": "plain_text", "content": f"语鲸付费日报 | {yesterday}"},
            },
            "body": {"elements": elements},
        }
        return "__raw__", card


_PLAN_ORDER = ["plus月费", "plus年费", "pro月费", "pro年费"]


def _new_subs_chart(new_subs: list[dict]) -> dict:
    """昨日新增付费 — 柱状图，横轴固定顺序。"""
    # 建立 plan→count 映射
    plan_counts: dict[str, int] = {}
    for row in new_subs:
        plan = row.get("plan", "unknown")
        plan_counts[plan] = int(row.get("count", 0))

    # 按固定顺序生成，没有的写 0
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
    """当前会员分布 — 饼图（不含试用）。"""
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
    """MRR / ARPU 网格展示。"""
    if not mrr_arpu:
        return {"tag": "markdown", "content": "MRR/ARPU: -"}
    row = mrr_arpu[0]
    mrr = row.get("mrr", 0)
    arpu = row.get("arpu", 0)
    paid = row.get("paid_users", 0)
    mau = row.get("mau_user", 0)

    mrr_str = f"¥{float(mrr):,.0f}" if mrr else "-"
    arpu_str = f"¥{float(arpu):.2f}" if arpu else "-"

    columns = [
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
            for col in columns
        ],
    }


register(PaymentReportCard())
