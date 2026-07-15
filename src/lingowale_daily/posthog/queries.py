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

# 注：不查 v_arpu（物化视图无定时刷新，会冻结在旧快照），直接从底层实时视图计算
PAYMENT_MRR_ARPU = """
SELECT
    (SELECT mrr_yuan FROM v_mrr) AS mrr,
    round((SELECT mrr_yuan FROM v_mrr) / (SELECT mau_user FROM v_mau_user), 4) AS arpu,
    round((SELECT mrr_yuan FROM v_mrr) / (SELECT paid_users FROM v_paying_users), 2) AS arppu,
    (SELECT mau_user FROM v_mau_user) AS mau_user,
    (SELECT paid_users FROM v_paying_users) AS paid_users
"""

PAYMENT_NEW_DEVICE_CONVERSION = """
SELECT
    p.properties.plan_tier AS plan_tier,
    p.properties.billing_period AS billing_period,
    count(DISTINCT p.person_id) AS cnt
FROM events p
WHERE p.event = 'payment_completed'
  AND p.person_id IN (
    SELECT e2.person_id
    FROM events e2
    WHERE e2.event = 'app_install'
      AND e2.properties.imei IN (
        SELECT e.properties.imei AS device_imei
        FROM events e
        LEFT JOIN mysql.open_deeplang.imei_mapping old
          ON e.properties.imei = old.cleaned_imei
        WHERE e.properties.imei IS NOT NULL
          AND e.properties.imei != ''
          AND e.event = 'app_install'
          AND old.cleaned_imei IS NULL
        GROUP BY e.properties.imei
        HAVING min(toDate(e.timestamp)) = today() - 1
      )
  )
  AND p.distinct_id NOT IN (
    '650881e6be2242c0b2db87712604db9b',
    '645e0764a5b98dc9ebeeda49',
    '0f06c8c94578444e9a5292d391ac9c25',
    'a7d1154ce7e94a669b9626c18e090362',
    'a8ce38e61e4145369caaef540942ac64',
    '283aaf2aafdd4c49bbc4808a4472953c',
    '9a153d7ddd864a9f94f055766204e5f1',
    'fddff5b86e544295a26514b4fab3c4a2'
  )
GROUP BY plan_tier, billing_period
ORDER BY cnt DESC
"""
