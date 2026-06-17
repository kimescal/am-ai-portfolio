import logging
import json
import requests
import inspect

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from core.settings import settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class QueryRagSchema(BaseModel):
    db_name: str = Field(
        description="Specify which API key to use. Options: 'requirement', 'portfolio'."
    )
    input: str = Field(
        description="【核心指令】请仅提取纯净的产品或客户名称。绝对不能包含用户的提问意图词汇（如'费率'、'赎回交收'、'需求'等必须剔除！）。"
    )

# 2. 将 Schema 绑定到工具，替换掉原本依赖注释(docstring)的解析方式
@tool(args_schema=QueryRagSchema)
def query_rag_api(input: str, db_name: str,config: RunnableConfig) -> str:
    """
    - When sql query result is empty, use RAG and list all similar PRTFL_SIM_NM mentioned.
    - If RAG returns no permission error, follow the same permission handling as sql_query.
    - Call knowledge base RAG API for querying.
    """
    logger.info(f"Calling RAG with db_name={db_name}: {input}")
    try:
        # 获取配置（所有验证在 get_rag_config 内完成）
        rag_config = settings.get_rag_config(db_name = db_name)

        headers = {
            "Apikey": rag_config["api_key"].get_secret_value(),
            "Content-Type": "application/json"
        }

        payload = {
            "InputData": json.dumps({"input": str(input)}),
            "UserID": "321"
        }

        response = requests.post(rag_config["url"], headers=headers, json=payload)

        logger.info(f"RAG API Response - Status: {response.status_code}")

        if response.status_code == 200:
            data = json.loads(response.text)
            answer = data.get('answer', data)
            
            # Check if response contains permission denied message
            answer_str = json.dumps(answer, indent=2, ensure_ascii=False)
            if "无权限" in answer_str:
                logger.info("Permission denied detected in RAG response")
                # Set user_id to None to bypass permission filter
                if config and "configurable" in config:
                    config["configurable"]["user_id"] = None
                    logger.info("Set user_id to None in config to bypass permission filter")
                return json.loads(answer_str)['output'].split(",")
            else:
                return answer_str
        else:
            error_msg = f"API request failed with status code: {response.status_code}"
            logger.error(f"RAG API Error: {error_msg}")
            return error_msg

    except Exception as e:
        error_msg = f"Error calling RAG API: {e}"
        logger.error(f"RAG API Exception: {error_msg}")
        return error_msg

if __name__ == "__main__":
    from tools.rag_api import sql_query

    # Simple query example
    sql = "SELECT * FROM sale_cust_invest_requirement limit 10"
    print(f"Executing SQL: {sql}")
    result = sql_query.invoke(sql)
    print(f"Result: {result[:500]}...") # Print first 500 characters

    # Test RAG API call
    test_query = "信银理财的拜访记录"
    print(f"\nTesting RAG API with query: {test_query}")
    # 必须提供db_name参数
    rag_result = query_rag_api.invoke({"input": test_query, "db_name": "dynamic"})
    print(f"RAG Result: {rag_result[:500]}...")  # Print first 500 characters