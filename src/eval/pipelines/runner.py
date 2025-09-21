import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

import yaml
from datasets import load_dataset, Dataset
from langchain_community.chat_models import ChatTongyi
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from src.core.settings import settings

# 允许从项目根导入 src 下模块
import sys
ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from src.rag.system import RAGSystem, RAGConfig  # noqa: E402


def load_config(cfg_path: str) -> Dict[str, Any]:
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_output_dir(base: Path, exp_name: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = base / f"{ts}-{exp_name}"
    out.mkdir(parents=True, exist_ok=True)
    return out


def build_system(engine_name: str, top_k: int, mmr: bool, rerank: bool) -> RAGSystem:
    cfg = RAGConfig()
    # 可根据评估需要覆盖参数
    cfg.SIMILARITY_TOP_K = int(top_k)
    system = RAGSystem(cfg)
    system.startup()
    return system


def run_eval(cfg_path: str):
    cfg = load_config(cfg_path)

    exp = cfg.get("experiment", "default")
    engine_name = cfg.get("engine", "local")
    dataset_path = cfg.get("dataset_path")
    retrieval = cfg.get("retrieval", {})
    top_k = retrieval.get("top_k", 8)
    mmr = retrieval.get("mmr", True)
    rerank = retrieval.get("rerank", True)

    output_dir = Path(cfg.get("output_dir", "reports/eval_runs"))
    out_run = ensure_output_dir(output_dir, exp)

    # 构建系统
    system = build_system(engine_name, top_k, mmr, rerank)
    qe = system.get_query_engine(engine_name)
    if qe is None:
        raise RuntimeError(f"Query engine not available: {engine_name}")

    # 加载评估集（jsonl，字段至少包含 question，可选 ground_truth）
    if dataset_path.endswith(".jsonl"):
        # 使用 datasets 加载本地 jsonl
        ds = load_dataset("json", data_files=dataset_path, split="train")
    else:
        ds = load_dataset(dataset_path, split="train")

    # 延迟导入 ragas，以便不影响主服务依赖
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        faithfulness,
        context_precision,
        context_recall,
    )

    questions = []
    contexts = []
    answers = []
    ground_truths = []

    for row in ds:
        q = row.get("question")
        gt = row.get("ground_truth")
        if not q:
            continue
        try:
            resp = qe.query(q)
            answers.append(str(resp))
            # 收集检索到的上下文（若可获取）
            try:
                ctx = [n.get_text() for n in getattr(resp, "source_nodes", [])]
            except Exception:
                ctx = []
            contexts.append(ctx)
            questions.append(q)
            ground_truths.append(gt or "")
        except Exception as e:
            answers.append("")
            contexts.append([])
            questions.append(q)
            ground_truths.append(gt or "")

    eval_dataset: Dataset = Dataset.from_dict(
        {
            "question": questions,
            "answer": answers,
            "contexts": contexts,
            "ground_truth": ground_truths,
        }
    )

    # 使用达摩盘/通义千问作为评估 LLM，避免 ragas 默认走 OpenAI
    llm = ChatTongyi(model="qwen-plus-2025-07-28", temperature=0.2, dashscope_api_key=settings.DASHSCOPE_API_KEY)

    # 评估用中文向量模型，避免 ragas 默认走 OpenAIEmbeddings
    hf_embeddings = HuggingFaceBgeEmbeddings(model_name=settings.EVAL_EMBED_MODEL, encode_kwargs={"normalize_embeddings": True})

    results = evaluate(
        dataset=eval_dataset,
        metrics=[answer_relevancy, faithfulness, context_precision, context_recall],
        llm=llm,
        embeddings=hf_embeddings,
    )

    metrics_dict = {}
    try:
        # ragas >= 0.3.0
        metrics_dict = {k: float(v) for k, v in results.scores.items()}  # type: ignore[attr-defined]
    except Exception:
        try:
            df = results.to_pandas()
            for col in df.columns:
                if col in {"question", "answer", "contexts", "ground_truth"}:
                    continue
                try:
                    metrics_dict[col] = float(df[col].mean())
                except Exception:
                    pass
        except Exception:
            metrics_dict = {}
    with open(out_run / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics_dict, f, ensure_ascii=False, indent=2)
    with open(out_run / "samples.json", "w", encoding="utf-8") as f:
        json.dump(
            [
                {
                    "question": questions[i],
                    "answer": answers[i],
                    "ground_truth": ground_truths[i],
                    "contexts": contexts[i],
                }
                for i in range(len(questions))
            ],
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(f"Saved metrics to: {out_run / 'metrics.json'}")
    print(f"Saved samples to: {out_run / 'samples.json'}")


if __name__ == "__main__":
    cfg_path = os.environ.get("RAGAS_CONFIG", str(ROOT / "src/eval/configs/ragas.yaml"))
    run_eval(cfg_path)


