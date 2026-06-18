"""AI 趋势点评（可选，fail-open）。"""

from __future__ import annotations

import json
import logging

from lingowale_daily.posthog.normalize import Metrics

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
你是语鲸App的资深数据分析师。根据给定的指标 JSON，输出2-3句话的深度点评。

要求：
- 关注数据之间的因果关联，例如：留存下降是否因为投放用户占比增大？自然激活变化是否与厂商分布有关？
- 引用具体数字佐证你的判断
- 如果有异常波动，尝试推测原因
- 用口语化中文，简洁有力，不要分条不要加标题
- 总字数不超过200字，但必须把话说完整"""


def analyze(metrics: Metrics, *, api_key: str, base_url: str = "") -> str | None:
    """调 Claude 出点评。失败返回 None，不阻断推送。"""
    try:
        import anthropic

        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = anthropic.Anthropic(**kwargs)
        message = client.messages.create(
            model="claude-haiku-4-5-20241022",
            max_tokens=400,
            temperature=0.3,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": json.dumps(metrics, ensure_ascii=False)}],
        )
        return message.content[0].text.strip()
    except Exception:
        log.warning("AI 分析失败，跳过", exc_info=True)
        return None
