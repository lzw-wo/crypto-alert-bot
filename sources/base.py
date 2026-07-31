"""数据源抽象:所有类别适配器实现 fetch(),统一返回 PricePoint 列表。

新增一个类别 = 在 sources/ 下新增一个模块实现该接口,engine 无需改动。
"""
from dataclasses import dataclass


@dataclass
class PricePoint:
    asset: str      # 例如 "BTC"
    price: float    # 当前价格
    quote: str = "USDT"


class Source:
    """适配器基类。"""

    async def fetch(self) -> list[PricePoint]:
        raise NotImplementedError
