"""报表任务清单。每个 job = (取数函数, 卡片名)。"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Callable

import httpx

from lingowale_daily.config import Settings
from lingowale_daily.posthog import run_hogql, query_insight
from lingowale_daily.posthog.normalize import Metrics, hogql_rows_to_dict
from lingowale_daily.posthog.queries import (
    NORTH_STAR_ACTIVE_DEVICES,
    NORTH_STAR_ACTIVE_USERS,
    NORTH_STAR_NEW_DEVICES,
    NORTH_STAR_NEW_SIGNUPS,
    DEVICE_MANUFACTURER_YESTERDAY,
    PAYMENT_MEMBERSHIP_DISTRIBUTION,
    PAYMENT_MRR_ARPU,
    PAYMENT_NEW_DEVICE_CONVERSION,
)

# 确保卡片模块被导入以触发 register
import lingowale_daily.feishu.cards.daily_report  # noqa: F401
import lingowale_daily.feishu.cards.payment_report  # noqa: F401
import lingowale_daily.feishu.cards.ad_report  # noqa: F401
import lingowale_daily.feishu.cards.combined_report  # noqa: F401

log = logging.getLogger(__name__)

# 留存 insight ID（"首次激活设备留存率_日维度"）
_RETENTION_INSIGHT_ID = 52
# 新增付费用户趋势 insight ID
_NEW_PAID_USERS_INSIGHT_ID = 176
# 试用转正式付费转化率 insight ID
_TRIAL_CONVERSION_INSIGHT_ID = 172
# 小红书买量留存 insight ID
_AD_RETENTION_INSIGHT_ID = 106

# 投放数据 HogQL
_AD_DAILY_SQL = """\
SELECT stat_date, total_fee, total_impression, total_click, total_activate
FROM mysql.open_deeplang.xhs_ad_daily
WHERE total_fee > 0
ORDER BY stat_date DESC
LIMIT 5
"""


@dataclass
class Job:
    name: str
    card: str  # registry 中的卡片名
    fetch: Callable[[Settings], Metrics]
    enabled: bool = True


def _query(settings: Settings, sql: str, *, timeout: float = 30.0) -> list[dict[str, Any]]:
    """执行 HogQL 并返回 dict 列表。"""
    result = run_hogql(settings, sql, timeout=timeout)
    return hogql_rows_to_dict(result.rows, result.columns)


def _fetch_retention(settings: Settings) -> list[dict[str, Any]]:
    """从 insight #52 缓存拉取留存数据，取最近 8 天（排除今天）。"""
    result = query_insight(settings, _RETENTION_INSIGHT_ID, refresh="force_cache")
    rows = hogql_rows_to_dict(result.rows, result.columns)
    today_str = date.today().strftime("%Y-%m-%d")

    recent = []
    for row in rows:
        if str(row.get("日期", ""))[:10] == today_str:
            continue
        if len(recent) >= 8:
            break
        recent.append({
            "date": row.get("日期", ""),
            "activated_devices": int(row.get("新激活设备数", 0) or 0),
            "day_1": row.get("day_1"),
            "day_3": row.get("day_3"),
            "day_7": row.get("day_7"),
            "day_14": row.get("day_14"),
        })
    return recent


def _fetch_new_paid_users(settings: Settings) -> dict[str, list[dict[str, Any]]]:
    """从 insight #176 获取昨日新增付费用户，分为付费和试用两组。"""
    url = f"{settings.posthog_host}/api/projects/{settings.posthog_project_id}/insights/{_NEW_PAID_USERS_INSIGHT_ID}"
    resp = httpx.get(url, headers={"Authorization": f"Bearer {settings.posthog_api_key}"}, timeout=30.0)
    resp.raise_for_status()
    insight = resp.json()

    result_series = insight.get("result", [])
    if not result_series:
        return {"paid": [], "trial": []}

    yesterday_str = (date.today() - timedelta(days=1)).strftime("%-d-%b-%Y")
    paid_counts: dict[str, int] = defaultdict(int)
    trial_counts: dict[str, int] = defaultdict(int)

    for series in result_series:
        custom_name = series.get("action", {}).get("custom_name", "")

        data = series.get("data", [])
        labels = series.get("labels", [])
        if not data or not labels:
            continue

        # 按日期找昨天的值
        yesterday_count = 0
        for i, label in enumerate(labels):
            if label == yesterday_str:
                yesterday_count = int(data[i] or 0)
                break

        if yesterday_count > 0:
            if "试用" in custom_name:
                trial_counts["试用"] += yesterday_count
            else:
                paid_counts[custom_name] += yesterday_count

    return {
        "paid": [{"plan": plan, "count": count} for plan, count in paid_counts.items()],
        "trial": [{"plan": plan, "count": count} for plan, count in trial_counts.items()],
    }


# ── 增长运营日报 ──

def _fetch_growth_report(settings: Settings) -> Metrics:
    """拉取增长运营数据：北极星指标 + 厂商分布 + 激活组成 + 留存。"""
    days = 8

    north_star = {
        "new_devices": _query(settings, NORTH_STAR_NEW_DEVICES.format(days=days)),
        "new_signups": _query(settings, NORTH_STAR_NEW_SIGNUPS.format(days=days)),
        "active_devices": _query(settings, NORTH_STAR_ACTIVE_DEVICES.format(days=days)),
        "active_users": _query(settings, NORTH_STAR_ACTIVE_USERS.format(days=days)),
    }

    # 厂商分布
    manufacturer_dist = _query(settings, DEVICE_MANUFACTURER_YESTERDAY)

    # 投放激活数（昨天）— 从 insight #106，按日期精确匹配；无行 = 当天投放激活为 0
    ad_retention_result = query_insight(settings, _AD_RETENTION_INSIGHT_ID, refresh="force_cache")
    ad_rows = hogql_rows_to_dict(ad_retention_result.rows, ad_retention_result.columns)
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    ad_activated_yesterday = 0
    for row in ad_rows:
        if str(row.get("日期", ""))[:10] == yesterday_str:
            ad_activated_yesterday = int(row.get("新激活设备数", 0) or 0)
            break

    retention = _fetch_retention(settings)

    return {
        "report_type": "daily",
        "north_star": north_star,
        "manufacturer_dist": manufacturer_dist,
        "ad_activated_yesterday": ad_activated_yesterday,
        "retention": retention,
    }


# ── 付费日报 ──

def _fetch_payment_report(settings: Settings) -> Metrics:
    """拉取付费数据：新增付费 + 会员分布 + MRR/ARPU。"""
    new_users = _fetch_new_paid_users(settings)
    payment = {
        "new_subs": new_users["paid"],
        "new_trial": new_users["trial"],
        "distribution": _query(settings, PAYMENT_MEMBERSHIP_DISTRIBUTION),
        "mrr_arpu": _query(settings, PAYMENT_MRR_ARPU),
    }

    return {"payment": payment}


# ── 投放日报 ──

def _fetch_ad_retention(settings: Settings) -> list[dict[str, Any]]:
    """从 insight #106 拉取小红书买量留存数据，取最近 8 天（排除今天）。"""
    result = query_insight(settings, _AD_RETENTION_INSIGHT_ID, refresh="force_cache")
    rows = hogql_rows_to_dict(result.rows, result.columns)
    today_str = date.today().strftime("%Y-%m-%d")

    recent = []
    for row in rows:
        if str(row.get("日期", ""))[:10] == today_str:
            continue
        if len(recent) >= 8:
            break
        recent.append({
            "date": row.get("日期", ""),
            "activated_devices": int(row.get("新激活设备数", 0) or 0),
            "day_1": row.get("day_1"),
            "day_3": row.get("day_3"),
            "day_7": row.get("day_7"),
            "day_14": row.get("day_14"),
        })
    return recent


def _fetch_ad_report(settings: Settings) -> Metrics:
    """拉取投放数据：广告日消耗 + 买量设备留存。"""
    ad_daily = _query(settings, _AD_DAILY_SQL)
    retention = _fetch_ad_retention(settings)

    return {
        "ad_daily": ad_daily,
        "retention": retention,
    }


# ── 合并日报 ──

def _fetch_combined_report(settings: Settings) -> Metrics:
    """拉取全部数据：增长 + 付费 + 投放，合并为一个 Metrics dict。"""
    days = 8

    north_star = {
        "new_devices": _query(settings, NORTH_STAR_NEW_DEVICES.format(days=days)),
        "new_signups": _query(settings, NORTH_STAR_NEW_SIGNUPS.format(days=days)),
        "active_devices": _query(settings, NORTH_STAR_ACTIVE_DEVICES.format(days=days)),
        "active_users": _query(settings, NORTH_STAR_ACTIVE_USERS.format(days=days)),
    }

    manufacturer_dist = _query(settings, DEVICE_MANUFACTURER_YESTERDAY)

    # 投放激活数（昨天）— 按日期精确匹配；无行 = 当天投放激活为 0
    ad_retention_result = query_insight(settings, _AD_RETENTION_INSIGHT_ID, refresh="force_cache")
    ad_rows = hogql_rows_to_dict(ad_retention_result.rows, ad_retention_result.columns)
    yesterday_str = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    ad_activated_yesterday = 0
    for row in ad_rows:
        if str(row.get("日期", ""))[:10] == yesterday_str:
            ad_activated_yesterday = int(row.get("新激活设备数", 0) or 0)
            break

    retention = _fetch_retention(settings)

    # 付费
    new_users = _fetch_new_paid_users(settings)
    trial_conversion_result = query_insight(settings, _TRIAL_CONVERSION_INSIGHT_ID, refresh="force_cache")
    trial_conversion = hogql_rows_to_dict(trial_conversion_result.rows, trial_conversion_result.columns)
    payment = {
        "new_subs": new_users["paid"],
        "new_trial": new_users["trial"],
        "distribution": _query(settings, PAYMENT_MEMBERSHIP_DISTRIBUTION),
        "mrr_arpu": _query(settings, PAYMENT_MRR_ARPU),
        "trial_conversion": trial_conversion[0] if trial_conversion else {},
        "new_device_conversion": _query(settings, PAYMENT_NEW_DEVICE_CONVERSION),
    }

    # 投放
    ad_daily = _query(settings, _AD_DAILY_SQL)
    ad_retention = _fetch_ad_retention(settings)

    return {
        "north_star": north_star,
        "manufacturer_dist": manufacturer_dist,
        "ad_activated_yesterday": ad_activated_yesterday,
        "retention": retention,
        "payment": payment,
        "ad_daily": ad_daily,
        "ad_retention": ad_retention,
    }


# ── 注册所有 job ──
ALL_JOBS: list[Job] = [
    Job(name="数据日报", card="combined_report", fetch=_fetch_combined_report),
    # 以下旧 job 保留但默认禁用，需要单独发时可启用
    Job(name="增长日报", card="daily_report", fetch=_fetch_growth_report, enabled=False),
    Job(name="付费日报", card="payment_report", fetch=_fetch_payment_report, enabled=False),
    Job(name="投放日报", card="ad_report", fetch=_fetch_ad_report, enabled=False),
]


def enabled_jobs() -> list[Job]:
    return [j for j in ALL_JOBS if j.enabled]
