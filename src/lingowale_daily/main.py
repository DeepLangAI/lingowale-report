"""主编排：遍历 job 跑 pipeline，兜底告警。"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from lingowale_daily.analysis import analyze
from lingowale_daily.config import Settings
from lingowale_daily.feishu import FeishuClient
from lingowale_daily.feishu.cards import get_card
from lingowale_daily.jobs import enabled_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def run(*, dry_run: bool = False) -> None:
    settings = Settings()
    client = FeishuClient(settings)

    jobs = enabled_jobs()
    log.info("开始执行，共 %d 个 job", len(jobs))

    for job in jobs:
        try:
            log.info("[%s] 开始取数", job.name)
            metrics = job.fetch(settings)

            # AI 点评（可选）
            note = None
            if settings.anthropic_api_key:
                note = analyze(
                    metrics,
                    api_key=settings.anthropic_api_key,
                    base_url=settings.anthropic_base_url,
                )

            # 组卡
            card_builder = get_card(job.card)
            template_id, card_data = card_builder.build(metrics, note)

            if dry_run:
                log.info("[%s] dry-run 输出:", job.name)
                log.info("  template_id: %s", template_id)
                log.info("  card_data: %s", json.dumps(card_data, ensure_ascii=False, indent=2))
                continue

            # 发送
            if template_id == "__raw__":
                client.send_card_webhook(card_data)
            else:
                client.send_template_card(settings.feishu_target_chat_id, template_id, card_data)
            log.info("[%s] 推送成功", job.name)

        except Exception as e:
            log.exception("[%s] 执行失败", job.name)
            if not dry_run:
                client.alert(f"⚠️ [{job.name}] 推送失败：{e}")

    log.info("全部完成")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Lingowale Daily 指标推送")
    parser.add_argument("--dry-run", action="store_true", help="只取数组卡，不实际发送")
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except Exception as e:
        log.critical("启动失败: %s", e, exc_info=True)
        # 尝试用最基本方式告警
        try:
            settings = Settings()
            client = FeishuClient(settings)
            client.alert(f"⚠️ lingowale-daily 启动失败：{e}")
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    cli()
