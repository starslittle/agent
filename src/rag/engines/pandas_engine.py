import logging
from pathlib import Path
from typing import Optional

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

    def build(self) -> Optional[BaseQueryEngine]:
        if not Path(self.config.CSV_FILE_PATH).exists():
            logger.info("CSV 文件不存在，跳过 Pandas 引擎。")
            return None
        try:
            df = pd.read_csv(self.config.CSV_FILE_PATH)
            qe: BaseQueryEngine = PandasQueryEngine(
                df=df,
                verbose=True,
                instructional_prompt="请严格根据指令生成Python代码来回答问题。",
            )
            return qe
        except Exception as e:
            logger.error(f"创建 Pandas 引擎时出错: {e}")
            return None


