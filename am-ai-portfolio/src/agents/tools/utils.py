import logging
import json
from typing import List, Dict, Any
from io import StringIO
import pandas as pd

from core import settings
from agents.tools import sql_query

logger = logging.getLogger(__name__)

def get_table_columns_info(table_name: str, with_comment: bool = True, ignore_cols: List[str] = [], col_comment:dict[str,str] = {}) -> str:
    """
    Get column information for specified table (including field types and optional comments)

    Args:
        table_name: table name
        with_comment: whether to include column comments in the output, defaults to False
        ignore_cols: list of column names to ignore, defaults to None

    Returns:
        Formatted column information string:
        - If with_comment=False: column_name(type),column_name(type),...
        - If with_comment=True: column_name(type, comment),column_name(type, comment),...
        - If comment does not exist, format: column_name(type)
    """
    try:
        if settings.OCEANBASE_ENABLED:
            # Production environment: get from OceanBase
            sql = f"""
            SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE{', COLUMN_COMMENT' if with_comment else ''}
            FROM information_schema.COLUMNS
            WHERE TABLE_NAME = '{table_name}'
            AND TABLE_SCHEMA = DATABASE()
            ORDER BY ORDINAL_POSITION
            """

            result = sql_query.invoke({"query": sql})
            columns_data = json.loads(result if isinstance(result, str) else str(result))
            columns_info = []

            # Type mapping (MySQL/OceanBase to simplified types)
            type_mapping = {
                'int': 'int',
                'bigint': 'int',
                'varchar': 'str',
                'char': 'str',
                'text': 'str',
                'datetime': 'datetime',
                'timestamp': 'datetime',
                'date': 'datetime',
                'decimal': 'float',
                'float': 'float',
                'double': 'float',
                'tinyint': 'int',
                'smallint': 'int',
                'mediumint': 'int'
            }

            for col in columns_data:
                col_name = col['COLUMN_NAME']
                if col_name in ignore_cols:
                    continue  # Skip ignored columns

                data_type = col['DATA_TYPE'].lower()
                col_type = type_mapping.get(data_type, 'str')

                if with_comment:
                    comment = (col.get('COLUMN_COMMENT', '') + f" {col_comment.get(col_name, '')}").strip()
                    columns_info.append(f"{col_name}({col_type}{f',{comment}' if comment else ''})")
                else:
                    columns_info.append(f"{col_name}({col_type})")
            return ",".join(columns_info)
        else:
            result = sql_query.invoke({"query": f"SELECT * FROM {table_name} LIMIT 1"})
            if isinstance(result, str) and result.startswith("Error"):
                raise Exception(f"Cannot query table {table_name}")

            try:
                df = pd.read_json(StringIO(result) if isinstance(result, str) else result)

                columns_info = []

                # Type mapping
                type_mapping = {
                    'int64': 'int',
                    'float64': 'float',
                    'object': 'str',
                    'bool': 'bool',
                    'datetime64[ns]': 'datetime',
                    'datetime64[ns, UTC]': 'datetime'
                }

                for col in df.columns:
                    if col in ignore_cols:
                        continue  # Skip ignored columns

                    dtype = str(df[col].dtype)
                    col_type = type_mapping.get(dtype, 'str')
                    comment = col_comment.get(col, '').strip() if with_comment else ''
                    columns_info.append(f"{col}({col_type}{f',{comment}' if comment else ''})")

                return ",".join(columns_info)
            except Exception as e:
                logger.warning(f"Failed to parse CSV column information: {e}")
                raise
    except Exception as e:
        logger.error(f"Failed to get column information for table {table_name}: {e}")
        return ""
