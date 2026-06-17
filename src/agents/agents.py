from dataclasses import dataclass

from langgraph.graph.state import CompiledStateGraph
from langgraph.pregel import Pregel

from agents.marketing.router import router_agent
from agents.marketing.shield_router import shield_router_agent
from agents.samples.bg_task_agent.bg_task_agent import bg_task_agent
from agents.samples.chatbot import chatbot
from agents.samples.command_agent import command_agent
from agents.samples.interrupt_agent import interrupt_agent
from agents.samples.langgraph_supervisor_agent import langgraph_supervisor_agent

from agents.marketing.supervisor import supervisor
from agents.marketing.requirement import requirement
from agents.portfolio.ai_portfolio import ai_portfolio
from agents.requirement.requirement_QA import requirement_QA


from schema import AgentInfo

from core.settings import settings

DEFAULT_AGENT = settings.DEFAULT_AGENT

# Type alias to handle LangGraph's different agent patterns
# - @entrypoint functions return Pregel
# - StateGraph().compile() returns CompiledStateGraph
AgentGraph = CompiledStateGraph | Pregel


@dataclass
class Agent:
    description: str
    graph: AgentGraph


agents: dict[str, Agent] = {
    "marketing-assistant": Agent(description="An assets marketing assistant.", graph=supervisor),
    "agent-router": Agent(description="agent_router", graph=router_agent),
    "shield-router": Agent(description="A router with electronic fence protection.", graph=shield_router_agent),
    "requirement-assistant": Agent(description="A requirement assistant.", graph=requirement),
    "portfolio-recommendation-assistant": Agent(description="An assets portfolio recommendation assistant.", graph=ai_portfolio),
    "custom-requirement-assistant": Agent(description="A custom requirement assistant.", graph=requirement_QA),
    "chatbot": Agent(description="A simple chatbot.", graph=chatbot),
    "command-agent": Agent(description="A command agent.", graph=command_agent),
    "bg-task-agent": Agent(description="A background task agent.", graph=bg_task_agent),
    "langgraph-supervisor-agent": Agent(
        description="A langgraph supervisor agent", graph=langgraph_supervisor_agent
    ),
    "interrupt-agent": Agent(description="An agent the uses interrupts.", graph=interrupt_agent),
}


def get_agent(agent_id: str) -> AgentGraph:
    return agents[agent_id].graph


def get_all_agent_info() -> list[AgentInfo]:
    return [
        AgentInfo(key=agent_id, description=agent.description) for agent_id, agent in agents.items()
    ]
