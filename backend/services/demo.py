"""演示环境重置：清空运营数据，保留法规库、规则库与演示案例。"""


def reset(conn):
    submissions = conn.execute("DELETE FROM submissions").rowcount
    library_cases = conn.execute(
        "DELETE FROM cases WHERE source IN ('submission','disposition','manual','import')").rowcount
    conn.execute("DELETE FROM sqlite_sequence WHERE name='submissions'")
    conn.commit()
    return {"submissions": submissions, "library_cases": library_cases}
