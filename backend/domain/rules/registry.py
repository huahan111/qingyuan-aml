"""规则注册表：新增规则只需写函数并加 @rule，不改执行主循环。"""
RULE_FUNCS = {}


def rule(rule_id):
    def register(fn):
        RULE_FUNCS[rule_id] = fn
        return fn
    return register
