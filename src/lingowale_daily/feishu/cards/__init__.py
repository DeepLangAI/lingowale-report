"""卡片协议与 registry。"""

from __future__ import annotations

from typing import Protocol

from lingowale_daily.posthog.normalize import Metrics


class Card(Protocol):
    """卡片构建器协议。"""

    name: str

    def build(self, data: Metrics, note: str | None) -> tuple[str, dict]:
        """返回 (template_id, template_variable)。

        约定: template_id == '__raw__' 时，dict 为完整 card JSON，走 send_raw_card。
        否则走 send_template_card(template_id, template_variable=dict)。
        """
        ...


# name → Card builder 实例
_registry: dict[str, Card] = {}


def register(card: Card) -> Card:
    _registry[card.name] = card
    return card


def get_card(name: str) -> Card:
    if name not in _registry:
        raise KeyError(f"未注册的卡片类型: {name!r}，可用: {list(_registry.keys())}")
    return _registry[name]


def list_cards() -> list[str]:
    return list(_registry.keys())
