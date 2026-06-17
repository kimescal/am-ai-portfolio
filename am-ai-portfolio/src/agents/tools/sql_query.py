from datetime import date
import logging
import pandas as pd
from pandasql import sqldf
import sqlalchemy as sa
import os
import json
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
from core.settings import settings
from agents.tools.sql_permission import permission_checker

logger = logging.getLogger(__name__)

@tool
def sql_query(query: str, config: RunnableConfig, bypass_permission: bool = False) -> str:
    """
    Query data using given SQL and return results.

    SQL tool usage:
    - SQL statements must comply with MySQL syntax.
    - Use 'like '%name%'' for any name-related query conditions.
    - When querying by strategy and uncertain about strategy levels, include all three strategy levels in query conditions.
    - Fields should be added depending on the context.
    - If the query result is empty, it may be due to insufficient permissions to view the relevant data.

    Args:
        query (str): SQL query string
        config (RunnableConfig): Configuration containing user_id
        bypass_permission (bool): If True, skip permission check. Default is False.

    Returns:
        str: JSON string of query results
    """
    logger.debug(f"Executing SQL query: {query}")

    dangerous_keywords = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE', 'EXECUTE', 'GRANT', 'REVOKE']
    sql_upper = query.strip().upper()
    if any(sql_upper.startswith(keyword) for keyword in dangerous_keywords):
        return json.dumps({"error": "danger SQL operation"}, ensure_ascii=False)
    
    # Apply WHERE conditions wrapping
    query = wrap_where_conditions(query)

    # Skip permission filter if bypass_permission is True
    if bypass_permission:
        logger.debug("Skipping permission filter: bypass_permission=True")
    elif config:
        user_id = config["configurable"].get("user_id", None) if config["configurable"] else None

        if user_id:
            query = permission_checker.apply_permission_filter(query, user_id)       
            logger.info(f"Modified query with permission filter: {query}")
        else:
            logger.debug("Skipping permission filter: user_id is None or empty")
    else:
        logger.debug("Skipping permission filter: no config provided")

    return _query_from_ob(query) if settings.OCEANBASE_ENABLED else _query_from_csv(query)


def wrap_where_conditions(query: str) -> str:
        """
        Wrap the WHERE clause conditions in parentheses, ensuring main SQL clauses remain outside.
        
        Args:
            query: Original SQL query string
            
        Returns:
            Modified SQL query with WHERE conditions wrapped in parentheses if they exist
        """
        # Remove any trailing semicolons
        query = query.rstrip().rstrip(';')
        
        # Convert to uppercase for case-insensitive matching
        sql_upper = query.upper()
        
        # Check if WHERE clause exists
        where_index = sql_upper.find(' WHERE ')
        if where_index == -1:
            return query
        
        # Get the part after WHERE clause
        after_where = query[where_index + 7:]
        
        # List of main SQL clauses that should be placed outside the parentheses
        main_clauses = [
            ' ORDER BY ', ' GROUP BY ', ' HAVING ', ' LIMIT ', 
            ' OFFSET ', ' UNION ', ' INTERSECT ', ' EXCEPT '
        ]
        
        # Find the first occurrence of any main clause after WHERE
        # This determines where to stop wrapping conditions
        clause_index = len(after_where)  # Default to end of string if no main clauses found
        for clause in main_clauses:
            # Search for clause after WHERE position
            clause_pos = sql_upper.find(clause, where_index + 7)
            if clause_pos != -1 and clause_pos < (where_index + 7 + clause_index):
                # Calculate relative position within after_where string
                clause_index = clause_pos - (where_index + 7)
        
        # Extract just the WHERE conditions part and remaining SQL clauses
        where_part = after_where[:clause_index].strip()
        remaining_part = after_where[clause_index:]
        
        # Check if WHERE conditions are already wrapped in parentheses
        if where_part and not (where_part.startswith('(') and where_part.endswith(')')):
            # Wrap the WHERE conditions in parentheses
            return query[:where_index + 7] + f'({where_part})' + remaining_part
        
        return query

def _load_csv_data() -> dict:
    """Load all CSV files into memory at once"""
    tables = {}
    data_dir = 'data'

    if not os.path.exists(data_dir) or not os.path.isdir(data_dir):
        raise FileNotFoundError(f"data directory not found at {os.path.abspath(data_dir)}")

    csv_files_found = 0
    for fname in os.listdir(data_dir):
        if fname.endswith(".csv"):
            var_name = os.path.splitext(fname)[0]
            fpath = os.path.join(data_dir, fname)
            try:
                df = pd.read_csv(fpath, encoding="utf-8")
                csv_files_found += 1

                # # Auto convert time columns
                # for col in df.columns:
                #     if 'time' in col.lower() or 'date' in col.lower():
                #         try:
                #             df[col] = pd.to_datetime(df[col])
                #         except (ValueError, TypeError):
                #             pass

                tables[var_name] = df
            except UnicodeDecodeError:
                # Try other encodings
                for encoding in ["gbk", "latin1"]:
                    try:
                        df = pd.read_csv(fpath, encoding=encoding)
                        tables[var_name] = df
                        csv_files_found += 1
                        break
                    except UnicodeDecodeError:
                        continue
            except Exception as e:
                logger.warning(f"Error reading {fpath}: {e}")

    if csv_files_found == 0:
        raise ValueError("No CSV files found in data directory")

    logger.info(f"Loaded {csv_files_found} CSV files")
    return tables

_csv_tables = _load_csv_data() if not settings.OCEANBASE_ENABLED else None

def _query_from_csv(query: str) -> str:
    """Execute SQL query from CSV files"""
    try:
        # Execute SQL query using preloaded data
        result_df = sqldf(query, _csv_tables)
        return result_df.to_json(orient="records", force_ascii=False, date_format="iso")
    except Exception as e:
        logger.error(f"Error executing CSV query: {e}")
        return f"Error executing CSV query: {e}"

def _get_ob_engine():
    """Get or create OceanBase connection pool engine"""
    try:
        # Check OceanBase configuration
        if not settings.OCEANBASE_HOST or not settings.OCEANBASE_USER:
            raise ValueError("OceanBase configuration missing")

        # Build database connection string
        password = settings.OCEANBASE_PASSWORD.get_secret_value() if settings.OCEANBASE_PASSWORD else None
        connection_string = (
            f"mysql+pymysql://{settings.OCEANBASE_USER}:{password}@"
            f"{settings.OCEANBASE_HOST}:{settings.OCEANBASE_PORT or 3306}/"
            f"{settings.OCEANBASE_DB}?charset=utf8mb4"
        )

        # Create connection pool engine
        import sqlalchemy
        ob_engine = sqlalchemy.create_engine(
            connection_string,
            pool_size=5,           # Connection pool size
            max_overflow=10,       # Overflow connection count
            pool_pre_ping=True,   # Connection health check
            pool_recycle=3600     # Connection recycle time
        )
        logger.info("OceanBase connection pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize OceanBase engine: {e}")
        raise

    return ob_engine

_ob_engine = _get_ob_engine() if settings.OCEANBASE_ENABLED else None

def _query_from_ob(query: str) -> str:
    """Execute SQL query from OceanBase database"""
    try:
        sql_text = sa.text(query)
        df = pd.read_sql(sql_text, _ob_engine)

        return df.to_json(orient="records", force_ascii=False, date_format="iso")
        
    except Exception as e:
        logger.error(f"Error executing OceanBase query: {e}")
        return f"Error executing OceanBase query: {e}"
