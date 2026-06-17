from typing import List
from decimal import Decimal
from langchain.tools import tool
from pydantic import BaseModel, Field


class SumNumbersInput(BaseModel):
    """Input schema for sum_numbers tool.
    """
    numbers: List[float] = Field(
        ...,
        description=(
            "A list of numeric values to be summed. "
        ),
    )


@tool("sum_numbers", args_schema=SumNumbersInput)
def sum_numbers(numbers: List[float]) -> str:
    """
    Sum a list of numbers and return the total.

    SUM numbers tool usage:
    - The agent MUST NOT perform manual addition or total calculation in reasoning or response.
    - When the user's question implies totals, such as:"total", "sum", "overall", "combined", MUST call the `sum_numbers` tool.
    - If values come from SQL, RAG, or other agents, first extract numeric values, then pass them to `sum_numbers(numbers=[...])`.
    - The result from `sum_numbers` should be used directly without modification.
    """
    total = sum(Decimal(str(x)) for x in numbers)
    return str(total)
