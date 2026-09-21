"""
项目工作台 - 启动页
v2.0.0 优化：增加项目右键菜单（重命名/复制）、管理模板按钮
"""

import os
import shutil
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog,
    QHeaderView, QLineEdit, QApplication, QDialog, QMenu,
    QInputDialog, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QCloseEvent

from core.project_manager import (
    get_projects_list, create_new_project, load_project,
    PROJECT_FILE_EXTENSION, delete_project,
    rename_project, copy_project,
    get_available_templates, rename_template, delete_template
)
from gui.new_project_dialog import NewProjectDialog
from gui.icon_manager import IconManager


class ProjectWorkspace(QWidget):
    """项目工作台 - 启动页"""
    
    project_opened = pyqtSignal(object, object, str)
    exit_app = pyqtSignal()
    
    def __init__(self, projects_dir: str, parent=None):
        super().__init__(parent)
        self.projects_dir = projects_dir
        self.icon_mgr = IconManager()
        
        self.setMinimumSize(900, 550)
        self.resize(900, 550)
        
        self._init_ui()
        self._refresh_projects()
    
    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # ---------- 标题 ----------
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setAlignment(Qt.AlignCenter)
        title_icon = QLabel()
        title_icon.setPixmap(self.icon_mgr.get_icon("folder_open_workspace_title").pixmap(32, 32))
        title_text = QLabel(" 底稿文件整理工具 v2.0.0")
        title_text.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_text)
        layout.addWidget(title_widget)
        
        subtitle = QLabel("选择或创建项目，开始整理底稿")
        subtitle.setFont(QFont("Microsoft YaHei", 10))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #666;")
        layout.addWidget(subtitle)
        
        # ---------- 操作栏 ----------
        action_layout = QHBoxLayout()
        
        # 新建和打开按钮
        self.btn_new = QPushButton(self.icon_mgr.get_icon("plus_circle_new_project"), " 新建项目")
        self.btn_new.clicked.connect(self._new_project)
        self.btn_new.setFixedWidth(120)
        action_layout.addWidget(self.btn_new)
        
        self.btn_open = QPushButton(self.icon_mgr.get_icon("folder_open_workspace_button"), " 打开项目")
        self.btn_open.clicked.connect(self._open_project)
        self.btn_open.setFixedWidth(120)
        action_layout.addWidget(self.btn_open)
        
        action_layout.addSpacing(20)
        
        # 搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索项目名称...")
        # 添加绿色放大镜图标 (search_workspace.svg 已存在)
        self.search_input.addAction(self.icon_mgr.get_icon("search_workspace"), QLineEdit.LeadingPosition)  
        self.search_input.textChanged.connect(self._on_search)
        self.search_input.setFixedWidth(200)
        action_layout.addWidget(self.search_input)
        
        # 管理模板按钮（放在刷新左侧）
        self.btn_manage_templates = QPushButton(self.icon_mgr.get_icon("upload_template_button"), " 管理模板")
        self.btn_manage_templates.clicked.connect(self._manage_templates)
        action_layout.addWidget(self.btn_manage_templates)
        
        # 刷新按钮
        self.btn_refresh = QPushButton(self.icon_mgr.get_icon("sync_refresh"), " 刷新")
        self.btn_refresh.clicked.connect(self._refresh_projects)
        self.btn_refresh.setFixedWidth(100)
        action_layout.addWidget(self.btn_refresh)
        
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        # ---------- 项目表格 ----------
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["项目名称", "文件数", "最后修改"])
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(1, 90)
        self.table.setColumnWidth(2, 200)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.table, 1)
        
        # ---------- 底部 ----------
        bottom_layout = QHBoxLayout()
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #666;")
        bottom_layout.addWidget(self.status_label)
        bottom_layout.addStretch()
        self.btn_delete = QPushButton(self.icon_mgr.get_icon("trash_delete_workspace"), " 删除选中")
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_delete.setFixedWidth(120)
        bottom_layout.addWidget(self.btn_delete)
        self.btn_quit = QPushButton(self.icon_mgr.get_icon("sign_out_exit"), " 退出")
        self.btn_quit.clicked.connect(self._on_quit)
        self.btn_quit.setFixedWidth(100)
        bottom_layout.addWidget(self.btn_quit)
        layout.addLayout(bottom_layout)
    
    def _on_search(self, text):
        self._refresh_projects(text)
    
    def _refresh_projects(self, search_text=""):
        if not os.path.exists(self.projects_dir):
            os.makedirs(self.projects_dir, exist_ok=True)
        projects = get_projects_list(self.projects_dir)
        if search_text.strip():
            search_lower = search_text.lower().strip()
            projects = [p for p in projects if search_lower in p['name'].lower()]
        self.table.setRowCount(0)
        if not projects:
            self.status_label.setText("还没有项目，点击「新建项目」开始")
            return
        self.table.setRowCount(len(projects))
        for row, p in enumerate(projects):
            name_item = QTableWidgetItem(p['name'])
            name_item.setData(Qt.UserRole, p['file_path'])
            name_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, name_item)
            count_item = QTableWidgetItem(str(p.get('file_count', 0)))
            count_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 1, count_item)
            time_str = p.get('updated_at', '')
            if time_str:
                try:
                    time_str = time_str.replace('T', ' ')[:16]
                except:
                    pass
            time_item = QTableWidgetItem(time_str if time_str else "未知")
            time_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 2, time_item)
        self.status_label.setText(f"共 {len(projects)} 个项目")
    
    def _on_item_double_clicked(self, item):
        row = item.row()
        file_path = self.table.item(row, 0).data(Qt.UserRole)
        if file_path:
            self._open_project_file(file_path)
    
    def _show_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        file_path = self.table.item(row, 0).data(Qt.UserRole)
        if not file_path:
            return
        menu = QMenu(self)
        action_rename = menu.addAction("重命名")
        action_copy = menu.addAction("复制项目")
        action = menu.exec_(self.table.viewport().mapToGlobal(pos))
        if action == action_rename:
            self._rename_project(file_path)
        elif action == action_copy:
            self._copy_project(file_path)
    
    def _rename_project(self, file_path):
        old_name = os.path.splitext(os.path.basename(file_path))[0]
        new_name, ok = QInputDialog.getText(self, "重命名项目", "请输入新的项目名称：", text=old_name)
        if ok and new_name.strip():
            if rename_project(file_path, new_name.strip()):
                self._refresh_projects()
                self.status_label.setText("✔ 项目重命名成功")
            else:
                QMessageBox.critical(self, "错误", "重命名失败，可能已存在同名项目。")
    
    def _copy_project(self, file_path):
        try:
            new_path = copy_project(file_path)
            self._refresh_projects()
            self.status_label.setText(f"✔ 已复制项目: {os.path.basename(new_path)}")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"复制失败: {str(e)}")
    
    def _delete_selected(self):
        selected_rows = set()
        for idx in self.table.selectedIndexes():
            selected_rows.add(idx.row())
        if not selected_rows:
            QMessageBox.information(self, "提示", "请先选中要删除的项目。")
            return
        if len(selected_rows) > 1:
            reply = QMessageBox.question(self, "确认删除", f"确定要删除选中的 {len(selected_rows)} 个项目吗？", QMessageBox.Yes | QMessageBox.No)
        else:
            row = next(iter(selected_rows))
            name = self.table.item(row, 0).text()
            reply = QMessageBox.question(self, "确认删除", f"确定要删除项目「{name}」吗？", QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        success_count = 0
        for row in selected_rows:
            file_path = self.table.item(row, 0).data(Qt.UserRole)
            if file_path and delete_project(file_path):
                success_count += 1
        self._refresh_projects()
        self.status_label.setText(f"✔ 已删除 {success_count} 个项目")
    
    def _new_project(self):
        dialog = NewProjectDialog(projects_dir=self.projects_dir, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        name, template_id = dialog.get_result()
        if not name:
            return
        try:
            file_path = create_new_project(name, template_id, self.projects_dir)
            project_data, meta = load_project(file_path)
            if project_data:
                self.project_opened.emit(project_data, meta, file_path)
            else:
                QMessageBox.critical(self, "错误", "创建项目失败，请检查文件权限。")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建项目失败: {str(e)}")
    
    def _open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "打开项目", self.projects_dir, f"项目文件 (*{PROJECT_FILE_EXTENSION})")
        if not file_path:
            return
        self._open_project_file(file_path)
    
    def _open_project_file(self, file_path):
        project_data, meta = load_project(file_path)
        if project_data:
            self.project_opened.emit(project_data, meta, file_path)
        else:
            QMessageBox.critical(self, "错误", "无法打开项目文件，文件可能已损坏。")
    
    def _manage_templates(self):
        # 简易模板管理窗口（重命名、删除）
        templates = get_available_templates(self.projects_dir)
        custom_templates = [t for t in templates if not t.get('is_builtin', False)]
        if not custom_templates:
            QMessageBox.information(self, "提示", "当前没有自定义模板。")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("模板管理")
        dialog.setMinimumSize(400, 300)
        layout = QVBoxLayout(dialog)
        
        list_widget = QListWidget()
        for t in custom_templates:
            item = QListWidgetItem(t['name'])
            item.setData(Qt.UserRole, t['id'])
            list_widget.addItem(item)
        layout.addWidget(list_widget)
        
        btn_layout = QHBoxLayout()
        btn_rename = QPushButton("重命名")
        btn_delete = QPushButton("删除")
        btn_close = QPushButton("关闭")
        btn_layout.addWidget(btn_rename)
        btn_layout.addWidget(btn_delete)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)
        
        def do_rename():
            item = list_widget.currentItem()
            if not item:
                return
            template_id = item.data(Qt.UserRole)  # 形如 "user_xxx"
            old_name = item.text()
            new_name, ok = QInputDialog.getText(dialog, "重命名模板", "请输入新的模板名称：", text=old_name)
            if ok and new_name.strip():
                if rename_template(template_id, new_name.strip(), self.projects_dir):
                    item.setText(new_name.strip())
                else:
                    QMessageBox.critical(dialog, "错误", "重命名模板失败。")
        
        def do_delete():
            item = list_widget.currentItem()
            if not item:
                return
            template_id = item.data(Qt.UserRole)
            reply = QMessageBox.question(dialog, "确认删除", f"确定要删除模板「{item.text()}」吗？", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                if delete_template(template_id, self.projects_dir):
                    list_widget.takeItem(list_widget.row(item))
                else:
                    QMessageBox.critical(dialog, "错误", "删除模板失败。")
        
        btn_rename.clicked.connect(do_rename)
        btn_delete.clicked.connect(do_delete)
        btn_close.clicked.connect(dialog.accept)
        
        dialog.exec_()
    
    def _on_quit(self):
        reply = QMessageBox.question(self, "确认退出", "确定要退出程序吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.exit_app.emit()
    
    def closeEvent(self, event: QCloseEvent):
        reply = QMessageBox.question(self, "确认退出", "确定要退出程序吗？", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.exit_app.emit()
            event.accept()
        else:
            event.ignore()
    
    def showEvent(self, event):
        self._refresh_projects()
        super().showEvent(event)