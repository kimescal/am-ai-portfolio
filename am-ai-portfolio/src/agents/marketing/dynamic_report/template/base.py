from abc import ABC, abstractmethod

from langchain_core.runnables import RunnableConfig


class TemplateModule(ABC):

    title_name = "模板名称"
    use_llm = True  

    @abstractmethod
    def fetch_data(self, args: dict) -> dict:
        pass

    @abstractmethod
    def get_template_chunk(self,data:dict,config:RunnableConfig) -> str:
        pass
