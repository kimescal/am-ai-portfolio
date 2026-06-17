from langchain_core.runnables import RunnableConfig

from .base import TemplateModule


class EndTemplate(TemplateModule):
    """报告结尾模块"""

    use_llm = False  
    
    def fetch_data(self, args: dict) -> dict:
        # 结尾模块不需要获取特定数据，返回空字典
        return {}

    def get_template_chunk(self, data: dict,config:RunnableConfig) -> dict[str, str]:
        # 直接返回结尾模板，包含联系信息
        template = {
            "prompt": """
##更多信息请联系企微数字员工"AI资管营销助理"
"""
        }
        return template