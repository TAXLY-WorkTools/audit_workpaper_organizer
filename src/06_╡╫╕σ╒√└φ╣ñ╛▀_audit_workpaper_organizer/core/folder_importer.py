"""
文件夹导入模块 - 递归构建真树
"""
import os
from typing import Optional
from .models import ProjectData, GroupItem

SUPPORTED_EXTS = {
    '.docx', '.xlsx', '.pdf',
    '.jpg', '.jpeg', '.png', '.bmp', '.tiff',
    '.doc', '.xls'
}

def scan_folder(root_path: str, root_group_name: Optional[str] = None) -> ProjectData:
    """扫描文件夹并构建真实层级树"""
    project = ProjectData()
    root_path = os.path.abspath(root_path)

    # 创建根分组（如果指定了）
    if root_group_name:
        root_node = project.add_group(root_group_name)
    else:
        root_node = project.root

    def _recursive_scan(fs_path, parent_node):
        try:
            for entry in os.scandir(fs_path):
                if entry.is_dir():
                    # 创建子文件夹节点
                    child_node = GroupItem(entry.name)
                    parent_node.add_child(child_node)
                    # 递归扫描
                    _recursive_scan(entry.path, child_node)
                elif entry.is_file():
                    ext = os.path.splitext(entry.name)[1].lower()
                    if ext in SUPPORTED_EXTS:
                        # 添加到父节点的文件列表
                        parent_node.add_file(entry.path)
        except PermissionError:
            pass

    _recursive_scan(root_path, root_node)
    return project