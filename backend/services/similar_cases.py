"""相似案例服务：演示案例 + 已定性案例库，调用领域召回。"""
from case_store import load_dataset
from domain.cases.retrieval import retrieve


def similar_for_case(case, conn=None, top_k=None):
    if conn is not None:
        from services.case_linkage import merge_cases
        cases = merge_cases(conn)
    else:
        cases = load_dataset()["cases"]
    return retrieve(case, cases, top_k=top_k)
