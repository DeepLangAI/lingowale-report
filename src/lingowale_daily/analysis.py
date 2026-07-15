"""AI 趋势点评（可选，fail-open）。"""

from __future__ import annotations

import copy
import json
import logging
from datetime import date, timedelta

from lingowale_daily.posthog.normalize import Metrics

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是语鲸App的资深数据分析师。根据给定的指标 JSON，输出2-3句话的深度点评。
数据截止到昨日（T-1，即 {yesterday}），不包含今日。

要求：
- 点评必须聚焦昨日（{yesterday}）的表现，更早几天的数据只用作对比基准
- 更早的异常波动若昨日已恢复或已过去多天，最多一句带过，不要当作重点反复报
- 关注数据之间的因果关联，例如：留存下降是否因为投放用户占比增大？自然激活变化是否与厂商分布有关？
- 引用具体数字佐证你的判断，如果昨日有异常波动，尝试推测原因
- 不要把两个独立指标硬算成转化率（如新注册与新激活设备不是漏斗关系），不要虚构"健康水位"之类的基准
- 用口语化中文，简洁有力，不要分条不要加标题
- 总字数不超过200字，但必须把话说完整"""


def _strip_today(metrics: Metrics) -> Metrics:
    """移除 north_star 中今天的不完整数据，避免 AI 误判。"""
    cleaned = copy.deepcopy(metrics)
    today_str = date.today().strftime("%Y-%m-%d")

    north_star = cleaned.get("north_star", {})
    for key, rows in north_star.items():
        if isinstance(rows, list):
            north_star[key] = [
                r for r in rows
                if str(r.get("day", ""))[:10] != today_str
            ]

    return cleaned


def analyze(metrics: Metrics, *, api_key: str, base_url: str = "") -> str | None:
    """调 Claude 出点评。失败返回 None，不阻断推送。"""
    try:
        import anthropic

        cleaned = _strip_today(metrics)

        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**kwargs)
        yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            temperature=0.3,
            system=_SYSTEM_PROMPT.format(yesterday=yesterday_str),
            messages=[{"role": "user", "content": json.dumps(cleaned, ensure_ascii=False)}],
        )
        return message.content[0].text.strip()
    except Exception:
        log.warning("AI 分析失败，跳过", exc_info=True)
        return None
