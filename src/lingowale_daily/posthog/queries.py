"""HogQL 查询定义：所有取数 SQL 集中管理。"""

from __future__ import annotations

# ── 北极星指标 ──

NORTH_STAR_NEW_DEVICES = """
SELECT day, new_devices
FROM v_new_devices_daily
WHERE day >= today() - {days}
ORDER BY day
"""

NORTH_STAR_NEW_SIGNUPS = """
SELECT
    toDate(timestamp) AS day,
    count() AS new_signups
FROM events
WHERE event = 'user_login_completed'
    AND properties.login_type LIKE '%注册%'
    AND properties.$lib = 'posthog-react-native'
    AND timestamp >= today() - {days}
GROUP BY day
ORDER BY day
"""

NORTH_STAR_ACTIVE_DEVICES = """
SELECT day, dau
FROM v_dau_device
WHERE day >= today() - {days}
ORDER BY day
"""

NORTH_STAR_ACTIVE_USERS = """
SELECT
    toDate(timestamp) AS day,
    uniqExact(distinct_id) AS active_users
FROM events
WHERE properties.$lib = 'posthog-react-native'
    AND NOT startsWith(distinct_id, 'IMEI')
    AND distinct_id != ''
    AND timestamp >= today() - {days}
GROUP BY day
ORDER BY day
"""

# ── 激活设备厂商分布 ──

DEVICE_MANUFACTURER_YESTERDAY = """
WITH first_install AS (
    SELECT
        e.properties.imei AS imei,
        min(toDate(e.timestamp)) AS install_date,
        argMin(e.properties.$device_manufacturer, e.timestamp) AS manufacturer
    FROM events e
    LEFT JOIN mysql.open_deeplang.imei_mapping old_devices
        ON e.properties.imei = old_devices.cleaned_imei
    WHERE e.event = 'app_install'
        AND e.properties.imei IS NOT NULL
        AND e.properties.imei != ''
        AND old_devices.cleaned_imei IS NULL
    GROUP BY e.properties.imei
)
SELECT manufacturer, count() AS cnt
FROM first_install
WHERE install_date = today() - 1
GROUP BY manufacturer
ORDER BY cnt DESC
"""

# ── 付费模块 ──

PAYMENT_MEMBERSHIP_DISTRIBUTION = """
SELECT plan, plan_status, member_count, billing_cycle
FROM v_membership_tier
"""

PAYMENT_MRR_ARPU = """
SELECT mrr, arpu, arppu, mau_user, paid_users
FROM v_arpu
"""
