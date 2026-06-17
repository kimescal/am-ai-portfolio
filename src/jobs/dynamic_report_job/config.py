# -*- coding: utf-8 -*-
"""
"""

import json
import os
from typing import Dict, List, Any
from cachetools import TTLCache

current_dir = os.path.dirname(os.path.abspath(__file__))
config_file_path = os.path.join(current_dir, 'dynamic_report_job_config.json')

config_cache = TTLCache(maxsize=1, ttl=7200)  # 2h

def get_config() -> Dict[str, Any]:
    if 'config' in config_cache:
        return config_cache['config']

    try:
        with open(config_file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            config_cache['config'] = config
            return config
    except FileNotFoundError:
        raise FileNotFoundError(f"团队配置文件未找到: {config_file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"团队配置文件格式错误: {e}")

def get_teams() -> Dict[str, Any]:
    return get_config().get('teams', {})

def get_all_team_names() -> List[str]:
    return list(get_config().get('teams', {}).keys())

def get_employees_by_team(team_name: str) -> Dict[str, str]:
    team_data = get_config().get('teams', {}).get(team_name)
    if not team_data:
        return {}

    return team_data.get('members', {})

def get_employees_by_regions(regions: List[str]) -> Dict[str, str]:
    """Get employees by multiple regions/team names

    Args:
        regions: List of region or team names (e.g., ["银行客群", "华北区域", "跨境区域"])

    Returns:
        Dictionary with employee names as keys and badge numbers as values
        (merged from all specified regions, duplicates removed)
    """
    all_employees = {}
    for region_name in regions:
        employees = get_employees_by_team(region_name)
        all_employees.update(employees)
    return all_employees

def get_all_employees() -> Dict[str, str]:
    all_employees = {}
    teams = get_config().get('teams', {})
    for team_data in teams.values():
        all_employees.update(team_data['members'])
    return all_employees

def get_team_leader(team_name: str) -> Dict[str, str]:
    teams = get_config().get('teams', {})
    team_data = teams.get(team_name)
    if not team_data:
        return None

    return team_data.get('leader', {})

def get_managers_info(managers: List[str]) -> Dict[str, str]:
    """Get manager information in dictionary format

    Args:
        managers: List of manager names

    Returns:
        Dictionary with manager names as keys and badge numbers as values
        e.g., {"John Doe": "12345", "Jane Smith": "67890"}
    """
    managers_info = {}
    all_employees = get_all_employees()

    for manager_name in managers:
        # Check if manager exists in all employees
        if manager_name in all_employees:
            managers_info[manager_name] = all_employees[manager_name]
        else:
            # Manager not found, skip or log warning
            print(f"Warning: Manager '{manager_name}' not found in employee database")

    return managers_info

def get_company_leaders() -> Dict[str, str]:
    company_leaders = get_config().get('company_leaders', {})
    return company_leaders

def get_admins() -> Dict[str, str]:
    admins = get_config().get('admins', {})
    return admins

def get_push_whitelist() -> Dict[str, str]:
    white_list = get_config().get('push_whitelist', {})
    return white_list

def get_push_blacklist() -> Dict[str, str]:
    black_list = get_config().get('push_blacklist', {})
    return black_list

def get_push_enabled() -> bool:
    """Get push enabled status from config"""
    return get_config().get('push_enabled', False)

def get_push_if_no_record() -> bool:
    """Get push if no record status from config"""
    return get_config().get('push_if_no_record', False)