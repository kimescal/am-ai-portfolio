from typing import Optional, List, Dict
from pydantic import BaseModel

from langgraph.graph import MessagesState

class StrategyItem(BaseModel):
    category_base: Optional[str] = None
    category: Optional[str] = None
    strategy: Optional[str] = None

class StrategyFilter(BaseModel):
    strategies: Optional[List[StrategyItem]] = None

class PortfolioFilter(BaseModel):
    full_names: Optional[List[str]]  = None
    investor_names: Optional[List[str]] = None
    risk_level: Optional[int] = None

class MarketDataBenchmark(BaseModel):
    name: Optional[str] = None
    rate: Optional[float] = None

class PortfolioSelectionState(MessagesState):
    strategy_filter: StrategyFilter
    portfolio_filter: PortfolioFilter
    market_data_benchmark: MarketDataBenchmark