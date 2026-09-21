"""
项目管理模块 - 适配重构后的树结构
包含项目CRUD、重命名、复制、模板管理（已补全 export_template）
"""
import os
import json
from typing import List, Optional, Dict
from datetime import datetime
from dataclasses import dataclass, asdict

from core.models import ProjectData, GroupItem, FileItem

PROJECT_FILE_EXTENSION = ".auditproj"
TEMPLATE_FILE_EXTENSION = ".audittpl"
PROJECT_VERSION = "2.0.0"


@dataclass
class ProjectMeta:
    name: str
    project_type: str
    created_at: str
    updated_at: str
    last_opened_at: str
    version: str = PROJECT_VERSION

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


# ==================== 模板管理 ====================
BUILTIN_TEMPLATES = {
    "report": {"name": "报告类", "description": "封面、目录、正文、附件", "groups": ["封面", "目录", "正文", "附件"]},
    "blank": {"name": "空白", "description": "无预设分组", "groups": []}
}

def get_available_templates(projects_dir: str = None) -> List[Dict]:
    templates = []
    for key, value in BUILTIN_TEMPLATES.items():
        templates.append({'id': key, 'name': value['name'], 'description': value['description'], 'groups': value['groups'], 'is_builtin': True})
    if projects_dir:
        templates_dir = os.path.join(projects_dir, "Templates")
        if os.path.exists(templates_dir):
            for filename in os.listdir(templates_dir):
                if filename.endswith(TEMPLATE_FILE_EXTENSION):
                    file_path = os.path.join(templates_dir, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        template_id = f"user_{filename[:-len(TEMPLATE_FILE_EXTENSION)]}"
                        templates.append({'id': template_id, 'name': data.get('name', filename), 'description': data.get('description', ''), 'groups': data.get('groups', []), 'is_builtin': False})
                    except: pass
    return templates

# ★ 补全：导出模板（适配新的真树结构） ★
def export_template(project_data: ProjectData, name: str, description: str, projects_dir: str) -> bool:
    try:
        templates_dir = os.path.join(projects_dir, "Templates")
        os.makedirs(templates_dir, exist_ok=True)
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip()
        if not safe_name:
            safe_name = "未命名模板"
        file_path = os.path.join(templates_dir, f"{safe_name}{TEMPLATE_FILE_EXTENSION}")
        # 处理重名
        counter = 1
        while os.path.exists(file_path):
            file_path = os.path.join(templates_dir, f"{safe_name}({counter}){TEMPLATE_FILE_EXTENSION}")
            counter += 1

        # 递归遍历新的树结构，收集所有分组的名称（保留层级顺序）
        def collect_group_names(node, current_list):
            for child in node.children:
                current_list.append(child.name)
                collect_group_names(child, current_list)
        group_names = []
        collect_group_names(project_data.root, group_names)

        data = {
            'name': name,
            'description': description,
            'groups': group_names,
            'created_at': datetime.now().isoformat()
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"导出模板失败: {str(e)}")
        return False


def rename_template(template_id: str, new_name: str, projects_dir: str) -> bool:
    if not template_id.startswith("user_"): return False
    templates_dir = os.path.join(projects_dir, "Templates")
    old_filename = template_id[5:] + TEMPLATE_FILE_EXTENSION
    old_path = os.path.join(templates_dir, old_filename)
    if not os.path.exists(old_path): return False
    try:
        with open(old_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data['name'] = new_name
        safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '_', '-')).strip()
        new_path = os.path.join(templates_dir, safe_name + TEMPLATE_FILE_EXTENSION)
        counter = 1
        base_new = new_path
        while os.path.exists(new_path) and new_path != old_path:
            new_path = os.path.join(templates_dir, f"{safe_name}({counter}){TEMPLATE_FILE_EXTENSION}")
            counter += 1
        with open(new_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        if new_path != old_path: os.remove(old_path)
        return True
    except: return False

def delete_template(template_id: str, projects_dir: str) -> bool:
    if not template_id.startswith("user_"): return False
    templates_dir = os.path.join(projects_dir, "Templates")
    old_filename = template_id[5:] + TEMPLATE_FILE_EXTENSION
    old_path = os.path.join(templates_dir, old_filename)
    if os.path.exists(old_path):
        try:
            os.remove(old_path)
            return True
        except: return False
    return False


# ==================== 项目 CRUD（适配树） ====================

def _count_files_in_node(node: GroupItem) -> int:
    """递归统计文件数"""
    count = len(node.files)
    for child in node.children:
        count += _count_files_in_node(child)
    return count

def get_projects_list(projects_dir: str) -> List[dict]:
    projects = []
    if not os.path.exists(projects_dir): return projects
    for filename in os.listdir(projects_dir):
        if not filename.endswith(PROJECT_FILE_EXTENSION): continue
        file_path = os.path.join(projects_dir, filename)
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            meta = data.get('meta', {})
            root = data.get('root', {})
            file_count = _count_files_in_node(GroupItem.from_dict(root)) if root else 0
            projects.append({'file_path': file_path, 'name': meta.get('name', filename), 'project_type': meta.get('project_type', 'blank'), 'updated_at': meta.get('updated_at', ''), 'file_count': file_count})
        except: continue
    projects.sort(key=lambda x: x['updated_at'], reverse=True)
    return projects

def save_project(project_data: ProjectData, meta: ProjectMeta, file_path: str) -> bool:
    try:
        now = datetime.now().isoformat()
        meta.updated_at = now
        meta.last_opened_at = now
        data = {
            'meta': meta.to_dict(),
            'root': project_data.root.to_dict(),
            'settings': {'output_dir': project_data.output_dir, 'merge_mode': project_data.merge_mode}
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存项目失败: {str(e)}")
        return False

def load_project(file_path: str) -> tuple:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        meta = ProjectMeta.from_dict(data.get('meta', {}))
        project_data = ProjectData()
        project_data.output_dir = data.get('settings', {}).get('output_dir', '')
        project_data.merge_mode = data.get('settings', {}).get('merge_mode', 'single')
        if "root" in data:
            project_data.root = GroupItem.from_dict(data["root"])
        return project_data, meta
    except Exception as e:
        print(f"加载项目失败: {str(e)}")
        return None, None

def create_new_project(name: str, template_id: str, projects_dir: str) -> str:
    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip()
    if not safe_name: safe_name = "未命名项目"
    base_path = os.path.join(projects_dir, safe_name + PROJECT_FILE_EXTENSION)
    file_path = base_path
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(projects_dir, f"{safe_name}({counter}){PROJECT_FILE_EXTENSION}")
        counter += 1
    project_data = ProjectData()
    meta = ProjectMeta(name=name, project_type=template_id, created_at=datetime.now().isoformat(), updated_at=datetime.now().isoformat(), last_opened_at=datetime.now().isoformat())
    # 应用模板
    templates = get_available_templates(projects_dir)
    for t in templates:
        if t['id'] == template_id:
            for gname in t['groups']:
                project_data.add_group(gname)
            break
    save_project(project_data, meta, file_path)
    return file_path

def delete_project(file_path: str) -> bool:
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    except: return False

def rename_project(file_path: str, new_name: str) -> bool:
    try:
        project_data, meta = load_project(file_path)
        if not project_data: return False
        meta.name = new_name
        safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '_', '-')).strip()
        new_path = os.path.join(os.path.dirname(file_path), safe_name + PROJECT_FILE_EXTENSION)
        counter = 1
        base_new = new_path
        while os.path.exists(new_path) and new_path != file_path:
            new_path = os.path.join(os.path.dirname(file_path), f"{safe_name}({counter}){PROJECT_FILE_EXTENSION}")
            counter += 1
        if save_project(project_data, meta, new_path):
            if new_path != file_path: os.remove(file_path)
            return True
        return False
    except: return False

def copy_project(file_path: str) -> str:
    try:
        project_data, meta = load_project(file_path)
        if not project_data: raise Exception("项目数据无效")
        new_name = meta.name + " - 副本"
        safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '_', '-')).strip()
        new_path = os.path.join(os.path.dirname(file_path), safe_name + PROJECT_FILE_EXTENSION)
        counter = 1
        while os.path.exists(new_path):
            new_path = os.path.join(os.path.dirname(file_path), f"{safe_name}({counter}){PROJECT_FILE_EXTENSION}")
            counter += 1
        meta.name = new_name
        meta.created_at = datetime.now().isoformat()
        meta.updated_at = datetime.now().isoformat()
        meta.last_opened_at = datetime.now().isoformat()
        if save_project(project_data, meta, new_path):
            return new_path
        raise Exception("保存副本失败")
    except Exception as e:
        raise e