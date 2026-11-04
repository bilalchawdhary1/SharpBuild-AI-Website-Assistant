from scripts.eval_retrieval import threshold_report
from scripts.smoke_chat import evaluate


def test_threshold_report_counts_fallbacks_per_kind():
    rows = [{"kind": "answerable", "top1": 0.65}, {"kind": "answerable", "top1": 0.57},
            {"kind": "offtopic", "top1": 0.5}, {"kind": "unpublished", "top1": 0.7}]
    assert threshold_report(rows, 0.58) == {"answerable": (1, 2), "unpublished": (0, 1), "offtopic": (1, 1)}


def test_smoke_evaluate():
    assert evaluate(True, [], {"answer": "x", "fallback": True}) == "PASS"
    assert evaluate(False, [], {"answer": "x", "fallback": True}).startswith("FAIL")
    assert evaluate(None, [], {"answer": "x", "fallback": False}) == "REVIEW"
    assert evaluate(None, ["secret"], {"answer": "The SECRET is", "fallback": False}).startswith("FAIL")
