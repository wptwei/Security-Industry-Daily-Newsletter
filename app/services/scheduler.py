"""定时调度：每个工作日（周一~周五）固定时间运行。"""
from __future__ import annotations

import time

import schedule

from app.agents.brief_agent import BriefAgent
from app.utils.logging import get_logger

logger = get_logger("scheduler")


class Scheduler:
    def __init__(self, agent: BriefAgent, schedule_time: str = "07:30") -> None:
        self.agent = agent
        self.schedule_time = schedule_time

    def run_once(self) -> None:
        logger.info("手动触发一次安防情报任务")
        self.agent.run_daily()

    def start(self) -> None:
        # schedule 支持按星期注册，这里注册周一~周五
        for weekday in ("monday", "tuesday", "wednesday", "thursday", "friday"):
            getattr(schedule.every(), weekday).at(self.schedule_time).do(self.agent.run_daily)
        logger.info("已启动工作日定时任务，每周一~周五 %s 运行一次", self.schedule_time)
        while True:
            schedule.run_pending()
            time.sleep(30)

    def stop(self) -> None:
        schedule.clear()
