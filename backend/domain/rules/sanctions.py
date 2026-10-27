"""R005 使用的名单快路径：只做精确/别名/整体包含，不做模糊打分。

模糊匹配留给 services/screening.py 的交互式筛查；规则引擎逐案判定必须是确定、
可复现、毫秒级的，所以这里刻意不调模糊逻辑。
名单数据来自 domain/sanctions/loader.py（联合国 + OFAC 真实名单）。
"""
from ..sanctions import fast_hit
from ..sanctions.policy import POLICY_TABLE

__all__ = ["fast_hit", "POLICY_TABLE"]
