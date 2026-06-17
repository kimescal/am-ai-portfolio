
import json

from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, ToolMessage, AIMessage
from langgraph.graph import END, START, StateGraph

from core import get_model, settings
from agents.portfolio.state import StrategyFilter, PortfolioSelectionState

def load_strategy_hierarchy():
    try:
        with open('data/strategy_hierarchy.md', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ""

SYSTEM_PROMPT = """
# 核心职责
分析用户需求, 提取用户感兴趣的策略类型

# 限制
- 所有策略均来自背景知识, 严禁发散
- 只返回最细粒度策略, 比如匹配到三级策略, 则返回三级策略即可
- 若匹配到多个策略, 则应都返回, 有特殊说明的除外

# 背景知识
## 策略层级:
- 一级策略(category_base) > 二级策略(category) > 三级策略(strategy)

# 分析流程(严格遵守, 若匹配到结果则忽略后续步骤)
1. 关键词匹配: 若包含以下关键词, 则直接使用对应的策略
  1. 固收+国债期货: [{"category": "信用债"}, {"strategy": "固收+利率衍生品"}]
  2. 现金增强 / 类货币 / 流动性管理: [{"category": "类货币"}, {"strategy": "现金增强FOF"}]
  3. 纯债 / 固收产品 / 存款替代: [{"category_base": "固定收益"}]
  4. 固收+ / 固收增强: [{"category": "固收组合"}, {"category": "偏债组合"}]
  5. 含权债 / 转债: [{"category": "可转债"}]
  6. 权益: [{"category": "全市场-成长"}, {"category": "全市场-均衡"}, {"category": "全市场-价值"}, {"category": "偏股组合"}]
2. 严格匹配: 策略需求字眼严格匹配策略名称, 匹配优先级: 一级 > 二级 > 三级
3. 近似匹配: 可根据经验推荐最接近的策略集, 不超过3个

# 策略完整列表
{full_strategy_hierarchy}

# 示例
- 输入: 我想投现金增强产品
  - 输出: [{"category": "类货币"}, {"strategy": "现金增强FOF"}]
- 输入: 我想投权益产品
  - 输出: [{"category": "全市场-成长"}, {"category": "全市场-均衡"}, {"category": "全市场-价值"}, {"category": "偏股组合"}]
- 输入: 我想投资固收组合产品
  - 输出: [{"category": "固收组合"}]
# 反面示例
- 输入: 我想投资固收组合产品
  - 匹配到一级策略: 固定收益 下 二级策略: 固收组合
  - 输出: [{"category_base": "固定收益"}, {"category": "固收组合"}]
  - 说明: 结果不应包含二级策略所属一级策略, 只输出最细粒度策略
""".replace("{full_strategy_hierarchy}", load_strategy_hierarchy())

def strategy_judge(state: PortfolioSelectionState, config: RunnableConfig):
    # llm = llm_large.with_structured_output(StrategyFilter).with_config(tool_choice="any")
    # response = llm.invoke([SystemMessage(SYSTEM_PROMPT)] + state["messages"], \
    #     config=dict(tags=["strategy_judger"]))
    # return {"messages": [AIMessage(response.model_dump_json() if response else "{}", agent="strategy_judge")]}

    response = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL)) \
        .invoke([SystemMessage(SYSTEM_PROMPT)] + state["messages"], config)
    content = json.loads(response.content)
    if content and len(content) > 0:
        content = {"strategies": content}
        return {"strategy_filter": StrategyFilter(**content), "messages":[AIMessage(response.content)]}

    return {"strategy_filter": None}


builder = StateGraph(PortfolioSelectionState)
builder.add_node("strategy_judge", strategy_judge) \
    .add_edge(START, "strategy_judge") \
    .add_edge("strategy_judge", END)

strategy_judger = builder.compile()