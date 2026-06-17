#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dynamic Report Job - Simplified version based on report.py
"""

import asyncio
import argparse
import logging
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any

# 先初始化 service 模块，避免循环依赖
# 这一步很重要：先完整初始化 service，使其进入 sys.modules
# 之后 agents 导入 service.qiwei.zhiyu_platform 时就不会触发循环导入
try:
    import service
    logging.info("Service module pre-initialized successfully")
except Exception as e:
    logging.warning(f"Service pre-initialization failed (may not be needed): {e}")

from agents.marketing.dynamic_report.report import dynamic_report

import jobs.dynamic_report_job.config as cfg

from core.logging_config import setup_logging
setup_logging()

logger = logging.getLogger(__name__)

async def process_manager(manager: Dict[str, Any], days: int = 7, template_modules: str = None, push_type='text') -> Dict[str, Any]:
    """Process single manager report"""
    try:
        # 解析模板模块
        templates = []
        if template_modules:
            templates = [m.strip() for m in template_modules.split(',')]
        else:
            # 默认模块
            templates = ["employee_visit"]
        
        config = {
            "configurable": {
                "employees": manager,
                "report_level": "employee",
                "data_days": days,
                "template": templates,  # 添加模块配置
                "admins": cfg.get_admins(),
                "push_whitelist": cfg.get_push_whitelist(),
                "push_blacklist": cfg.get_push_blacklist(),
                "push_enabled": cfg.get_push_enabled(),
                "push_if_no_record": cfg.get_push_if_no_record(),
                "push_type": push_type
            }
        }

        result = await dynamic_report.ainvoke({}, config=config)

        return {
            "manager_name": list(manager.keys())[0],
            "status": "success" if not result.get("error_message") else "failed",
            "error": result.get("error_message", "")
        }

    except Exception as e:
        manager_name = list(manager.keys())[0] if manager else "unknown"
        logger.error(f"Failed to process {manager_name}: {e}")
        return {
            "manager_name": manager_name,
            "status": "failed",
            "error": str(e)
        }


async def process_team(team_name: str, days: int = 7, template_modules: str = None,push_type:str = 'text') -> Dict[str, Any]:
    """Process single team report"""
    try:
        employees = cfg.get_employees_by_team(team_name)
        if not employees:
            logger.error(f"No employees found for team '{team_name}'")
            return {
                "manager_name": team_name,
                "status": "failed",
                "error": f"No employees found for team '{team_name}'"
            }

        # Get team leader for push notification
        team_leader = cfg.get_team_leader(team_name)
        if not team_leader:
            logger.warning(f"No team leader found for team '{team_name}'")

        # 解析模板模块
        modules = []
        if template_modules:
            modules = [m.strip() for m in template_modules.split(',')]
        else:
            # 默认模块
            modules = ["team_visit"]

        config = {
            "configurable": {
                "report_level": "team",
                "employees": employees,
                "data_days": days,
                "team_name": team_name,
                "team_leader": team_leader,  # Add team leader info for push optimization
                "template": modules,  # 添加模块配置
                "admins": cfg.get_admins(),
                "push_whitelist": cfg.get_push_whitelist(),
                "push_blacklist": cfg.get_push_blacklist(),
                "push_enabled": cfg.get_push_enabled(),
                "push_if_no_record": cfg.get_push_if_no_record(),
                "push_type": push_type
            }
        }

        result = await dynamic_report.ainvoke({}, config=config)

        return {
            "manager_name": team_name,
            "status": "success" if not result.get("error_message") else "failed",
            "error": result.get("error_message", "")
        }

    except Exception as e:
        logger.error(f"Failed to process team '{team_name}': {e}")
        return {
            "manager_name": team_name,
            "status": "failed",
            "error": str(e)
        }

def get_period_days(period: str) -> int:
    """
    Convert period to days
    """
    today = datetime.now()

    if period == "week":
        days_since_monday = today.weekday()  # Monday is 0
        begin_date = today - timedelta(days=days_since_monday)
        return (today - begin_date).days

    elif period == "month":
        begin_date = today.replace(day=1)
        return (today - begin_date).days

    elif period == "quarter":
        current_month = today.month
        if current_month <= 3:
            begin_date = today.replace(month=1, day=1)
        elif current_month <= 6:
            begin_date = today.replace(month=4, day=1)
        elif current_month <= 9:
            begin_date = today.replace(month=7, day=1)
        else:
            begin_date = today.replace(month=10, day=1)
        return (today - begin_date).days

    elif period == "year":
        begin_date = today.replace(month=1, day=1)
        return (today - begin_date).days

    else:
        raise ValueError(f"Invalid period: {period}")


async def run_reports(level: str = "employee", managers: List[str] = None,
                      days: int = 7, max_concurrent: int = 5,
                      teams: List[str] = None, period: str = None,
                      templates: str = None, push_type: str = "text",
                      regions: List[str] = None):
    """Run dynamic reports

    Args:
        level: Report level - employee, team, or company
        managers: List of manager names (for employee level)
        days: Number of days for report data, default 7
        max_concurrent: Maximum concurrent processing, default 5
        teams: List of team names (for team level)
        period: Period type - week, month, quarter, year (overrides days parameter)
        templates: Template template to use (comma-separated): employee_visit,team_visit,company_visit,requirement
        regions: List of region names to filter employees by (e.g., ["银行客群", "华北区域", "跨境区域"])
    """
    logger.info(f"Starting dynamic report generation - {datetime.now()}")

    # Handle period parameter
    if period:
        days = get_period_days(period)
        logger.info(f"Using period '{period}' - calculated {days} days")

    # Handle different report levels
    if level == "employee":
        # When level is employee, handle managers parameter
        if not managers:
            # If managers is empty, check if regions is specified
            if regions:
                # Get employees by multiple regions
                managers = cfg.get_employees_by_regions(regions)
                if not managers:
                    logger.warning(f"No employees found for regions '{regions}'")
                    return
                logger.info(f"Using {len(managers)} managers from regions '{regions}'")
            else:
                # Get all active managers from config
                managers = cfg.get_all_employees()

                if not managers:
                    logger.warning("No managers found in config")
                    return
                logger.info(f"Using all {len(managers)} managers from config")
        else:
            managers = cfg.get_managers_info(managers)

        # Process employee managers with concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(manager):
            async with semaphore:
                return await process_manager(manager, days, templates, push_type)

        # Run all tasks
        tasks = [process_with_semaphore({m: n}) for m, n in managers.items()]
        results = await asyncio.gather(*tasks)

    elif level == "team":
        # When level is team, handle teams parameter
        if not teams:
            # If teams is empty, get all teams from config
            teams = cfg.get_all_team_names()
            if not teams:
                logger.warning("No teams found in config")
                return
            logger.info(f"Using all {len(teams)} teams from config")

        logger.info(f"Processing {len(teams)} teams")

        # Process teams with concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_with_semaphore(team_name):
            async with semaphore:
                return await process_team(team_name, days, templates,push_type)

        # Run all tasks
        tasks = [process_with_semaphore(team_name) for team_name in teams]
        results = await asyncio.gather(*tasks)

    elif level == "company":
        # Single company report
        logger.info("Generating company level report")

        # 解析模板模块
        modules = []
        if templates:
            modules = [m.strip() for m in templates.split(',')]
        else:
            # 默认模块
            modules = ["company_visit"]

        config = {
            "configurable": {
                "report_level": "company",
                "teams_info": cfg.get_teams(),
                "data_days": days,
                "company_leaders": cfg.get_company_leaders(),  # Use company_leaders for push optimization
                "template": modules,  # 添加模块配置
                "admins": cfg.get_admins(),
                "push_whitelist": cfg.get_push_whitelist(),
                "push_blacklist": cfg.get_push_blacklist(),
                "push_enabled": cfg.get_push_enabled(),
                "push_if_no_record": cfg.get_push_if_no_record(),
                "push_type": push_type
            }
        }

        try:
            result = await dynamic_report.ainvoke({}, config=config)
            success = not result.get("error_message")
            error = result.get("error_message", "")

            results = [{
                "manager_name": "company_report",
                "status": "success" if success else "failed",
                "error": error
            }]
        except Exception as e:
            logger.error(f"Failed to generate company report: {e}")
            results = [{
                "manager_name": "company_report",
                "status": "failed",
                "error": str(e)
            }]
    else:
        logger.error(f"Invalid level: {level}")
        return

    # Statistics
    success = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "failed")

    logger.info(f"Report generation completed!")
    logger.info(f"Total: {len(results)}, Success: {success}, Failed: {failed}")

    # Show first 10 results
    for i, result in enumerate(results):
        logger.info(f"  {i+1}. {result['manager_name']} - {result['status']}")
        if result["error"]:
            logger.error(f"     Error: {result['error']}")

    return {"total": len(results), "success": success, "failed": failed}


def main():
    """Main function"""

    parser = argparse.ArgumentParser(description='Dynamic Report Job')
    parser.add_argument('--level', choices=['employee', 'team', 'company'], default='employee',
                       help='Report level: employee, team, or company')
    parser.add_argument('--managers', nargs='+', help='Manager names')
    parser.add_argument('--teams', nargs='+', help='Team name(s) for team level. If not specified when level=team, all teams will be processed')
    parser.add_argument('--regions', nargs='+', help='Region/team names for employee level (use full team names from config)')
    parser.add_argument('--days', type=int, help='Report days, default 7')
    parser.add_argument('--max-concurrent', type=int, default=5,
                       help='Max concurrent processing, default 5')
    parser.add_argument('--period', choices=['week', 'month', 'quarter', 'year'],
                       help='Period type (overrides days): week=current week, month=current month, quarter=current quarter, year=current year')
    parser.add_argument('--templates', type=str, help='Template template to use (comma-separated): employee_visit,team_visit,company_visit,requirement')
    parser.add_argument('--push-type', default='text',
                       help='Push type: text, file, or text,file for both')

    args = parser.parse_args()


    logger.info("Dynamic Report Job Started")
    logger.info("=" * 50)

    result = asyncio.run(run_reports(
        level=args.level,
        managers=args.managers,
        days=args.days,
        max_concurrent=args.max_concurrent,
        teams=args.teams,
        period=args.period,
        templates=args.templates,
        push_type=args.push_type,
        regions=args.regions
    ))

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())