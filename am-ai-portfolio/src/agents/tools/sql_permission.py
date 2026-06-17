import logging
import json
import os
import re
from typing import Dict, List, Union, Any, Optional

logger = logging.getLogger(__name__)

class SQLPermissionChecker:
    """SQL Query Permission Controller - Three-tier access control with row filtering and manager permissions"""

    def __init__(self):
        self.permission_config = self.load_permission_config()
        self.dynamic_report_job_config = self.load_dynamic_report_job_config()
        self.employee_cache = {}  # Cache for employee name lookups


    def load_permission_config(self) -> Dict[str, Dict[str, Any]]:
        """Load permission configuration from JSON file"""
        config_file_path = os.path.join(os.path.dirname(__file__), 'sql_permission_config.json')
        try:
            with open(config_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading permission config from {config_file_path}: {e}")
            return {}

    def load_dynamic_report_job_config(self) -> Dict[str, Dict[str, Any]]:
        """Load member configuration from JSON file"""
        config_file_path = os.path.join(os.path.dirname(__file__), 'dynamic_report_job_config.json')


        try:
            with open(config_file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading permission config from {config_file_path}: {e}")
            return {}

    def get_employee_name(self, badge: str) -> Optional[str]:
        """Get employee name by badge number from emp_key_info table"""
        if badge in self.employee_cache:
            return self.employee_cache[badge]

        try:
            from agents.tools.sql_query import sql_query
            query = f"SELECT NAME FROM emp_key_info WHERE BADGE = '{badge}'"
            result = sql_query.invoke({"query": query})
            result_data = json.loads(result)

            if isinstance(result_data, list) and len(result_data) > 0 and 'NAME' in result_data[0]:
                name = result_data[0]['NAME']
                self.employee_cache[badge] = name
                return name
            return None
        except Exception as e:
            logger.error(f"Error querying employee name: {e}")
            return None

    def extract_table_names(self, sql_query: str) -> List[str]:
        """Extract table names from SQL query"""
        tables = []

        # FROM clause
        from_pattern = r'\bFROM\s+([a-zA-Z_]\w*)'
        tables.extend(re.findall(from_pattern, sql_query, re.IGNORECASE))

        # JOIN clauses
        join_pattern = r'\b(?:LEFT|RIGHT|INNER|FULL)\s+JOIN\s+([a-zA-Z_]\w*)'
        tables.extend(re.findall(join_pattern, sql_query, re.IGNORECASE))

        return list(set(tables))

    def _build_permission_result(self, level: str, can_access: bool, mask_fields: Dict = None,
                                  manager_field: str = None, is_list_field: bool = False,
                                  user_name: str = None, apply_manager_filter: bool = False,
                                  table_name: str = None) -> Dict[str, Any]:
        """Build permission result dictionary"""
        if not manager_field:
            apply_manager_filter = False

        return {
            "level": level,
            "can_access": can_access,
            "mask_fields": mask_fields or {},
            "manager_field": manager_field,
            "is_list_field": is_list_field,
            "user_name": user_name,
            "apply_manager_filter": apply_manager_filter,
            "table_name": table_name
        }

    def get_user_permission_level(self, table_name: str, user_badge: str) -> Dict[str, Any]:
        """Determine user's permission level for specific table"""
        # Table not configured
        if table_name not in self.permission_config:
            return self._build_permission_result("none", can_access=True, table_name=table_name)

        # Get manager field config
        permission_fields = self.permission_config[table_name].get("permission_fields", {})
        manager_field = permission_fields.get("manager_field")
        is_list_field = permission_fields.get("is_list_field", False)

        # Get all level configs
        hard_config = self.permission_config[table_name].get("hard_level", {})
        norm_config = self.permission_config[table_name].get("norm_level", {})
        soft_config = self.permission_config[table_name].get("soft_level", {})

        # 读取测试模式
        emp_access_only = self.permission_config[table_name].get("emp_access_only")

        # Check if user is a manager
        user_name = self.get_employee_name(user_badge)
        if not emp_access_only:
            if not user_name:
                mask_fields = hard_config.get("mask_fields", {}).copy()
                mask_fields.update(norm_config.get("mask_fields", {}))
                mask_fields.update(soft_config.get("mask_fields", {}))
                return self._build_permission_result("default_manager", can_access=True, mask_fields=mask_fields,
                                            manager_field=manager_field, is_list_field=is_list_field,
                                            user_name=user_name, apply_manager_filter=True, table_name=table_name)
        else:
            if not user_name:
                return self._build_permission_result("none", can_access=False, table_name=table_name)
        # if not user_name:
        #     mask_fields = hard_config.get("mask_fields", {}).copy()
        #     mask_fields.update(norm_config.get("mask_fields", {}))
        #     mask_fields.update(soft_config.get("mask_fields", {}))
        #     return self._build_permission_result("default_manager", can_access=True, mask_fields=mask_fields,
        #                                     manager_field=manager_field, is_list_field=is_list_field, 
        #                                     user_name=user_name, apply_manager_filter=True)

        if user_name in hard_config.get("blacklist", {}):
            return self._build_permission_result("hard_blacklist", can_access=False,
                                                manager_field=manager_field, is_list_field=is_list_field, user_name=user_name, table_name=table_name)

        if user_name in norm_config.get("blacklist", {}):
            return self._build_permission_result("norm_blacklist", can_access=False,
                                                manager_field=manager_field, is_list_field=is_list_field, user_name=user_name, table_name=table_name)

        if user_name in soft_config.get("blacklist", {}):
            return self._build_permission_result("soft_blacklist", can_access=False,
                                                manager_field=manager_field, is_list_field=is_list_field, user_name=user_name, table_name=table_name)

        # Check whitelists (no manager restriction, progressive unlock model)
        # Hard whitelist: Full access, no masks at all
        if user_name in hard_config.get("whitelist", {}):
            return self._build_permission_result("hard_whitelist", can_access=True,
                                                manager_field=manager_field, is_list_field=is_list_field, user_name=user_name, table_name=table_name)

        # Norm whitelist: Only blocked by hard masks (unlocked norm+soft levels)
        if user_name in norm_config.get("whitelist", {}):
            mask_fields = hard_config.get("mask_fields", {}).copy()
            return self._build_permission_result("norm_whitelist", can_access=True, mask_fields=mask_fields,
                                                manager_field=manager_field, is_list_field=is_list_field, user_name=user_name, table_name=table_name)

        # Soft whitelist: Blocked by hard+norm masks (unlocked soft level)
        if user_name in soft_config.get("whitelist", {}):
            mask_fields = hard_config.get("mask_fields", {}).copy()
            mask_fields.update(norm_config.get("mask_fields", {}))
            return self._build_permission_result("soft_whitelist", can_access=True, mask_fields=mask_fields,
                                                manager_field=manager_field, is_list_field=is_list_field, user_name=user_name, table_name=table_name)

        # Default: Normal manager with all masks and manager filter
        mask_fields = hard_config.get("mask_fields", {}).copy()
        mask_fields.update(norm_config.get("mask_fields", {}))
        mask_fields.update(soft_config.get("mask_fields", {}))
        return self._build_permission_result("default_manager", can_access=True, mask_fields=mask_fields,
                                            manager_field=manager_field, is_list_field=is_list_field,
                                            user_name=user_name, apply_manager_filter=True, table_name=table_name)

    def build_permission_conditions(self, permission: Dict[str, Any]) -> List[str]:
        """Build SQL conditions based on permission level"""
        teams = self.dynamic_report_job_config.get("teams", {})
        conditions = []
        user_name = permission.get("user_name")

        # Add row filtering conditions (exclude masked values)
        # BUT: if user_name is in CUST_NAME, allow access even if masked
        mask_fields = permission.get("mask_fields", {})
        for field, mask_values in mask_fields.items():
            # Support both single value and list of values for masking
            if isinstance(mask_values, list):
                # Multiple values to mask: field NOT IN ('value1', 'value2', ...)
                if mask_values:
                    values_str = "', '".join(str(v) for v in mask_values)
                    mask_condition = f"{field} NOT IN ('{values_str}')"
            else:
                mask_condition = f"{field} != '{mask_values}'"

            if user_name:
                conditions.append(f"({mask_condition} OR CUST_NAME = '{user_name}')")
            else:
                conditions.append(mask_condition)

        # Add manager permission conditions - Only apply if explicitly required
        apply_manager_filter = permission.get("apply_manager_filter", False)
        if apply_manager_filter:
            manager_field = permission.get("manager_field")
            is_list_field = permission.get("is_list_field", False)

            if manager_field and user_name:
                if is_list_field:
                    conditions.append(f"FIND_IN_SET('{user_name}', {manager_field}) > 0")
                else:
                    # consider leader and members
                    target_names = {user_name}
                    for team_name, team_info in teams.items():
                        leaders = team_info.get("leader", {})
                        members = team_info.get("members", {})

                        if user_name in leaders:
                            target_names.update(members.keys())
                            break

                    if target_names:
                        names_alt = "|".join(re.escape(n) for n in sorted(target_names))
                        pattern = rf"(^|,)({names_alt})(,|$)"
                        final_sql = f"(REPLACE({manager_field}, ' ', '') REGEXP '{pattern}')"
                        conditions.append(final_sql)
                    # Add filter fields conditions with OR logic
                    # Only process if table_name is not empty
                    table_name = permission.get("table_name")
                    if table_name:
                        filter_fields = self.permission_config.get(table_name, {}).get("filter_fields", {})
                        if filter_fields:
                            filter_conditions = []
                            for field, field_values in filter_fields.items():
                                if isinstance(field_values, list) and field_values:
                                    values_str = "', '".join(str(v) for v in field_values)
                                    filter_conditions.append(f"{field} IN ('{values_str}')")

                            if filter_conditions:
                                # Combine all filter fields with OR
                                filter_or_condition = " OR ".join(filter_conditions)
                                conditions.append(f"({filter_or_condition})")

        return conditions

    def apply_permission_filter(self, sql_query: str, user_badge: str) -> str:
        """Apply permission filter to SQL query"""
        # Only process SELECT queries
        if not re.search(r'\bSELECT\b', sql_query, re.IGNORECASE):
            logger.warning("Permission control only supports SELECT queries")
            return sql_query

        if not user_badge:
            return sql_query

        try:
            tables = self.extract_table_names(sql_query)
            all_conditions = []

            # Check each table's permission
            for table in tables:
                permission = self.get_user_permission_level(table, user_badge)

                if not permission["can_access"]:
                    # User cannot access this table, return empty result
                    return "SELECT * FROM (SELECT 1) as dummy WHERE 1=0 LIMIT 0"

                # Build conditions for this table
                table_conditions = self.build_permission_conditions(permission)
                all_conditions.extend(table_conditions)

            # Apply conditions to the query
            if all_conditions:
                combined_conditions = " OR ".join(all_conditions)

                if re.search(r'\bWHERE\b', sql_query, re.IGNORECASE):
                    # If WHERE clause already exists, add AND conditions at the beginning
                    modified_query = re.sub(
                        r'(\bWHERE\b)',
                        rf'\1 ({combined_conditions}) AND ',
                        sql_query,
                        count=1,
                        flags=re.IGNORECASE
                    )
                else:
                    # If no WHERE clause exists, add WHERE condition
                    # Try to find a position before GROUP BY, ORDER BY, LIMIT, UNION, or end of query
                    where_position = re.search(
                        r'(\bFROM\b[^;]*?)(\s+(?:GROUP\s+BY|ORDER\s+BY|LIMIT|UNION|HAVING)\b|$)',
                        sql_query,
                        re.IGNORECASE | re.DOTALL
                    )

                    if where_position:
                        modified_query = sql_query[:where_position.end(1)] + f' WHERE ({combined_conditions})' + sql_query[where_position.start(2):]
                    else:
                        # Fallback: append at the end
                        modified_query = sql_query.rstrip(';') + f' WHERE ({combined_conditions})'

                return modified_query

            return sql_query
        except Exception as e:
            logger.error(f"Error adding permission filter: {e}")
            return sql_query
            
# Create global permission checker instance
permission_checker = SQLPermissionChecker()