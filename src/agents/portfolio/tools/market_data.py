from typing import Dict, Any, Optional, List, TypedDict

from langchain_core.tools import tool

@tool
def market_data(indicators: list[str] | None = None) -> dict[str, dict[str, str | float]]:
    """获取金融市场常见参考收益率.

    Args:
    - indicators (list[str], optional): 需要返回的指标列表. 如果为 None,则返回所有指标.

    indicators可选值如下:
    # 存款类:
    - demand_deposit: 活期存款
    - time_deposit_1y: 一年期定期存款
    - time_deposit_3y: 三年期定期存款
    - time_deposit_5y: 五年期定期存款
    # 国债类:
    - gov_bond_1y: 一年期国债
    - gov_bond_3y: 三年期国债
    - gov_bond_5y: 五年期国债
    - gov_bond_10y: 十年期国债
    # 货币市场:
    - money_fund: 货币基金
    - shibor_1d: 隔夜Shibor
    - shibor_3m: 三个月Shibor
    # 理财产品:
    - wealth_low_risk: 低风险理财产品
    - wealth_medium_risk: 中等风险理财产品
    # 贷款基准:
    - lpr_1y: 一年期LPR
    - lpr_5y: 五年期LPR

    Returns:
    - 收益率数据字典.
    """
    all_data = {
        ### 存款类
        "demand_deposit": {
            "name": "活期存款",
            "rate": 0.25,
            "term": "活期",
            "risk_level": "无风险",
            "description": "银行活期存款基准利率"
        },
        "time_deposit_1y": {
            "name": "一年期定期存款",
            "rate": 1.50,
            "term": "1年",
            "risk_level": "无风险",
            "description": "银行一年期定期存款基准利率"
        },
        "time_deposit_3y": {
            "name": "三年期定期存款",
            "rate": 2.00,
            "term": "3年",
            "risk_level": "无风险",
            "description": "银行三年期定期存款基准利率"
        },
        "time_deposit_5y": {
            "name": "五年期定期存款",
            "rate": 2.50,
            "term": "5年",
            "risk_level": "无风险",
            "description": "银行五年期定期存款基准利率"
        },
        ### 国债类
        "gov_bond_1y": {
            "name": "一年期国债",
            "rate": 2.00,
            "term": "1年",
            "risk_level": "无风险",
            "description": "一年期国债收益率"
        },
        "gov_bond_3y": {
            "name": "三年期国债",
            "rate": 2.50,
            "term": "3年",
            "risk_level": "无风险",
            "description": "三年期国债收益率"
        },
        "gov_bond_5y": {
            "name": "五年期国债",
            "rate": 3.00,
            "term": "5年",
            "risk_level": "无风险",
            "description": "五年期国债收益率"
        },
        "gov_bond_10y": {
            "name": "十年期国债",
            "rate": 3.50,
            "term": "10年",
            "risk_level": "无风险",
            "description": "十年期国债收益率"
        },
        ### 货币市场
        "money_fund": {
            "name": "货币基金",
            "rate": 2.00,
            "term": "7天",
            "risk_level": "低风险",
            "description": "货币基金7日年化收益率"
        },
        "shibor_1d": {
            "name": "隔夜Shibor",
            "rate": 1.80,
            "term": "1天",
            "risk_level": "低风险",
            "description": "上海银行间同业拆放利率(隔夜)"
        },
        "shibor_3m": {
            "name": "三个月Shibor",
            "rate": 2.50,
            "term": "3个月",
            "risk_level": "低风险",
            "description": "上海银行间同业拆放利率(3个月)"
        },
        ### 理财产品
        "wealth_low_risk": {
            "name": "低风险理财产品",
            "rate": 3.50,
            "term": "3-6个月",
            "risk_level": "低风险",
            "description": "银行低风险理财产品参考收益率"
        },
        "wealth_medium_risk": {
            "name": "中等风险理财产品",
            "rate": 4.50,
            "term": "6-12个月",
            "risk_level": "中等风险",
            "description": "银行中等风险理财产品参考收益率"
        },
        ### 贷款基准
        "lpr_1y": {
            "name": "一年期LPR",
            "rate": 3.65,
            "term": "1年",
            "risk_level": "基准利率",
            "description": "贷款市场报价利率(1年期)"
        },
        "lpr_5y": {
            "name": "五年期LPR",
            "rate": 4.30,
            "term": "5年",
            "risk_level": "基准利率",
            "description": "贷款市场报价利率(5年期)"
        }
    }

    if indicators is None:
        return [{"name": v["name"], "rate": v["rate"]} for k, v in all_data.items()]

    return [{"name": v["name"], "rate": v["rate"]} for k, v in all_data.items() if k in indicators]
    # return {k: v for k, v in all_data.items() if k in indicators}
