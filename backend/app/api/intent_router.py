#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能意图路由器 - 判断用户输入的意图类型

该模块负责分析用户输入，判断其是属于：
1. chat - 日常聊天、问候、简单对话
2. task - 复杂任务、需要使用工具的请求

基于判断结果，将请求路由到合适的 Agent。
"""

from typing import Literal, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_community.chat_models import ChatTongyi
from langchain_core.output_parsers import StrOutputParser
from app.core.settings import settings


# 意图分类的提示词模板
INTENT_CLASSIFICATION_PROMPT = """你是一个智能意图分析器。你需要分析用户的输入，判断其意图类型。

请仔细分析用户的输入，并严格按照以下规则进行分类：

**chat类型（日常聊天）**：
- 简单问候：你好、hi、hello、早上好、晚安等
- 闲聊对话：今天天气怎么样、你是谁、介绍一下自己等
- 简单询问：你能做什么、有什么功能等
- 情感表达：谢谢、不客气、再见等

**task类型（复杂任务）**：
- 命理分析：分析命盘、紫微斗数、八字算命、风水等
- 信息搜索：搜索新闻、查找资料、网络检索等
- 数据分析：分析CSV数据、处理Excel文件等
- 专业咨询：技术问题、学术研究、深度分析等
- 文档处理：总结文档、分析PDF内容等
- 工具使用：需要调用特定工具或API的请求

**判断原则**：
1. 如果用户输入简短（通常少于20字）且内容简单，倾向于判断为 chat
2. 如果用户输入包含专业术语、复杂描述、明确的任务指令，判断为 task
3. 如果用户提到具体的分析、搜索、计算需求，判断为 task
4. 当不确定时，倾向于判断为 chat，避免不必要的复杂处理

用户输入: {user_input}

请只回答 "chat" 或 "task"，不要添加任何其他内容。"""


class IntentRouter:
    """智能意图路由器"""
    
    def __init__(self):
        """初始化路由器"""
        self.llm = ChatTongyi(
            model="qwen-plus-2025-07-28",
            temperature=0.1,  # 使用较低的温度确保判断的一致性
            dashscope_api_key=settings.DASHSCOPE_API_KEY or "",
        )
        
        self.prompt = ChatPromptTemplate.from_template(INTENT_CLASSIFICATION_PROMPT)
        self.parser = StrOutputParser()
        
        # 构建分类链
        self.classification_chain = self.prompt | self.llm | self.parser
        
        # 缓存常见问候语的判断结果，提高效率
        self.chat_keywords = {
            "你好", "hi", "hello", "早上好", "晚上好", "晚安", "再见",
            "谢谢", "不客气", "没关系", "好的", "嗯", "哦", "是的",
            "你是谁", "介绍", "功能", "能做什么", "怎么用"
        }

    @staticmethod
    def _normalize_text(text: str) -> str:
        """去掉空白与常见标点，仅保留中英文与数字，便于稳健判定问候。"""
        import re
        s = (text or "").strip()
        # 仅保留中文、英文、数字
        return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", s)
    
    def classify_intent(self, user_input: str) -> Literal["chat", "task"]:
        """
        分类用户输入的意图
        
        Args:
            user_input: 用户输入的文本
            
        Returns:
            "chat" 或 "task"
        """
        if not user_input or not user_input.strip():
            return "chat"
        
        user_input = user_input.strip()
        
        # 第一优先级：简单问候与极短文本，直接返回 chat（避免不必要的LLM 调用）
        norm = self._normalize_text(user_input)
        simple_greetings = ["你好", "您好", "嗨", "hi", "hello"]
        if norm.lower() in [g.lower() for g in simple_greetings]:
            return "chat"
        
        # 第二优先级：包含聊天关键词且长度较短（小于20字符），直接判断为 chat
        if len(norm) <= 20 and any(keyword in user_input.lower() for keyword in self.chat_keywords):
            return "chat"
        
        # 第三优先级：明确的任务关键词，直接判断为task
        task_keywords = [
            # 命理相关
            "命盘", "紫微", "八字", "风水", "算命", "占卜", "命理", "斗数", "分析命盘", "生辰", "时辰", "排盘", "流年", "运势", "财运", "婚姻", "官禄", "交友", "父母", "田宅", "福德", "疾厄", "兄弟", "夫妻", "子女", "迁移", "身宫",
            # 深度思考相关  
            "分析", "研究", "调研", "搜索", "查找", "深入", "详细", "综合分析"
        ]
        if any(keyword in user_input for keyword in task_keywords):
            return "task"
        
        # 第四优先级：长文本（超过50字）很可能是复杂任务
        if len(user_input) > 50:
            return "task"
        
        # 最后：对于模糊情况，倾向于判断为chat（避免不必要的ReAct复杂度）
        # 只有在真正需要时才使用LLM分类
        if len(user_input) > 20:  # 中等长度的文本才需要LLM判断
            try:
                result = self.classification_chain.invoke({"user_input": user_input})
                result = result.strip().lower()
                
                if result in ["chat", "task"]:
                    return result
                else:
                    print(f"[WARNING] 意图分类器返回了意外结果: {result}, 默认为chat")
                    return "chat"
                    
            except Exception as e:
                print(f"[ERROR] 意图分类失败: {e}, 默认为chat")
                return "chat"
        
        # 默认情况：短文本且无明确任务特征，判断为chat
        return "chat"
    
    def route_to_agent(self, intent: Literal["chat", "task"], user_input: str, mode_hint: str = None) -> Dict[str, Any]:
        """
        根据意图和模式提示选择合适的Agent
        
        Args:
            intent: 分类后的意图
            user_input: 用户输入
            mode_hint: 模式提示 ("fortune", "research", None)
            
        Returns:
            包含agent_name和相关信息的字典
        """
        if intent == "chat":
            return {
                "agent_name": "default_llm_agent",
                "reason": "检测到日常聊天意图，使用简单对话模式",
                "intent": "chat"
            }
        else:  # task
            # 根据mode_hint进行受限域路由
            if mode_hint == "fortune":
                # 命理模式的智能路由：在命理Agent和简单聊天间选择
                if any(keyword in user_input for keyword in ["命盘", "紫微", "八字", "风水", "算命", "占卜", "命理", "斗数", "生辰", "时辰"]):
                    return {
                        "agent_name": "fortune_agent",
                        "reason": "命理模式下检测到命理分析任务，使用专业命理Agent",
                        "intent": "task",
                        "task_type": "fortune"
                    }
                else:
                    # 命理模式下的非命理问题，回退到简单聊天
                    return {
                        "agent_name": "default_llm_agent",
                        "reason": "命理模式下检测到普通聊天，回退到简单对话模式",
                        "intent": "chat"
                    }
            
            elif mode_hint == "research":
                # 深度思考模式的智能路由：在研究Agent和通用RAG间选择
                if any(keyword in user_input for keyword in ["搜索", "查找", "研究", "调研", "深入分析", "综合分析", "网络搜索"]):
                    return {
                        "agent_name": "research_agent",
                        "reason": "深度思考模式下检测到研究分析任务，使用研究型Agent",
                        "intent": "task",
                        "task_type": "research"
                    }
                elif any(keyword in user_input for keyword in ["分析", "总结", "解释", "详细"]):
                    return {
                        "agent_name": "general_rag_agent",
                        "reason": "深度思考模式下检测到一般分析任务，使用通用RAG Agent",
                        "intent": "task",
                        "task_type": "general"
                    }
                else:
                    # 深度思考模式下的简单问题，回退到简单聊天
                    return {
                        "agent_name": "default_llm_agent",
                        "reason": "深度思考模式下检测到普通聊天，回退到简单对话模式",
                        "intent": "chat"
                    }
            
            else:
                # 无mode_hint的全局智能路由（auto模式）
                if any(keyword in user_input for keyword in ["命盘", "紫微", "八字", "风水", "算命", "占卜", "命理", "斗数", "生辰", "时辰", "排盘", "流年", "运势"]):
                    return {
                        "agent_name": "fortune_agent",
                        "reason": "检测到命理分析任务，使用专业命理Agent",
                        "intent": "task",
                        "task_type": "fortune"
                    }
                elif any(keyword in user_input for keyword in ["搜索", "查找", "研究", "调研", "分析"]):
                    return {
                        "agent_name": "research_agent",
                        "reason": "检测到研究分析任务，使用研究型Agent",
                        "intent": "task",
                        "task_type": "research"
                    }
                else:
                    return {
                        "agent_name": "general_rag_agent",
                        "reason": "检测到通用任务，使用通用RAG Agent",
                        "intent": "task",
                        "task_type": "general"
                    }


# 全局路由器实例
_router_instance = None

def get_intent_router() -> IntentRouter:
    """获取全局意图路由器实例（单例模式）"""
    global _router_instance
    if _router_instance is None:
        _router_instance = IntentRouter()
    return _router_instance


def classify_and_route(user_input: str, mode_hint: str = None) -> Dict[str, Any]:
    """
    便捷函数：分类用户输入并返回路由结果
    
    Args:
        user_input: 用户输入
        mode_hint: 模式提示 ("fortune", "research", None)
        
    Returns:
        路由结果字典
    """
    router = get_intent_router()
    intent = router.classify_intent(user_input)
    routing_result = router.route_to_agent(intent, user_input, mode_hint)
    
    mode_info = f" (模式: {mode_hint})" if mode_hint else ""
    print(f"[INTENT_ROUTER] 输入: {user_input[:50]}{'...' if len(user_input) > 50 else ''}{mode_info}")
    print(f"[INTENT_ROUTER] 意图: {intent} -> Agent: {routing_result['agent_name']}")
    print(f"[INTENT_ROUTER] 理由: {routing_result['reason']}")
    
    return routing_result
