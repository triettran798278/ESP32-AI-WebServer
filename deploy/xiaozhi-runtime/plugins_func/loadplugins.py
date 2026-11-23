import importlib
import pkgutil
from config.logger import setup_logging

TAG = __name__

logger = setup_logging()

def auto_import_modules(package_name):
    """
    自动导入指定包内的所有模块。

    Args:
        package_name (str): 包的名称，如 'functions'。
    """
    # Get package path
    package = importlib.import_module(package_name)
    package_path = package.__path__

    # Iterate through all modules in the package
    for _, module_name, _ in pkgutil.iter_modules(package_path):
        # Import module
        full_module_name = f"{package_name}.{module_name}"
        importlib.import_module(full_module_name)
        #logger.bind(tag=TAG).info(f"Module '{full_module_name}' loaded")