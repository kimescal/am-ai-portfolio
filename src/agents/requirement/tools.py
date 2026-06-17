import pandas as pd
from pandasql import sqldf
import os
import json
import pymysql
from langchain_core.tools import tool
from core.settings import settings
from datetime import datetime

@tool
def query_requirement_csv(sql_query: str) -> str:
    """
    使用给定的SQL查询CSV数据并返回结果。

    Args:
        sql_query (str): SQL查询字符串。

    Returns:
        str: 查询结果的JSON字符串。
    """
    csv_file_path = None
    current_dir = os.path.dirname(__file__)
    for i in range(4):
        potential_path = os.path.join(current_dir, 'data', 'sale_cust_invest_requirement.csv')
        if os.path.exists(potential_path):
            csv_file_path = potential_path
            break
        current_dir = os.path.abspath(os.path.join(current_dir, '..'))

    if not csv_file_path:
        return "Error: CSV file not found in parent directories."

    try:
        # 读取CSV文件，尝试多种编码方式
        try:
            sale_cust_invest_requirement = pd.read_csv(csv_file_path, encoding='utf-8')
        except UnicodeDecodeError:
            try:
                sale_cust_invest_requirement = pd.read_csv(csv_file_path, encoding='gbk')
            except UnicodeDecodeError:
                sale_cust_invest_requirement = pd.read_csv(csv_file_path, encoding='latin1')

        sale_cust_invest_requirement['create_time'] = pd.to_datetime(sale_cust_invest_requirement['create_time'])
        sale_cust_invest_requirement['update_time'] = pd.to_datetime(sale_cust_invest_requirement['update_time'])

        # 使用pandasql执行SQL查询
        result_df = sqldf(sql_query, locals())

        # 将结果转换为JSON字符串并返回
        return result_df.to_json(orient="records", force_ascii=False)
    except Exception as e:
        return f"Error executing SQL query: {e}"

@tool
def query_requirement_ob(sql_query: str) -> str:
    """
    使用给定的SQL查询OceanBase数据库并返回结果。

    Args:
        sql_query (str): SQL查询字符串。

    Returns:
        str: 查询结果的JSON字符串。
    """
    try:
        # 这里需要添加OceanBase连接和查询逻辑
        # 示例代码:
        conn = pymysql.connect(
            host=settings.OCEANBASE_HOST,
            port=settings.OCEANBASE_PORT,
            user=settings.OCEANBASE_USER,
            password=settings.OCEANBASE_PASSWORD.get_secret_value() if settings.OCEANBASE_PASSWORD else None,
            database=settings.OCEANBASE_DB
        )
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute(sql_query)
        result = cursor.fetchall()
        conn.close()

        # Convert datetime objects to strings for JSON serialization
        for row in result:
            for key, value in row.items():
                if isinstance(value, datetime):
                    row[key] = value.isoformat()

        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return f"Error executing OceanBase query: {e}"

if __name__ == "__main__":
    from agents.tools import sql_query
    
    # 简单的查询示例
    sql = "SELECT * FROM sale_cust_invest_requirement limit 10"
    print(f"Executing SQL: {sql}")
    result = sql_query.invoke(sql)
    print(f"Result: {result[:500]}...") # 打印前500个字符