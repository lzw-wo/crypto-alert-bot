"""数据源抽象:所有类别适配器实现 fetch(),统一返回 AlertItem 列表。

新增一个类别 = 在 sources/ 下新增一个模块实现该接口,engine 无需改动。
"""
from dataclasses import dataclass, field


@dataclass
class AlertItem:
    category: str      # 类别:'price' | 'whale'
    key: str           # 去重键(price=资产名, whale=交易 hash)
    asset: str         # 币种,如 "BTC";whale 也用它匹配订阅
    value: float       # 判定值(price=当前价格, whale=金额 USD)
    extra: dict = field(default_factory=dict)  # 额外信息(报价货币 / 链 / 来源去向等)


class Source:
    """适配器基类。"""

    async def fetch(self) -> list[AlertItem]:
        raise NotImplementedError
