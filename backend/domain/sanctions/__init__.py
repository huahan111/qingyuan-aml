"""制裁/涉恐名单域：加载、匹配、处置分级。"""
from .match import HIT_THRESHOLD, MIN_QUERY_LEN, SUSPECT_THRESHOLD, fast_hit, search
from .policy import POLICY_TABLE, policy_for

__all__ = ["HIT_THRESHOLD", "SUSPECT_THRESHOLD", "MIN_QUERY_LEN",
           "search", "fast_hit", "policy_for", "POLICY_TABLE"]
