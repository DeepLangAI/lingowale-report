"""PostHog 取数客户端。"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from lingowale_daily.config import Settings

_TIMEOUT = 30.0


def _headers(settings: Settings) -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.posthog_api_key}"}


def _base_url(settings: Settings) -> str:
    return f"{settings.posthog_host}/api/projects/{settings.posthog_project_id}"


@dataclass
class HogQLResult:
    columns: list[str]
    rows: list[list]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
def get_insight(settings: Settings, short_id: str, *, refresh: bool = False) -> dict:
    """按 short_id 拉取 insight 结果。"""
    url = f"{_base_url(settings)}/insights"
    params: dict = {"short_id": short_id}
    if refresh:
        params["refresh"] = "true"
    resp = httpx.get(url, headers=_headers(settings), params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results", [])
    if not results:
        raise ValueError(f"Insight {short_id!r} not found")
    return results[0]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10), reraise=True)
def run_hogql(settings: Settings, sql: str, *, timeout: float = _TIMEOUT) -> HogQLResult:
    """执行 HogQL 查询，返回列名和行列表。"""
    url = f"{_base_url(settings)}/query"
    payload = {"query": {"kind": "HogQLQuery", "query": sql}}
    resp = httpx.post(url, headers=_headers(settings), json=payload, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    return HogQLResult(
        columns=data.get("columns", []),
        rows=data.get("results", []),
    )


@retry(stop=stop_after_attempt(2), wait=wait_exponential(min=2, max=10), reraise=True)
def query_insight(settings: Settings, insight_id: int, *, refresh: str = "blocking") -> HogQLResult:
    """通过 insight ID 获取已缓存的查询结果（避免重新计算）。

    refresh 可选值:
    - "force_cache": 只返回缓存数据
    - "blocking": 有缓存用缓存，否则同步计算
    - "lazy_async": 用缓存，后台刷新
    """
    # 先获取 insight 的 query 定义
    url = f"{_base_url(settings)}/insights/{insight_id}"
    resp = httpx.get(url, headers=_headers(settings), timeout=_TIMEOUT)
    resp.raise_for_status()
    insight = resp.json()

    query_def = insight.get("query")
    if not query_def:
        raise ValueError(f"Insight {insight_id} 没有 query 定义")

    # 用 query endpoint 执行，带 cache 参数
    query_url = f"{_base_url(settings)}/query"
    payload = {"query": query_def, "refresh": refresh}
    resp = httpx.post(query_url, headers=_headers(settings), json=payload, timeout=120.0)
    resp.raise_for_status()
    data = resp.json()

    # DataVisualizationNode 返回结构: {"results": {"columns": [...], "results": [...]}}
    results = data.get("results", data)
    if isinstance(results, dict):
        columns = results.get("columns", [])
        rows = results.get("results", [])
    else:
        columns = data.get("columns", [])
        rows = data.get("results", [])

    return HogQLResult(columns=columns, rows=rows)
