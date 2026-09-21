"""
新建项目对话框
从模板管理器动态加载模板列表
SVG图标已集成
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QListWidget, QListWidgetItem,
    QWidget
)
from PyQt5.QtCore import Qt

from core.project_manager import get_available_templates
from gui.icon_manager import IconManager


class NewProjectDialog(QDialog):
    def __init__(self, projects_dir: str = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(350)
        self.projects_dir = projects_dir
        self._result = None

        # 初始化图标管理器
        self.icon_mgr = IconManager()

        self._init_ui()
        self._update_preview()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # ---------- 项目名称 ----------
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("项目名称:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("输入项目名称，如：2026年泰安审计底稿")
        name_layout.addWidget(self.name_edit)
        layout.addLayout(name_layout)
        
        # ---------- 模板选择 ----------
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("选择模板:"))
        self.type_combo = QComboBox()
        self.type_combo.currentIndexChanged.connect(self._update_preview)
        type_layout.addWidget(self.type_combo)
        layout.addLayout(type_layout)
        
        # ---------- 模板预览 ----------
        preview_label = QLabel("模板预览:")
        preview_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(preview_label)
        
        self.preview_list = QListWidget()
        self.preview_list.setMinimumHeight(150)
        self.preview_list.setMaximumHeight(200)
        self.preview_list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self.preview_list)
        
        # ---------- 提示（★ 修复：使用组合布局放图标和文字） ----------
        tip_widget = QWidget()
        tip_layout = QHBoxLayout(tip_widget)
        tip_layout.setContentsMargins(0, 0, 0, 0)
        
        tip_icon = QLabel()
        tip_icon.setPixmap(self.icon_mgr.get_icon("lightbulb_new_project_tip").pixmap(16, 16))
        tip_text = QLabel(" 提示: 您稍后可以自由增删改分组")
        tip_text.setStyleSheet("color: #666; font-size: 9pt;")
        
        tip_layout.addWidget(tip_icon)
        tip_layout.addWidget(tip_text)
        tip_layout.addStretch()
        layout.addWidget(tip_widget)
        
        # ---------- 按钮 ----------
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_create = QPushButton("创建项目")
        self.btn_create.setDefault(True)
        self.btn_create.clicked.connect(self._on_create)
        btn_layout.addWidget(self.btn_create)
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        
        # ---------- 加载模板列表 ----------
        self._load_templates()
    
    def _load_templates(self):
        """从模板管理器加载模板列表"""
        self.type_combo.clear()
        templates = get_available_templates(self.projects_dir)
        self._templates = templates
        
        for t in templates:
            display_name = t['name']
            if t.get('is_builtin'):
                display_name += " (内置)"
            self.type_combo.addItem(display_name, t['id'])
    
    def _update_preview(self):
        """更新模板预览（★ 为列表项添加图标）"""
        self.preview_list.clear()
        
        current_idx = self.type_combo.currentIndex()
        if current_idx < 0 or current_idx >= len(self._templates):
            return
        
        template = self._templates[current_idx]
        groups = template.get('groups', [])
        
        if not groups:
            item = QListWidgetItem("（空白项目，无预设分组）")
            item.setForeground(Qt.gray)
            self.preview_list.addItem(item)
        else:
            for group_name in groups:
                # ★ 使用 SVG 图标替换原来的 ▶ 文字 ★
                item = QListWidgetItem(self.icon_mgr.get_icon("play_template_preview"), f"  {group_name}")
                self.preview_list.addItem(item)
    
    def _on_create(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入项目名称。")
            return
        
        current_idx = self.type_combo.currentIndex()
        if current_idx < 0 or current_idx >= len(self._templates):
            QMessageBox.warning(self, "提示", "请选择有效的模板。")
            return
        
        template_id = self._templates[current_idx]['id']
        self._result = (name, template_id)
        self.accept()
    
    def get_result(self):
        """返回 (项目名称, 模板ID)"""
        return getattr(self, '_result', (None, None))