"""
错误处理模块 - 记录失败文件，支持重试
"""

from typing import List, Tuple

class ErrorHandler:
    def __init__(self):
        self.failed_items: List[Tuple[str, str]] = []  # (文件路径, 错误信息)

    def add_error(self, file_path: str, error_msg: str):
        self.failed_items.append((file_path, error_msg))

    def clear(self):
        self.failed_items.clear()

    def get_failed(self) -> List[Tuple[str, str]]:
        return self.failed_items