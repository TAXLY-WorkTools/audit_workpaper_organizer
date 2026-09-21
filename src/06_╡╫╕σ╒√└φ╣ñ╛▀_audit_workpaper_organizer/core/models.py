"""
数据模型模块 - 重构版（真正的树结构）
"""
import os
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class FileItem:
    """表示一个待处理文件（保持不变）"""
    path: str
    order: int = 0
    is_cover: bool = False
    rename_as: Optional[str] = None
    _cached_name: Optional[str] = None

    def __post_init__(self):
        if self._cached_name is None:
            self._cached_name = os.path.basename(self.path)

    @property
    def name(self) -> str:
        return self._cached_name or os.path.basename(self.path)

    @property
    def ext(self) -> str:
        return os.path.splitext(self.path)[1].lower()

    @property
    def size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "order": self.order,
            "is_cover": self.is_cover,
            "rename_as": self.rename_as,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FileItem":
        return cls(
            path=data["path"],
            order=data.get("order", 0),
            is_cover=data.get("is_cover", False),
            rename_as=data.get("rename_as"),
        )


# ===== 核心修改：GroupItem 变成了真正的树节点 =====
class GroupItem:
    """表示一个分组/条目（重构版：包含真实的父子关系）"""
    def __init__(self, name: str, parent=None, code: Optional[str] = None, notes: str = ""):
        self.name = name
        self.parent = parent
        self.children: List["GroupItem"] = []
        self.files: List[FileItem] = []
        self.notes: str = notes
        self.code: Optional[str] = code

    def add_child(self, node: "GroupItem") -> "GroupItem":
        node.parent = self
        self.children.append(node)
        return node

    def remove_from_parent(self):
        if self.parent:
            self.parent.children.remove(self)
            self.parent = None

    def get_full_path(self) -> str:
        """通过父节点引用动态生成相对路径"""
        path = []
        node = self
        while node:
            path.append(node.name)
            node = node.parent
        return "/".join(reversed(path))

    def add_file(self, file_path: str, is_cover: bool = False) -> FileItem:
        max_order = max([f.order for f in self.files], default=-1)
        item = FileItem(file_path, order=max_order + 1, is_cover=is_cover)
        self.files.append(item)
        return item

    def remove_file(self, index: int) -> bool:
        if 0 <= index < len(self.files):
            self.files.pop(index)
            return True
        return False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "code": self.code,
            "notes": self.notes,
            "files": [f.to_dict() for f in self.files],
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GroupItem":
        node = cls(
            name=data["name"],
            code=data.get("code"),
            notes=data.get("notes", ""),
        )
        for fdata in data.get("files", []):
            node.files.append(FileItem.from_dict(fdata))
        for cdata in data.get("children", []):
            node.add_child(cls.from_dict(cdata))
        return node


class ProjectData:
    """项目数据容器 - 使用真树结构"""
    def __init__(self):
        self.root = GroupItem("__ROOT__")  # 虚拟根节点，永远不为空
        self.output_dir: str = ""
        self.merge_mode: str = "single"

    def add_group(self, name: str, parent: GroupItem = None) -> GroupItem:
        if parent is None:
            parent = self.root
        return parent.add_child(GroupItem(name))

    def get_group_by_name(self, name: str, parent: GroupItem = None) -> Optional[GroupItem]:
        if parent is None:
            parent = self.root
        for child in parent.children:
            if child.name == name:
                return child
            res = self.get_group_by_name(name, child)
            if res:
                return res
        return None

    def clear(self):
        self.root = GroupItem("__ROOT__")

    def to_dict(self) -> dict:
        return {
            "root": self.root.to_dict(),
            "output_dir": self.output_dir,
            "merge_mode": self.merge_mode,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ProjectData":
        proj = cls()
        proj.output_dir = data.get("output_dir", "")
        proj.merge_mode = data.get("merge_mode", "single")
        if "root" in data:
            proj.root = GroupItem.from_dict(data["root"])
        return proj