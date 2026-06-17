import logging.config
import logging
import logging.config
from pathlib import Path
import yaml

def find_log_config(log_config_file: str = "logging.yaml") -> Path:
    """
    查找最近的日志配置文件，类似于 load_dotenv 的行为
    从当前目录开始向上查找，直到找到文件或到达根目录
    """
    current = Path(__file__).resolve().parent
    root = Path(__file__).resolve().parents[2]

    while current != root.parent:  # 搜索到项目根目录的上一级
        config_path = current / log_config_file
        if config_path.exists():
            return config_path
        current = current.parent

    return root / log_config_file  # 默认返回项目根目录下的文件

def setup_logging(log_config_file: str = "logging.yaml"):
    log_config_path = find_log_config(log_config_file)
    if log_config_path.exists():
        with open(log_config_path, 'r') as f:
            config = yaml.safe_load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        logging.warning(f"Logging configuration file not found at {log_config_path}. Using default logging configuration.")