"""规则领域：基础规则、类型化规则与执行入口。"""
from .engine import RULE_FUNCS, run_engine

__all__ = ["RULE_FUNCS", "run_engine"]
