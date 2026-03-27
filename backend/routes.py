"""
兼容保留：
旧代码可能仍从 `routes.py` 导入 `api_bp`，这里转发到新 api 文件。
"""

from api import api_bp

