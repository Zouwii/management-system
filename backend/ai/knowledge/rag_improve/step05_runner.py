"""A vs B 对照实验运行器。

用法: python -m ai.knowledge.rag_improve.step05_runner
"""
from __future__ import annotations
import json, sys, time
from pathlib import Path
from collections import defaultdict

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from ai.knowledge.rag_improve.step03_strategies import strategy_a, strategy_b
from ai.knowledge.rag_improve.step04_metrics import recall_at_k, mrr, ndcg_at_k

TEST_QUERIES = Path(__file__).parent / "test_queries.json"
K = 5


def format_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def row(name: str, rec: float, mr: float, nd: float) -> dict:
    return {"name": name, "recall": rec, "mrr": mr, "ndcg": nd}


def print_table(rows: list[dict]) -> None:
    print(f"{'':<22} {'Recall@{:d}'.format(K):>9} {'MRR':>9} {'nDCG@{:d}'.format(K):>9}".format(K, K))
    print("-" * 52)
    for r in rows:
        print(f"{r['name']:<22} {format_pct(r['recall']):>9} {r['mrr']:.4f}{'':>4} {r['ndcg']:.4f}{'':>4}")


def run(output_path: Path | None = None):
    queries = json.loads(TEST_QUERIES.read_text(encoding="utf-8"))
    print(f"=== A vs B 对照实验 ===\n")
    print(f"测试集: {len(queries)} 条")
    print(f"A（基线）: Hybrid RRF → top-{K}")
    print(f"B（实验）: Hybrid RRF top-20 → bge-reranker-base → top-{K}\n")

    # 按维度分组收集
    results_a: dict[str, list[list[int]]] = defaultdict(list)
    results_b: dict[str, list[list[int]]] = defaultdict(list)

    # 整体
    all_a = []
    all_b = []
    all_relevant = []

    # 逐条记录（用于保存到文件）
    per_query: list[dict] = []

    for q in queries:
        qid = q["id"]
        qtype = q["type"]
        diff = q["difficulty"]
        query_text = q["query"]
        relevant = set(q["relevant_chunk_ids"])

        print(f"[{qid:2d}] {query_text[:50]}...", end=" ", flush=True)

        # 策略 A
        t0 = time.time()
        pred_a_raw = strategy_a(query_text, k=K)
        t_a = time.time() - t0
        pred_a = [r["chunk_id"] for r in pred_a_raw]

        # 策略 B
        t0 = time.time()
        pred_b_raw = strategy_b(query_text, k=K)
        t_b = time.time() - t0
        pred_b = [r["chunk_id"] for r in pred_b_raw]

        # 延迟
        print(f"A={t_a:.2f}s B={t_b:.2f}s", end=" ", flush=True)

        # 指标
        rec_a = recall_at_k(pred_a, list(relevant), K)
        rec_b = recall_at_k(pred_b, list(relevant), K)
        mr_a = mrr(pred_a, list(relevant))
        mr_b = mrr(pred_b, list(relevant))
        nd_a = ndcg_at_k(pred_a, list(relevant), K)
        nd_b = ndcg_at_k(pred_b, list(relevant), K)
        print(f"R@{K}: {rec_a:.2f}→{rec_b:.2f} {'▲' if rec_b>rec_a else '▼' if rec_b<rec_a else '—'}", flush=True)

        per_query.append({
            "id": qid,
            "query": query_text,
            "type": qtype,
            "difficulty": diff,
            "relevant_chunk_ids": sorted(relevant),
            "relevant_count": len(relevant),
            "A": {
                "predicted_ids": pred_a,
                "recall": round(rec_a, 4),
                "mrr": round(mr_a, 4),
                "ndcg": round(nd_a, 4),
                "time_s": round(t_a, 3),
            },
            "B": {
                "predicted_ids": pred_b,
                "recall": round(rec_b, 4),
                "mrr": round(mr_b, 4),
                "ndcg": round(nd_b, 4),
                "time_s": round(t_b, 3),
            },
            "delta": {
                "recall": round(rec_b - rec_a, 4),
                "mrr": round(mr_b - mr_a, 4),
                "ndcg": round(nd_b - nd_a, 4),
            },
        })

        all_a.append(pred_a)
        all_b.append(pred_b)
        all_relevant.append(list(relevant))

        results_a[qtype].append(pred_a)
        results_b[qtype].append(pred_b)

        results_a[f"diff_{diff}"].append(pred_a)
        results_b[f"diff_{diff}"].append(pred_b)

    # ---- 计算整体指标 ----
    overall_a_rec = sum(recall_at_k(all_a[i], all_relevant[i], K) for i in range(len(queries))) / len(queries)
    overall_b_rec = sum(recall_at_k(all_b[i], all_relevant[i], K) for i in range(len(queries))) / len(queries)
    overall_a_mrr = sum(mrr(all_a[i], all_relevant[i]) for i in range(len(queries))) / len(queries)
    overall_b_mrr = sum(mrr(all_b[i], all_relevant[i]) for i in range(len(queries))) / len(queries)
    overall_a_ndcg = sum(ndcg_at_k(all_a[i], all_relevant[i], K) for i in range(len(queries))) / len(queries)
    overall_b_ndcg = sum(ndcg_at_k(all_b[i], all_relevant[i], K) for i in range(len(queries))) / len(queries)

    print(f"\n{'='*52}")
    print(f"                    整体汇总")
    print(f"{'='*52}")
    print_table([
        row("A（基线）", overall_a_rec, overall_a_mrr, overall_a_ndcg),
        row("B（+reranker）", overall_b_rec, overall_b_mrr, overall_b_ndcg),
    ])

    # ---- 按类型细分 ----
    for dim_label, dim_key in [("查询类型", None), ("难度", "diff_")]:
        if dim_label == "查询类型":
            categories = ["技术文档", "会议纪要", "表格", "跨文档"]
        else:
            categories = ["easy", "medium", "hard"]

        print(f"\n{'='*52}")
        print(f"                    按{dim_label}细分")
        print(f"{'='*52}")
        sub_rows = []
        for cat in categories:
            key = cat if dim_label == "查询类型" else f"diff_{cat}"
            preds_a = results_a.get(key, [])
            preds_b = results_b.get(key, [])
            rels_a = [all_relevant[i] for i, q in enumerate(queries)
                      if (q["type"] if dim_label == "查询类型" else q["difficulty"]) == cat]
            if not preds_a:
                continue

            n = len(preds_a)
            rec_a = sum(recall_at_k(preds_a[i], rels_a[i], K) for i in range(n)) / n
            rec_b = sum(recall_at_k(preds_b[i], rels_a[i], K) for i in range(n)) / n
            mr_a = sum(mrr(preds_a[i], rels_a[i]) for i in range(n)) / n
            mr_b = sum(mrr(preds_b[i], rels_a[i]) for i in range(n)) / n
            nd_a = sum(ndcg_at_k(preds_a[i], rels_a[i], K) for i in range(n)) / n
            nd_b = sum(ndcg_at_k(preds_b[i], rels_a[i], K) for i in range(n)) / n

            name = f"{cat} (A→B)"
            sub_rows.append(row(name, rec_b - rec_a, mr_b - mr_a, nd_b - nd_a))

        # Show as delta
        print(f"{'':<22} {'ΔRecall@{:d}'.format(K):>10} {'ΔMRR':>10} {'ΔnDCG@{:d}'.format(K):>10}".format(K, K))
        print("-" * 52)
        for r in sub_rows:
            rec_sign = "+" if r["recall"] >= 0 else ""
            mrr_sign = "+" if r["mrr"] >= 0 else ""
            nd_sign = "+" if r["ndcg"] >= 0 else ""
            print(f"{r['name']:<22} {rec_sign}{format_pct(r['recall']):>9} {mrr_sign}{r['mrr']:.4f}{'':>5} {nd_sign}{r['ndcg']:.4f}{'':>4}")

    # ---- 保存逐条结果 ----
    if output_path is None:
        output_path = Path(__file__).parent / "results.json"
    summary = {
        "experiment_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "strategy": "Dual Recall (Hybrid RRF + Pure Vector) → Cross-Encoder",
        "test_queries": len(queries),
        "K": K,
        "overall": {
            "A": {"recall": round(overall_a_rec, 4), "mrr": round(overall_a_mrr, 4), "ndcg": round(overall_a_ndcg, 4)},
            "B": {"recall": round(overall_b_rec, 4), "mrr": round(overall_b_mrr, 4), "ndcg": round(overall_b_ndcg, 4)},
        },
        "per_query": per_query,
    }
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n逐条结果已保存至: {output_path}")

    print(f"\n{'='*52}")
    print("实验完成")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=str, default="results.json", help="输出文件名（默认 results.json）")
    args = ap.parse_args()
    out = Path(__file__).parent / args.output
    run(output_path=out)
