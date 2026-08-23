"""
pytest 全局配置
将 apps/ 加入 pythonpath，使 pytest 能按 app label 发现测试模块
"""
import sys
from pathlib import Path


# 将 apps/ 加入模块搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parent / "apps"))
