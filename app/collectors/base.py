"""采集器统一接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.models.event import SecurityEvent


class BaseCollector(ABC):
    """所有情报采集器的基类，方便接入新数据源。

    新数据源只需继承并实现 collect() 返回 List[SecurityEvent]，
    上层 BriefAgent 无需任何改动。
    """

    name: str = "base"

    @abstractmethod
    def collect(self) -> List[SecurityEvent]:
        """采集一批安防情报事件，返回 SecurityEvent 列表。"""
        raise NotImplementedError
