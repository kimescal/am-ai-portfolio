import asyncio
import sys
import os
import multiprocessing

import uvicorn
from dotenv import load_dotenv

from core import settings

from core.logging_config import setup_logging
setup_logging()

load_dotenv()

if __name__ == "__main__":
    # Set Compatible event loop policy on Windows Systems.
    # On Windows systems, the default ProactorEventLoop can cause issues with
    # certain async database drivers like psycopg (PostgreSQL driver).
    # The WindowsSelectorEventLoopPolicy provides better compatibility and prevents
    # "RuntimeError: Event loop is closed" errors when working with database connections.
    # This needs to be set before running the application server.
    # Refer to the documentation for more information.
    # https://www.psycopg.org/psycopg3/docs/advanced/async.html#asynchronous-operations
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 根据CPU核心数确定进程数，通常设置为CPU核心数或核心数+1
    workers = settings.UVICORN_WORKERS
    if workers is None:
        workers = multiprocessing.cpu_count()

    # 在开发模式下不使用多进程，因为reload=True与workers>1不兼容
    if settings.is_dev():
        uvicorn.run("service:app", host=settings.HOST, port=settings.PORT, reload=True, reload_dirs=["src"], reload_excludes=["*.pyc", "src/client", "src/streamlit_app.py"])
    else:
        uvicorn.run("service:app", host=settings.HOST, port=settings.PORT, workers=workers)
