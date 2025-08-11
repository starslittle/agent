import logging
from pathlib import Path
from typing import Optional, List

import pandas as pd
from llama_index.core.base.base_query_engine import BaseQueryEngine
from llama_index.experimental.query_engine import PandasQueryEngine


logger = logging.getLogger(__name__)


class PandasEngine:
    name = "pandas"
    tool_name = "sales_data_analyzer"
    description = "CSV 销售数据的查询与分析。"

    def __init__(self, config):
        self.config = config

    def _load_single_csv(self, file_path: Path) -> Optional[pd.DataFrame]:
        try:
            df = pd.read_csv(file_path)
            return df
        except Exception as e:
            logger.error(f"读取 CSV 失败: {file_path} -> {e}")
            return None

    def _merge_csvs(self, csv_files: List[Path]) -> Optional[pd.DataFrame]:
        frames: List[pd.DataFrame] = []
        for fp in csv_files:
            df = self._load_single_csv(fp)
            if df is not None:
                df["__source_file__"] = fp.name
                frames.append(df)
        if not frames:
            return None
        try:
            return pd.concat(frames, ignore_index=True)
        except Exception as e:
            logger.error(f"合并 CSV 失败: {e}")
            return None

    def build(self) -> Optional[BaseQueryEngine]:
        csv_file = Path(getattr(self.config, "CSV_FILE_PATH", ""))
        csv_dir = Path(getattr(self.config, "CSV_DIR_PATH", ""))

        df: Optional[pd.DataFrame] = None

        # 优先读取指定文件
        if csv_file and csv_file.exists() and csv_file.is_file():
            df = self._load_single_csv(csv_file)
        else:
            # 尝试从目录批量读取
            if csv_dir and csv_dir.exists() and csv_dir.is_dir():
                csv_files = sorted([p for p in csv_dir.glob("*.csv")])
                if not csv_files:
                    logger.info("CSV 目录存在，但未发现 .csv 文件，跳过 Pandas 引擎。")
                    return None
                df = self._merge_csvs(csv_files)
            else:
                logger.info("未找到 CSV 文件或目录，跳过 Pandas 引擎。")
                return None

        if df is None:
            logger.info("CSV 数据为空，跳过 Pandas 引擎。")
            return None

        try:
            qe: BaseQueryEngine = PandasQueryEngine(
                df=df,
                verbose=True,
                instructional_prompt="请严格根据指令生成Python代码来回答问题。",
            )
            return qe
        except Exception as e:
            logger.error(f"创建 Pandas 引擎时出错: {e}")
            return None


