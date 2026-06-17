from langchain_core.messages.utils import trim_messages,count_tokens_approximately
from langmem.short_term import SummarizationNode

from core.llm import get_model
from core.settings import settings

def trim_history(state):
    trimmed_messages = trim_messages(
        state["messages"],
        strategy="last",
        token_counter=count_tokens_approximately,
        max_tokens=settings.HISTORY_MAX_TOKENS,
        start_on="human",
        end_on=("human", "tool"),
    )
    # You can return updated messages either under `llm_input_messages` or
    # `messages` key (see the note below)
    return {"llm_input_messages": trimmed_messages}

summary_history = SummarizationNode(
    token_counter=count_tokens_approximately,
    model=get_model(settings.HISTORY_SUMMARY_MODEL),
    max_tokens=settings.HISTORY_MAX_TOKENS,
    max_summary_tokens=8192,
    output_messages_key="llm_input_messages",
)
