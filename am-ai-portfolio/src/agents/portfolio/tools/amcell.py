import os
from pathlib import Path
import requests
from typing import Dict, Any, Optional, List
import datetime

from langchain_core.tools import tool

AMCELL_ADDR = "http://amcell-test.citicsinfo.com"

def portfolio_filter(
    strategies: Optional[List[Dict[str, str]]] = None,
    investor_names: Optional[List[str]] = None,
    full_names: Optional[List[str]] = None,
    risk_level: Optional[int] = None,
    # page: int = 1,
    # limit: int = 0,
    # ctx: Context = None
) -> List[Dict[str, Any]]:
    """使用信息过滤portfolio, 该函数用于根据给定的过滤条件筛选并返回portfolio基本信息.

    Args:
    - strategies (List[Dict[str, str]], optional): 策略过滤条件列表. 每个元素是一个字典{category_base:'', category:'', strategy:''}. 默认为None.
      匹配时按照strategy-category-category_base的优先级检查是否有值且非空，如果有就不考虑后面的策略层级。数组中的元素之间是OR关系。
    - investor_names (List[str], optional): 投资者名称列表. 默认为None.
    - full_names (List[str], optional): 产品全称列表. 默认为None.
    - risk_level (int, optional): 风险等级. 默认为None.
    # - page (int, optional): 页数. 默认为1.
    # - limit (int, optional): 每页数量. 默认为0.

    Returns:
    - 包含portfolio基本信息和近一年业绩的JSON字符串
    """
    # columns = ["id", "prtfl_sim_nm"]
    columns = ["id", "prtfl_sim_nm", "prtfl_ful_nm", "category_base_type", "category_name", "strategy_name", "start_dt",
        "aum", "acct_type", "base_line", "strategy_minimum_risk_level", "performance_investor_names"]

    sql_parts = []
    # 根据策略构建过滤条件
    if strategies:
        strategy_conditions = []
        for strategy_item in strategies:
            strategy = strategy_item.get('strategy')
            category = strategy_item.get('category')
            category_base = strategy_item.get('category_base')

            # 按照strategy-category-category_base的优先级检查
            if strategy and strategy.strip():
                # 如果strategy中没有摊余字眼，加上摊余 not in strategy过滤条件，如果有摊余字眼则正常过滤
                if '摊余' not in strategy:
                    strategy_conditions.append(f"strategy_name = '{strategy}' AND strategy_name NOT LIKE '%摊余%'")
                else:
                    strategy_conditions.append(f"strategy_name = '{strategy}'")
            else:
                if category and category.strip():
                    strategy_conditions.append(f"category_name = '{category}' AND strategy_name NOT LIKE '%摊余%'")
                elif category_base and category_base.strip():
                    strategy_conditions.append(f"category_base_type = '{category_base}' AND strategy_name NOT LIKE '%摊余%'")

        # 如果有策略条件，将它们以OR连接
        if strategy_conditions:
            sql_parts.append(f"({' OR '.join(strategy_conditions)})")

    if investor_names:
        like_conditions = [f"performance_investor_names LIKE '%{name}%'" for name in investor_names]
        sql_parts.append(f"({' OR '.join(like_conditions)})")
    if full_names:
        like_conditions = [f"prtfl_ful_nm LIKE '%{name}%'" for name in full_names]
        sql_parts.append(f"({' OR '.join(like_conditions)})")
    if risk_level is not None:
        sql_parts.append(f"strategy_minimum_risk_level <= {risk_level}")
        # sql_parts.append(f"{risk_level} <= strategy_maximum_risk_level")

    where_clause = " WHERE " + " AND ".join(sql_parts) if sql_parts else ""
    columns_clause = ", ".join(columns)
    # limit_clause = f" LIMIT {limit}" if limit > 0 else ""
    # offset_clause = f" OFFSET {(page - 1) * limit}" if limit > 0 and page > 1 else ""

    # sql_str = f"SELECT {columns_clause} FROM v_portfolio_wide{where_clause}{limit_clause}{offset_clause}"
    sql_str = f"SELECT {columns_clause} FROM v_portfolio_wide{where_clause}"
    # if ctx:
    #     await ctx.debug(f"Generated SQL: {sql_str}")

    try:
        payload = {
            "sql_str": sql_str
        }
        response = requests.post(
            f"{AMCELL_ADDR}/api/v1/portfolio/sql",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        portfolios = response.json().get('data', [])

        # 获取近一年日期范围
        end_dt = datetime.date.today().strftime('%Y-%m-%d')
        start_dt = (datetime.date.today() - datetime.timedelta(days=365)).strftime('%Y-%m-%d')

        # 获取产品ID列表
        portfolio_ids = [p['id'] for p in portfolios]

        # 获取绩效数据
        if portfolio_ids:
            performance_data = portfolio_performance(
                portfolio_id_list=portfolio_ids,
                start_dt=start_dt,
                end_dt=end_dt
            ).get('data', [])
            # 将绩效数据合并到portfolios列表中
            performance_map = {item['portfolio_id']: {k: v for k, v in item.items() if k not in ['start_dt', 'end_dt']} for item in performance_data}

            for p in portfolios:
                p['recent_1y_perf'] = performance_map.get(p['id'], {})

        # 收集所有产品的绩效指标
        all_volatilities = [p['recent_1y_perf']['volatility'] for p in portfolios if 'recent_1y_perf' in p and 'volatility' in p['recent_1y_perf'] and p['recent_1y_perf']['volatility'] is not None]
        all_max_drawdowns = [p['recent_1y_perf']['max_drawdown'] for p in portfolios if 'recent_1y_perf' in p and 'max_drawdown' in p['recent_1y_perf'] and p['recent_1y_perf']['max_drawdown'] is not None]
        all_sharpe_ratios = [p['recent_1y_perf']['sharpe_ratio'] for p in portfolios if 'recent_1y_perf' in p and 'sharpe_ratio' in p['recent_1y_perf'] and p['recent_1y_perf']['sharpe_ratio'] is not None]
        all_return_rates = [p['recent_1y_perf']['return_rate'] for p in portfolios if 'recent_1y_perf' in p and 'return_rate' in p['recent_1y_perf'] and p['recent_1y_perf']['return_rate'] is not None]

        # 对绩效指标进行排序, 用于后续排名计算
        all_volatilities.sort()
        all_max_drawdowns.sort()
        all_sharpe_ratios.sort(reverse=True)
        all_return_rates.sort(reverse=True)

        # 计算得分并排序
        scored_portfolios = []
        for p in portfolios:
            score = calculate_score(p, all_volatilities, all_max_drawdowns, all_sharpe_ratios, all_return_rates)
            scored_portfolios.append({'portfolio': p, 'score': score})

        # 按得分降序排序
        scored_portfolios.sort(key=lambda x: x['score'], reverse=True)

        top_portfolios = [item['portfolio'] for item in scored_portfolios[:10]]

        return top_portfolios
    except requests.exceptions.Timeout:
        raise TimeoutError("请求超时, 请稍后重试")
    except requests.exceptions.RequestException as e:
        raise requests.exceptions.RequestException(f"请求失败: {str(e)}")
    except ValueError as e:
        raise ValueError(f"解析响应数据失败: {str(e)}")

def calculate_score(portfolio: Dict[str, Any], all_volatilities: List[float], all_max_drawdowns: List[float], all_sharpe_ratios: List[float], all_return_rates: List[float]) -> float:
    """
    根据图片中的逻辑计算portfolio的得分.

    Args:
    - portfolio (Dict[str, Any]): 包含portfolio信息和绩效数据的字典.

    Returns:
    - float: 计算出的得分.
    """
    score = 0
    performance = portfolio.get('recent_1y_perf', {})

    # 运作时长 (假设start_dt在portfolio信息中)
    start_dt_str = portfolio.get('start_dt')
    if start_dt_str:
        start_dt = datetime.datetime.strptime(start_dt_str, '%Y-%m-%d').date()
        today = datetime.date.today()
        delta = today - start_dt
        if delta.days >= 3 * 365:
            score += 100 * 0.1
        elif delta.days >= 1 * 365:
            score += 80 * 0.1
        elif delta.days >= 6 * 30:
            score += 40 * 0.1
        else:
            score += 0 * 0.1

    # 合意规模 (假设aum在portfolio信息中)
    aum = portfolio.get('aum', 0)
    if aum >= 500000000:
        score += 100 * 0.1
    else:
        score += 0 * 0.1

    # 近一年波动率 (假设annualized_volatility在performance中)
    volatility = performance.get('volatility')
    if volatility is not None and len(all_volatilities) > 0:
        # 波动率越低越好
        rank = sorted(all_volatilities).index(volatility)
        percentile = rank / len(all_volatilities)
        if percentile <= 0.2:
            score += 100 * 0.2
        elif percentile <= 0.4:
            score += 60 * 0.2
        else:
            score += 0 * 0.2

    max_drawdown = performance.get('max_drawdown')
    if max_drawdown is not None and len(all_max_drawdowns) > 0:
        # 最大回撤越低越好
        rank = sorted(all_max_drawdowns).index(max_drawdown)
        percentile = rank / len(all_max_drawdowns)
        if percentile <= 0.2:
            score += 100 * 0.2
        elif percentile <= 0.4:
            score += 60 * 0.2
        else:
            score += 0 * 0.2

    sharpe_ratio = performance.get('sharpe_ratio')
    if sharpe_ratio is not None and len(all_sharpe_ratios) > 0:
        # 夏普比越高越好
        rank = sorted(all_sharpe_ratios, reverse=True).index(sharpe_ratio)
        percentile = rank / len(all_sharpe_ratios)
        if percentile <= 0.2:
            score += 100 * 0.2
        elif percentile <= 0.4:
            score += 60 * 0.2
        else:
            score += 0 * 0.2

    return_rate = performance.get('return_rate')
    if return_rate is not None and len(all_return_rates) > 0:
        # 累计收益越高越好
        rank = sorted(all_return_rates, reverse=True).index(return_rate)
        percentile = rank / len(all_return_rates)
        if percentile <= 0.2:
            score += 100 * 0.2
        elif percentile <= 0.4:
            score += 60 * 0.2
        else:
            score += 0 * 0.2

    return score

def portfolio_info(
    portfolio_id_list: List[str],
    # ctx: Context = None
) -> List[Dict[str, Any]]:
    """
    获取portfolio详细信息.

    Args:
    - portfolio_id_list (List[str]): portfolio的ID列表.

    Returns:
    - 包含portfolio详细信息及运作以来绩效表现的JSON字符串列表.
    """
    # 构建IN查询, 确保ID用单引号括起来
    ids_str = ', '.join(f"'{pid}'" for pid in portfolio_id_list)
    sql_str = f"SELECT * FROM v_portfolio_wide WHERE id IN ({ids_str})"

    # if ctx:
    #     ctx.debug(f"Generated SQL: {sql_str}")

    try:
        payload = {
            "sql_str": sql_str
        }
        response = requests.post(
            f"{AMCELL_ADDR}/api/v1/portfolio/sql",
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        portfolios = response.json().get('data', [])

        # 获取产品ID列表
        portfolio_ids = [p['id'] for p in portfolios]

        # 获取绩效数据
        if portfolio_ids:
            # 计算当前日期
            end_dt_str = datetime.date.today().strftime('%Y-%m-%d')
            # 遍历每个portfolio, 获取其成立以来的绩效数据
            for p in portfolios:
                start_dt_str = p.get('start_dt')
                if start_dt_str:
                    performance_data = portfolio_performance(
                        portfolio_id_list=[p['id']],
                        start_dt=start_dt_str,
                        end_dt=end_dt_str
                    )
                    if performance_data and performance_data.get('data'):
                        p['from_start_perf'] = performance_data['data'][0]
                        # 计算运作以来年化收益
                        from_start_return_rate = p['from_start_perf'].get('return_rate')
                        start_dt_str = p.get('start_dt')
                        if from_start_return_rate is not None and start_dt_str:
                            start_dt = datetime.datetime.strptime(start_dt_str, '%Y-%m-%d').date()
                            today = datetime.date.today()
                            delta_days = (today - start_dt).days
                            if delta_days > 0:
                                # 年化收益率 = (1 + 累计收益率)^(365 / 运作天数) - 1
                                annualized_return = (1 + from_start_return_rate)**(365 / delta_days) - 1
                                p['from_start_perf']['annualized_return'] = annualized_return

        return portfolios
    except requests.exceptions.Timeout:
        raise TimeoutError("请求超时, 请稍后重试")
    except requests.exceptions.RequestException as e:
        raise requests.exceptions.RequestException(f"请求失败: {str(e)}")
    except ValueError as e:
        raise ValueError(f"解析响应数据失败: {str(e)}")

def portfolio_performance(
    portfolio_id_list: List[str],
    start_dt: str,
    end_dt: str,
) -> str:
    """
    获取组合绩效信息.

    Args:
    - portfolio_id_list(List[str], optional): 组合ID列表.
    - start_dt(str, 格式为YYYY-MM-DD, optional): 开始日期.
    - end_dt(str, 格式为YYYY-MM-DD, optional): 结束日期.

    Returns:
    - str: 以JSON格式返回的组合绩效信息.
    """
    try:
        payload = {
            'portfolio_id_list': portfolio_id_list,
            'start_dt': start_dt,
            'end_dt': end_dt,
        }
        response = requests.post(
            f'{AMCELL_ADDR}/api/v1/portfolio/performance',
            json=payload,
            timeout=10
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        raise TimeoutError('请求超时, 请稍后重试')
    except requests.exceptions.RequestException as e:
        raise requests.exceptions.RequestException(f'请求失败: {str(e)}')
    except ValueError as e:
        raise ValueError(f'解析响应数据失败: {str(e)}')
