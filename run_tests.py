"""运行全部单元测试（标准库 unittest，无需 pytest）。

用法：
    python run_tests.py
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 测试套件强制离线：即使 .env 配了真实 Key 也走 MockLLM，
# 保证测试确定性、零花费、不依赖网络（真实链路由 demo.py 验证）。
for _key in ("LLM_API_KEY", "LLM_BASE_URL", "OPENAI_API_KEY", "OPENAI_BASE_URL"):
    os.environ[_key] = ""

if __name__ == "__main__":
    loader = unittest.defaultTestLoader
    suite = loader.discover(start_dir="tests", pattern="test_*.py")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)