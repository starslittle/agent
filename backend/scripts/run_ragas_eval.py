import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from eval.pipelines.runner import run_eval  # noqa: E402


def main():
    cfg = os.environ.get("RAGAS_CONFIG", str(ROOT / "src/eval/configs/ragas.yaml"))
    run_eval(cfg)


if __name__ == "__main__":
    main()


