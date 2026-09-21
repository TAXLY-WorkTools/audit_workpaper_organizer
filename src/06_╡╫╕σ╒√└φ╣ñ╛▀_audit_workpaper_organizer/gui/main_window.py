"""
主窗口 - 包含左右分栏布局、工具栏、状态栏
v2.0.0 完整版（含撤销/重做、拖拽修复、SVG图标集成、重构树结构适配）
"""

import os
import re
import copy
from datetime import datetime
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QTableWidget, QTableWidgetItem,
    QPushButton, QFileDialog, QMessageBox, QProgressBar, QLabel,
    QHeaderView, QMenu, QAction, QToolBar, QStatusBar,
    QApplication, QInputDialog, QDialog, QStyle, QCheckBox,
    QMenuBar, QAbstractItemView
)
from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSignal, QRect
from PyQt5.QtGui import QIcon, QFont, QCloseEvent, QKeySequence, QColor, QBrush, QPen, QPainter

from core.folder_importer import scan_folder
from core.models import ProjectData, GroupItem, FileItem
from core.project_manager import save_project, ProjectMeta, export_template

from gui.dialogs import ExportModeDialog
from gui.worker_thread import ConvertWorker
from gui.progress_window import ProgressWindow
from gui.retry_dialog import RetryDialog
from gui.log_dialog import LogDialog
from gui.folder_import_dialog import FolderImportDialog
from gui.switch_panel import SwitchPanel

# 导入图标管理器
from gui.icon_manager import IconManager


class MainWindow(QMainWindow):
    closed = pyqtSignal()
    
    def __init__(self, project_data=None, meta=None, project_file_path=None, workspace=None, projects_dir=None):
        super().__init__()
        self.setWindowTitle("底稿文件整理工具 v2.0.0")
        self.setGeometry(100, 100, 1400, 850)
        self.setMinimumSize(1000, 700)

        self.project_data = project_data if project_data else ProjectData()
        self.meta = meta
        self.project_file_path = project_file_path
        self.workspace = workspace
        self.projects_dir = projects_dir
        self.current_group = None

        self.suppress_delete_warning = False
        self.expanded_items = set()
        self.show_files = False

        # 初始化图标管理器
        self.icon_mgr = IconManager()

        # 项目切换边栏
        self.switch_panel = None
        if self.projects_dir:
            self.switch_panel = SwitchPanel(self.projects_dir, self)
            self.switch_panel.project_selected.connect(self._on_switch_project)
            self.switch_panel.new_project_requested.connect(self._go_to_new_project)

        # 拖拽相关状态
        self.drag_target_item = None
        self.drag_over_blank = False
        self.drag_is_external = False

        # ===== 撤销/重做 =====
        self.undo_stack = []
        self.redo_stack = []
        self.max_undo_steps = 30
        self.is_undoing = False

        if self.meta and self.meta.name:
            self.setWindowTitle(f"底稿文件整理工具 v2.0.0 - {self.meta.name}")

        self.worker = None
        self.progress_window = None
        self.log_messages = []
        self.last_conversion_summary = ""

        self._init_ui()
        self._update_tree()

    def _init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._create_menubar()
        toolbar = self._create_toolbar()
        main_layout.addWidget(toolbar)

        title_bar = self._create_title_bar()
        main_layout.addWidget(title_bar)

        splitter = QSplitter(Qt.Horizontal)

        # 左面板
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        left_title_widget = QWidget()
        left_title_layout = QHBoxLayout(left_title_widget)
        left_title_layout.setContentsMargins(0, 0, 0, 0)
        left_icon = QLabel()
        left_icon.setPixmap(self.icon_mgr.get_icon("folder_open_tree_title").pixmap(24, 24))
        left_text = QLabel(" 条目 / 分组")
        left_text.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        left_title_layout.addWidget(left_icon)
        left_title_layout.addWidget(left_text)
        left_title_layout.addStretch()
        left_layout.addWidget(left_title_widget)
        
        left_btn_layout = QHBoxLayout()
        self.btn_new_entry = QPushButton(self.icon_mgr.get_icon("folder_new_button"), " 新建")
        self.btn_new_entry.clicked.connect(self._add_group)
        self.btn_new_entry.setToolTip("在当前选中位置新建条目")
        left_btn_layout.addWidget(self.btn_new_entry)
        
        self.btn_collapse = QPushButton(self.icon_mgr.get_icon("minus_circle_collapse"), " 折叠")
        self.btn_collapse.clicked.connect(self._collapse_all)
        self.btn_collapse.setToolTip("折叠所有分组")
        left_btn_layout.addWidget(self.btn_collapse)
        
        self.btn_show_files = QPushButton(self.icon_mgr.get_icon("file_show_files_button"), " 显示文件")
        self.btn_show_files.clicked.connect(self._toggle_show_files)
        self.btn_show_files.setToolTip("显示/隐藏末级文件")
        left_btn_layout.addWidget(self.btn_show_files)
        
        left_btn_layout.addStretch()
        left_layout.addLayout(left_btn_layout)
        
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("名称")
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.setIndentation(20)
        self.tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.dragEnterEvent = self._tree_drag_enter_event
        self.tree.dragMoveEvent = self._tree_drag_move_event
        self.tree.dropEvent = self._tree_drop_event
        self.tree.dragLeaveEvent = self._tree_drag_leave_event
        self.tree.paintEvent = self._tree_paint_event
        left_layout.addWidget(self.tree)

        left_btn_layout2 = QHBoxLayout()
        self.btn_add_group = QPushButton(self.icon_mgr.get_icon("plus_add_subgroup"), " 新增子级")
        self.btn_del_group = QPushButton(self.icon_mgr.get_icon("times_delete_group"), " 删除")
        self.btn_group_move_up = QPushButton(self.icon_mgr.get_icon("arrow_up_group"), " 上移")
        self.btn_group_move_down = QPushButton(self.icon_mgr.get_icon("arrow_down_group"), " 下移")
        self.btn_add_group.clicked.connect(self._add_sub_group)
        self.btn_del_group.clicked.connect(self._delete_group)
        self.btn_group_move_up.clicked.connect(self._move_group_up)
        self.btn_group_move_down.clicked.connect(self._move_group_down)
        left_btn_layout2.addWidget(self.btn_add_group)
        left_btn_layout2.addWidget(self.btn_del_group)
        left_btn_layout2.addWidget(self.btn_group_move_up)
        left_btn_layout2.addWidget(self.btn_group_move_down)
        left_btn_layout2.addStretch()
        left_layout.addLayout(left_btn_layout2)

        # 右面板
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 5, 5, 5)
        
        right_title_widget = QWidget()
        right_title_layout = QHBoxLayout(right_title_widget)
        right_title_layout.setContentsMargins(0, 0, 0, 0)
        right_icon = QLabel()
        right_icon.setPixmap(self.icon_mgr.get_icon("file_table_title").pixmap(24, 24))
        right_text = QLabel(" 当前条目下的底稿文件")
        right_text.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        right_title_layout.addWidget(right_icon)
        right_title_layout.addWidget(right_text)
        right_title_layout.addStretch()
        right_layout.addWidget(right_title_widget)

        self.table = QTableWidget()
        
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["文件名", "状态", "类型", "大小"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.setAcceptDrops(True)
        self.table.setDragDropMode(QAbstractItemView.DropOnly)
        self.table.dragEnterEvent = self._table_drag_enter_event
        self.table.dragMoveEvent = self._table_drag_move_event
        self.table.dropEvent = self._table_drop_event
        self.table.dragLeaveEvent = self._table_drag_leave_event
        right_layout.addWidget(self.table)

        right_btn_layout = QHBoxLayout()
        self.btn_add_file = QPushButton(self.icon_mgr.get_icon("plus_add_file"), " 添加文件")
        self.btn_move_up = QPushButton(self.icon_mgr.get_icon("arrow_up_file"), " 上移")
        self.btn_move_down = QPushButton(self.icon_mgr.get_icon("arrow_down_file"), " 下移")
        self.btn_del_file = QPushButton(self.icon_mgr.get_icon("times_remove_file"), " 移除")
        self.btn_move_first = QPushButton(self.icon_mgr.get_icon("thumbtack_move_first"), " 移到第一位")
        self.btn_move_last = QPushButton(self.icon_mgr.get_icon("thumbtack_move_last"), " 移到最后一位")
        self.btn_rename_file = QPushButton(self.icon_mgr.get_icon("edit_rename_button"), " 重命名")

        self.btn_add_file.clicked.connect(self._add_file)
        self.btn_move_up.clicked.connect(self._move_up)
        self.btn_move_down.clicked.connect(self._move_down)
        self.btn_del_file.clicked.connect(self._delete_file)
        self.btn_move_first.clicked.connect(self._move_to_first)
        self.btn_move_last.clicked.connect(self._move_to_last)
        self.btn_rename_file.clicked.connect(self._rename_file)

        right_btn_layout.addWidget(self.btn_add_file)
        right_btn_layout.addWidget(self.btn_move_up)
        right_btn_layout.addWidget(self.btn_move_down)
        right_btn_layout.addWidget(self.btn_del_file)
        right_btn_layout.addWidget(self.btn_move_first)
        right_btn_layout.addWidget(self.btn_move_last)
        right_btn_layout.addWidget(self.btn_rename_file)
        right_btn_layout.addStretch()
        right_layout.addLayout(right_btn_layout)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 1050])
        main_layout.addWidget(splitter, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label, 1)
        self.status_bar.addPermanentWidget(self.progress_bar)

    def _create_menubar(self):
        menubar = QMenuBar(self)
        self.setMenuBar(menubar)
        
        project_menu = menubar.addMenu("项目")
        action_new = QAction("新建项目", self)
        action_new.triggered.connect(self._go_to_new_project)
        project_menu.addAction(action_new)
        action_open = QAction("打开项目...", self)
        action_open.triggered.connect(self._go_to_open_project)
        project_menu.addAction(action_open)
        project_menu.addSeparator()
        action_save = QAction("保存项目", self)
        action_save.triggered.connect(self._save_project)
        action_save.setShortcut(QKeySequence("Ctrl+S"))
        project_menu.addAction(action_save)
        action_save_as = QAction("另存为...", self)
        action_save_as.triggered.connect(self._save_project_as)
        project_menu.addAction(action_save_as)
        project_menu.addSeparator()
        action_close = QAction("关闭项目", self)
        action_close.triggered.connect(self._close_project)
        project_menu.addAction(action_close)
        action_exit = QAction("退出", self)
        action_exit.triggered.connect(self._exit_app)
        project_menu.addAction(action_exit)
        
        export_menu = menubar.addMenu("导出")
        action_export = QAction("导出...", self)
        action_export.triggered.connect(self._start_export)
        action_export.setShortcut(QKeySequence("Ctrl+E"))
        export_menu.addAction(action_export)
        export_menu.addSeparator()
        action_export_mode1 = QAction("① 导出到单文件夹", self)
        action_export_mode1.triggered.connect(lambda: self._export_with_mode(1))
        export_menu.addAction(action_export_mode1)
        action_export_mode2 = QAction("② 按文件夹结构导出", self)
        action_export_mode2.triggered.connect(lambda: self._export_with_mode(2))
        export_menu.addAction(action_export_mode2)
        action_export_mode3 = QAction("③ 合并为单个PDF", self)
        action_export_mode3.triggered.connect(lambda: self._export_with_mode(3))
        export_menu.addAction(action_export_mode3)

    def _create_toolbar(self):
        toolbar = QToolBar()
        toolbar.setIconSize(QSize(24, 24))
        toolbar.setMovable(False)
        
        btn_save = QPushButton(self.icon_mgr.get_icon("save_button"), " 保存")
        btn_save.clicked.connect(self._save_project)
        btn_save.setToolTip("保存项目 (Ctrl+S)")
        toolbar.addWidget(btn_save)
        toolbar.addSeparator()
        
        btn_sort = QPushButton(self.icon_mgr.get_icon("sort_button"), " 排序")
        btn_sort.clicked.connect(self._sort_by_name)
        btn_sort.setToolTip("按名称排序（一次性）")
        toolbar.addWidget(btn_sort)
        toolbar.addSeparator()
        
        btn_import = QPushButton(self.icon_mgr.get_icon("folder_import_button"), " 导入")
        btn_import.clicked.connect(self._import_folder)
        btn_import.setToolTip("导入文件夹")
        toolbar.addWidget(btn_import)
        
        btn_add = QPushButton(self.icon_mgr.get_icon("file_add_button"), " 添加")
        btn_add.clicked.connect(self._add_file_from_toolbar)
        btn_add.setToolTip("添加文件")
        toolbar.addWidget(btn_add)
        
        toolbar.addSeparator()
        
        btn_export = QPushButton(self.icon_mgr.get_icon("play_export_button"), " 导出")
        btn_export.clicked.connect(self._start_export)
        btn_export.setToolTip("导出 (Ctrl+E)")
        toolbar.addWidget(btn_export)
        
        self.action_start = btn_export
        
        toolbar.addSeparator()
        
        btn_template = QPushButton(self.icon_mgr.get_icon("upload_template_button"), " 模板")
        btn_template.clicked.connect(self._export_as_template)
        btn_template.setToolTip("导出模板")
        toolbar.addWidget(btn_template)
        
        toolbar.addSeparator()
        
        btn_clear = QPushButton(self.icon_mgr.get_icon("trash_clear_button"), " 清空")
        btn_clear.clicked.connect(self._clear_project)
        btn_clear.setToolTip("清空项目")
        toolbar.addWidget(btn_clear)
        
        btn_log = QPushButton(self.icon_mgr.get_icon("list_log_button"), " 日志")
        btn_log.clicked.connect(self._show_log)
        btn_log.setToolTip("显示日志")
        toolbar.addWidget(btn_log)
        
        btn_workspace = QPushButton(self.icon_mgr.get_icon("folder_open_toolbar_workbench"), " 工作台")
        btn_workspace.clicked.connect(self._return_to_workspace)
        btn_workspace.setToolTip("返回工作台 (Ctrl+W)")
        toolbar.addWidget(btn_workspace)
        
        return toolbar

    def _create_title_bar(self):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_switch_project = QPushButton(self.icon_mgr.get_icon("bars_switch_button"), " 切换项目")
        self.btn_switch_project.setStyleSheet("""
            QPushButton {
                background-color: #e8e8e8;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: bold;
                color: #333;
            }
            QPushButton:hover { background-color: #d0d0d0; }
        """)
        self.btn_switch_project.clicked.connect(self._toggle_switch_panel)
        layout.addWidget(self.btn_switch_project)
        
        name_widget = QWidget()
        name_layout = QHBoxLayout(name_widget)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_icon = QLabel()
        name_icon.setPixmap(self.icon_mgr.get_icon("thumbtack_title_project").pixmap(24, 24))
        name_text = QLabel(f" 当前项目: {self.meta.name if self.meta and self.meta.name else '未命名'}")
        name_text.setStyleSheet("font-weight: bold; color: #2a5c8a; font-size: 10pt; margin-left: 10px;")
        name_layout.addWidget(name_icon)
        name_layout.addWidget(name_text)
        name_layout.addStretch()
        layout.addWidget(name_widget)
        
        layout.addStretch()
        if self.meta and self.meta.name:
            info_label = QLabel(f"{self.meta.project_type if hasattr(self.meta, 'project_type') else '自定义'}  |  共 {len(self.project_data.root.children)} 个分组  |  {self.total_files()} 个文件")
            info_label.setStyleSheet("color: #666; font-size: 9pt;")
            layout.addWidget(info_label)
        return widget

    def _go_to_new_project(self):
        if self.workspace:
            self.close()
    def _go_to_open_project(self):
        if self.workspace:
            self.close()
    def _save_project_as(self):
        if not self.meta:
            QMessageBox.warning(self, "提示", "请先创建或打开一个项目。")
            return
        if not self.projects_dir:
            QMessageBox.warning(self, "提示", "项目目录未设置。")
            return
        new_name, ok = QInputDialog.getText(
            self, "另存为",
            "请输入新的项目名称：",
            text=self.meta.name + "_副本"
        )
        if ok and new_name.strip():
            from core.project_manager import create_new_project, load_project
            new_file = create_new_project(new_name.strip(), self.meta.project_type, self.projects_dir)
            project_data, meta = load_project(new_file)
            if project_data:
                self.project_data = project_data
                self.meta = meta
                self.project_file_path = new_file
                self._update_tree()
                self.status_label.setText(f"✔ 项目已另存为: {new_name}")
    def _close_project(self):
        self.close()
    def _exit_app(self):
        QApplication.quit()
    def _export_with_mode(self, mode):
        self._start_export_with_mode(mode)
    def _start_export_with_mode(self, mode):
        if not self.project_data.root.children or self.total_files() == 0:
            QMessageBox.warning(self, "提示", "请先导入包含文件的文件夹。")
            return
        from gui.dialogs import ExportModeDialog
        dialog = ExportModeDialog(self)
        if mode == 1:
            dialog.check_mode1.setChecked(True)
            dialog.check_mode2.setChecked(False)
            dialog.check_mode3.setChecked(False)
        elif mode == 2:
            dialog.check_mode1.setChecked(False)
            dialog.check_mode2.setChecked(True)
            dialog.check_mode3.setChecked(False)
        else:
            dialog.check_mode1.setChecked(False)
            dialog.check_mode2.setChecked(False)
            dialog.check_mode3.setChecked(True)
        if dialog.exec_() != QDialog.Accepted:
            return
        result = dialog.get_result()
        self._run_export(result)
    def _run_export(self, result):
        modes = result.get('modes', [])
        export_scope = result.get('export_scope', 'all')
        output_format = result.get('output_format', 'pdf')
        generate_bookmark = result.get('generate_bookmark', False)
        output_path = result.get('output_path', '')
        add_prefix = result.get('add_prefix', False)
        if not output_path or not modes:
            return
        selected_groups = self.get_selected_group_names()
        selected_files = self.get_selected_file_paths()
        self.progress_window = ProgressWindow(self)
        self.progress_window.cancel_requested.connect(self._on_cancel_requested)
        self.progress_window.show()
        self.worker = ConvertWorker(
            self.project_data,
            modes=modes,
            export_scope=export_scope,
            output_format=output_format,
            generate_bookmark=generate_bookmark,
            output_path=output_path,
            options={'add_prefix': add_prefix},
            selected_groups=selected_groups if export_scope == 'selected_groups' else [],
            selected_files=selected_files if export_scope == 'selected_files' else []
        )
        self.worker.progress_updated.connect(self._on_progress_updated)
        self.worker.progress_detail.connect(self._on_progress_detail)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.error_occurred.connect(self._on_error_occurred)
        self.worker.finished_all.connect(self._on_finished_all)
        self.worker.log_message.connect(self._on_log_message)
        self.worker.mode_progress.connect(self._on_mode_progress)
        self.action_start.setEnabled(False)
        self.status_label.setText("正在导出...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.worker.start()

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Z:
            self._undo()
            event.accept()
            return
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_Y:
            self._redo()
            event.accept()
            return
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_E:
            self._start_export()
            event.accept()
            return
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_N:
            if self._has_focus_on_tree_or_table():
                self._add_group()
                event.accept()
                return
        if event.key() == Qt.Key_Delete:
            if self._has_focus_on_tree():
                self._delete_group()
                event.accept()
                return
            elif self._has_focus_on_table():
                self._delete_file()
                event.accept()
                return
        super().keyPressEvent(event)

    def _has_focus_on_tree(self): return self.tree.hasFocus()
    def _has_focus_on_table(self): return self.table.hasFocus()
    def _has_focus_on_tree_or_table(self): return self._has_focus_on_tree() or self._has_focus_on_table()

    def _show_delete_confirmation(self, item_type, item_name):
        if self.suppress_delete_warning:
            return True
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认删除")
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText(f"确定要删除{item_type}「{item_name}」吗？")
        msg_box.setInformativeText("此操作不可撤销！")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)
        check_box = QCheckBox("本次不再提示")
        check_box.setStyleSheet("margin-left: 20px;")
        msg_box.setCheckBox(check_box)
        result = msg_box.exec_()
        if check_box.isChecked():
            self.suppress_delete_warning = True
            self.status_label.setText("☝ 删除确认已关闭（本次会话内不再提示）")
        return result == QMessageBox.Yes

    def _save_project(self):
        if not self.meta:
            QMessageBox.warning(self, "提示", "请先创建或打开一个项目。")
            return
        if not self.project_file_path:
            QMessageBox.warning(self, "提示", "项目文件路径无效。")
            return
        self.meta.updated_at = datetime.now().isoformat()
        if save_project(self.project_data, self.meta, self.project_file_path):
            self.status_label.setText("✔ 项目已保存")
            self.log_messages.append(f"项目已保存: {self.project_file_path}")
            return True
        else:
            QMessageBox.critical(self, "错误", "保存项目失败，请检查文件权限。")
            return False

    def _return_to_workspace(self):
        if self.workspace:
            self._save_project()
            self.hide()
            self.workspace.show()
            self.workspace.raise_()
        else:
            QMessageBox.warning(self, "提示", "无法返回工作台。")

    def _import_folder(self):
        self._save_undo_state()
        has_existing = len(self.project_data.root.children) > 0
        dialog = FolderImportDialog(has_existing_groups=has_existing, parent=self)
        if dialog.exec_() != QDialog.Accepted:
            return
        folders, import_mode = dialog.get_result()
        if not folders:
            return
        if import_mode == 'replace':
            self.project_data.clear()
            self.log_messages.append("已清空现有分组（替换模式）")
        total_groups = 0
        for folder in folders:
            folder_name = os.path.basename(folder)
            self.status_label.setText(f"正在扫描: {folder_name} ...")
            QApplication.processEvents()
            try:
                temp_project = scan_folder(folder, root_group_name=folder_name)
                for child in temp_project.root.children:
                    child.remove_from_parent()
                    self.project_data.root.add_child(child)
                    total_groups += 1
            except Exception as e:
                QMessageBox.critical(self, "错误", f"扫描 {folder} 失败: {str(e)}")
                continue
        self._update_tree()
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setExpanded(True)
        self.status_label.setText(f"✔ 导入完成，新增 {total_groups} 个分组")
        self.log_messages.append(f"导入 {len(folders)} 个文件夹，新增 {total_groups} 个分组")
        self._save_project()

    # ==================== 左面板操作 ====================
    def _get_expanded_names(self):
        expanded = []
        def collect(item):
            for i in range(item.childCount()):
                child = item.child(i)
                if child.isExpanded():
                    group = child.data(0, Qt.UserRole)
                    if group and hasattr(group, 'get_full_path'):
                        expanded.append(group.get_full_path())
                collect(child)
        for i in range(self.tree.topLevelItemCount()):
            collect(self.tree.topLevelItem(i))
        return expanded

    def _set_expanded_names(self, names):
        def restore(item):
            for i in range(item.childCount()):
                child = item.child(i)
                group = child.data(0, Qt.UserRole)
                if group and hasattr(group, 'get_full_path') and group.get_full_path() in names:
                    child.setExpanded(True)
                restore(child)
        for i in range(self.tree.topLevelItemCount()):
            restore(self.tree.topLevelItem(i))

    def _update_tree(self):
        expanded_names = self._get_expanded_names()
        selected_group = self.current_group
        self.tree.clear()

        def add_node(parent_item, group):
            item = QTreeWidgetItem([group.name])
            item.setData(0, Qt.UserRole, group)
            item.setIcon(0, self.icon_mgr.get_icon("folder_open_tree_title"))
            if group.files:
                item.setText(1, f"{len(group.files)} 个文件")
                font = QFont("Microsoft YaHei", 9)
                font.setBold(True)
                item.setFont(1, font)
            else:
                item.setText(1, "")
                font = QFont("Microsoft YaHei", 9)
                font.setItalic(True)
                item.setForeground(1, Qt.gray)
                item.setFont(1, font)
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            if self.show_files and group.files:
                for file_item in group.files:
                    file_node = QTreeWidgetItem([f"  {file_item.name}"])
                    file_node.setData(0, Qt.UserRole, None)
                    file_node.setForeground(0, Qt.gray)
                    file_node.setIcon(0, self.icon_mgr.get_icon("file_add_button"))
                    item.addChild(file_node)
            for child in group.children:
                add_node(item, child)

        for group in self.project_data.root.children:
            add_node(None, group)

        self._set_expanded_names(expanded_names)
        if selected_group:
            self._select_group_in_tree(selected_group)

    def _find_item_by_path(self, path):
        def find_recursive(item):
            group = item.data(0, Qt.UserRole)
            if group and group.get_full_path() == path:
                return item
            for i in range(item.childCount()):
                child = item.child(i)
                result = find_recursive(child)
                if result:
                    return result
            return None
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            result = find_recursive(item)
            if result:
                return result
        return None

    def _on_tree_item_clicked(self, item):
        group = item.data(0, Qt.UserRole)
        if group:
            self.current_group = group
            self._update_table(group)

    def _show_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        action_rename = menu.addAction("重命名")
        action_rename.triggered.connect(lambda: self._rename_group(item))
        action_del = menu.addAction("删除")
        action_del.triggered.connect(self._delete_group)
        action_add = menu.addAction("同级新建")
        action_add.triggered.connect(self._add_group)
        action_add_sub = menu.addAction("子级新建")
        action_add_sub.triggered.connect(self._add_sub_group)
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def _rename_group(self, item):
        self._save_undo_state()
        group = item.data(0, Qt.UserRole)
        if not group:
            QMessageBox.warning(self, "提示", "请选择一个分组。")
            return
        new_name, ok = QInputDialog.getText(self, "重命名", "请输入新名称：", text=group.name)
        if ok and new_name.strip():
            group.name = new_name.strip()
            self._update_tree()
            self._select_group_in_tree(group)
            if group.parent and hasattr(group.parent, 'name'):
                parent_item = self._find_item_by_path(group.parent.get_full_path())
                if parent_item:
                    parent_item.setExpanded(True)
            self.status_label.setText(f"✔ 分组已重命名为: {group.name}")
            self._save_project()

    def _select_group_in_tree(self, target_group):
        def find_item(item):
            if item.data(0, Qt.UserRole) == target_group:
                return item
            for i in range(item.childCount()):
                result = find_item(item.child(i))
                if result:
                    return result
            return None
        for i in range(self.tree.topLevelItemCount()):
            result = find_item(self.tree.topLevelItem(i))
            if result:
                self.tree.setCurrentItem(result)
                self._on_tree_item_clicked(result)
                break

    def _add_group(self):
        self._save_undo_state()
        current_item = self.tree.currentItem()
        parent_group = self.project_data.root
        if current_item:
            current_group = current_item.data(0, Qt.UserRole)
            if current_group:
                if current_group.parent:
                    parent_group = current_group.parent
                else:
                    parent_group = self.project_data.root
        base_name = "未命名"
        name = base_name
        counter = 1
        existing_names = [c.name for c in parent_group.children]
        while name in existing_names:
            name = f"{base_name}({counter})"
            counter += 1
        new_group = GroupItem(name=name)
        parent_group.add_child(new_group)
        self._update_tree()
        self._select_group_in_tree(new_group)
        new_name, ok = QInputDialog.getText(self, "重命名条目", "请输入条目名称：", text=name)
        if ok and new_name.strip():
            final_name = new_name.strip()
            if final_name != name:
                existing_names = [c.name for c in parent_group.children if c != new_group]
                temp_name = final_name
                counter = 1
                while temp_name in existing_names:
                    temp_name = f"{final_name}({counter})"
                    counter += 1
                final_name = temp_name
            new_group.name = final_name
            self._update_tree()
            self._select_group_in_tree(new_group)
            self.status_label.setText(f"✔ 已创建同级分组: {final_name}")
        else:
            new_group.remove_from_parent()
            self._update_tree()
            self.status_label.setText("已取消创建")
            return
        self._save_project()

    def _add_sub_group(self):
        self._save_undo_state()
        current_item = self.tree.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选中一个分组。")
            return
        parent_group = current_item.data(0, Qt.UserRole)
        if not parent_group:
            QMessageBox.warning(self, "提示", "请选中一个完整的分组。")
            return
        name, ok = QInputDialog.getText(self, "新增子级", f"在「{parent_group.name}」下添加：")
        if ok and name.strip():
            new_group = GroupItem(name=name.strip())
            parent_group.add_child(new_group)
            self._update_tree()
            self._select_group_in_tree(new_group)
            self.status_label.setText(f"✔ 已添加子分组: {name}")
            self._save_project()

    def _delete_group(self):
        self._save_undo_state()
        item = self.tree.currentItem()
        if not item:
            return
        group = item.data(0, Qt.UserRole)
        if not group:
            return
        if not self._show_delete_confirmation("分组", group.name):
            return
        parent_group = group.parent
        group.remove_from_parent()
        self._update_tree()
        if parent_group and hasattr(parent_group, 'name'):
            parent_item = self._find_item_by_path(parent_group.get_full_path())
            if parent_item:
                parent_item.setExpanded(True)
        self.table.clearContents()
        self.table.setRowCount(0)
        self.current_group = None
        self.status_label.setText(f"✔ 已删除分组及其子项: {group.name}")
        self._save_project()

    def _move_group_up(self):
        self._save_undo_state()
        item = self.tree.currentItem()
        if not item:
            return
        group = item.data(0, Qt.UserRole)
        if not group or not group.parent:
            return
        siblings = group.parent.children
        idx = siblings.index(group)
        if idx > 0:
            siblings[idx], siblings[idx - 1] = siblings[idx - 1], siblings[idx]
            self._update_tree()
            self._select_group_in_tree(group)
            self.status_label.setText(f"⬆ 上移: {group.name}")
            self._save_project()

    def _move_group_down(self):
        self._save_undo_state()
        item = self.tree.currentItem()
        if not item:
            return
        group = item.data(0, Qt.UserRole)
        if not group or not group.parent:
            return
        siblings = group.parent.children
        idx = siblings.index(group)
        if idx < len(siblings) - 1:
            siblings[idx], siblings[idx + 1] = siblings[idx + 1], siblings[idx]
            self._update_tree()
            self._select_group_in_tree(group)
            self.status_label.setText(f"⬇ 下移: {group.name}")
            self._save_project()

    # ==================== 右面板操作 ====================
    def _update_table(self, group: GroupItem):
        self.table.setRowCount(0)
        if not group:
            return
        files = group.files
        self.table.setRowCount(len(files))
        for row, file_item in enumerate(files):
            display_name = file_item.name
            if hasattr(file_item, 'display_name') and file_item.display_name:
                display_name = file_item.display_name
            if row == 0:
                item = QTableWidgetItem(self.icon_mgr.get_icon("thumbtack_table_first_row", 16), display_name)
            else:
                item = QTableWidgetItem(display_name)
            self.table.setItem(row, 0, item)
            path_exists = os.path.exists(file_item.path)
            if path_exists:
                status_icon = self.icon_mgr.get_icon("check_circle_table_exists", 16)
                status_text = " 存在"
            else:
                status_icon = self.icon_mgr.get_icon("times_circle_table_missing", 16)
                status_text = " 缺失"
            status_item = QTableWidgetItem(status_icon, status_text)
            status_item.setTextAlignment(Qt.AlignCenter)
            if not path_exists:
                status_item.setForeground(Qt.red)
                status_item.setToolTip(f"文件不存在: {file_item.path}")
            else:
                status_item.setToolTip("文件存在")
            self.table.setItem(row, 1, status_item)
            self.table.setItem(row, 2, QTableWidgetItem(file_item.ext.upper() if file_item.ext else ""))
            size_kb = file_item.size / 1024
            if size_kb > 1024:
                size_str = f"{size_kb/1024:.1f} MB"
            else:
                size_str = f"{size_kb:.1f} KB"
            self.table.setItem(row, 3, QTableWidgetItem(size_str))
        if files:
            for col in range(4):
                item = self.table.item(0, col)
                if item:
                    item.setBackground(Qt.yellow)

    def _add_file(self):
        self._save_undo_state()
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先在左侧选择一个条目。")
            return
        file_paths, _ = QFileDialog.getOpenFileNames(
            self, "选择文件", "",
            "支持文件 (*.docx *.xlsx *.pdf *.jpg *.png *.doc *.xls);;所有文件 (*.*)"
        )
        if file_paths:
            for path in file_paths:
                exists = any(f.path == path for f in self.current_group.files)
                if not exists:
                    self.current_group.add_file(path)
            self._update_table(self.current_group)
            self._update_tree()
            self.status_label.setText(f"✔ 已添加 {len(file_paths)} 个文件")
            self._save_project()

    def _add_file_from_toolbar(self):
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先在左侧选中一个条目，再添加文件。")
            return
        self._add_file()

    def _delete_file(self):
        self._save_undo_state()
        if not self.current_group:
            return
        current_row = self.table.currentRow()
        if current_row < 0:
            return
        file_item = self.current_group.files[current_row]
        if not self._show_delete_confirmation("文件", file_item.name):
            return
        self.current_group.remove_file(current_row)
        self._update_table(self.current_group)
        self._update_tree()
        self.status_label.setText(f"✔ 已移除文件: {file_item.name}")
        self._save_project()

    def _move_up(self):
        self._save_undo_state()
        if not self.current_group:
            return
        current_row = self.table.currentRow()
        if current_row <= 0:
            return
        files = self.current_group.files
        files[current_row], files[current_row - 1] = files[current_row - 1], files[current_row]
        for i, f in enumerate(files):
            f.order = i
        self._update_table(self.current_group)
        self.table.selectRow(current_row - 1)
        self._save_project()

    def _move_down(self):
        self._save_undo_state()
        if not self.current_group:
            return
        current_row = self.table.currentRow()
        files = self.current_group.files
        if current_row >= len(files) - 1 or current_row < 0:
            return
        files[current_row], files[current_row + 1] = files[current_row + 1], files[current_row]
        for i, f in enumerate(files):
            f.order = i
        self._update_table(self.current_group)
        self.table.selectRow(current_row + 1)
        self._save_project()

    def _move_to_first(self):
        self._save_undo_state()
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先在左侧选择一个条目。")
            return
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先在右侧选中一个文件。")
            return
        files = self.current_group.files
        if len(files) <= 1 or current_row == 0:
            return
        item = files.pop(current_row)
        files.insert(0, item)
        for i, f in enumerate(files):
            f.order = i
        self._update_table(self.current_group)
        self.table.selectRow(0)
        self._save_project()

    def _move_to_last(self):
        self._save_undo_state()
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先在左侧选择一个条目。")
            return
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先在右侧选中一个文件。")
            return
        files = self.current_group.files
        if len(files) <= 1 or current_row == len(files) - 1:
            return
        item = files.pop(current_row)
        files.append(item)
        for i, f in enumerate(files):
            f.order = i
        self._update_table(self.current_group)
        self.table.selectRow(len(files) - 1)
        self._save_project()

    def _contains_invalid_chars(self, name): return bool(re.search(r'[\\/:*?"<>|]', name))

    def _rename_file(self):
        self._save_undo_state()
        if not self.current_group:
            QMessageBox.warning(self, "提示", "请先在左侧选择一个条目。")
            return
        current_row = self.table.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "提示", "请先在右侧选中一个文件。")
            return
        file_item = self.current_group.files[current_row]
        current_display = getattr(file_item, 'display_name', file_item.name)
        new_name, ok = QInputDialog.getText(
            self, "重命名文件",
            "请输入新的显示名称（不修改物理文件）：",
            text=current_display
        )
        if ok:
            new_name = new_name.strip()
            if not new_name:
                QMessageBox.warning(self, "提示", "名称不能为空。")
                return
            if self._contains_invalid_chars(new_name):
                QMessageBox.warning(self, "提示", "名称不能包含以下字符：\\ / : * ? \" < > |")
                return
            file_item.display_name = new_name
            self._update_table(self.current_group)
            self.status_label.setText(f"✔ 文件已重命名为: {new_name}")
            self._save_project()

    def _start_export(self):
        if not self.project_data.root.children or self.total_files() == 0:
            QMessageBox.warning(self, "提示", "请先导入包含文件的文件夹。")
            return
        selected_groups = self.get_selected_group_names()
        selected_files = self.get_selected_file_paths()
        dialog = ExportModeDialog(self)
        dialog.set_selected_info(selected_groups, selected_files)
        if dialog.exec_() != QDialog.Accepted:
            return
        result = dialog.get_result()
        self._run_export(result)

    def _on_cancel_requested(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("正在取消...")
            self.progress_bar.setVisible(False)
            if self.progress_window:
                self.progress_window.set_cancelled()

    def total_files(self):
        def count_files(node):
            count = len(node.files)
            for child in node.children:
                count += count_files(child)
            return count
        return count_files(self.project_data.root)

    def get_selected_group_names(self):
        selected_names = []
        for item in self.tree.selectedItems():
            group = item.data(0, Qt.UserRole)
            if group:
                selected_names.append(group.get_full_path())
        return selected_names

    def get_selected_file_paths(self):
        selected_paths = []
        for row in self.table.selectedIndexes():
            if row.column() == 0:
                if self.current_group and row.row() < len(self.current_group.files):
                    file_item = self.current_group.files[row.row()]
                    if file_item and file_item.path not in selected_paths:
                        selected_paths.append(file_item.path)
        return selected_paths

    def _on_progress_updated(self, progress, status):
        self.progress_bar.setValue(progress)
        self.status_label.setText(status)
    def _on_progress_detail(self, total_percent, current_percent, file_name, group_name, current_idx, total_files, status_text):
        if self.progress_window:
            self.progress_window.update_progress(total_percent, current_percent, file_name, group_name, current_idx, total_files, status_text)
    def _on_mode_progress(self, current, total, mode_name):
        if self.progress_window:
            self.progress_window.update_mode_progress(current, total, mode_name)
    def _on_file_done(self, filename, success):
        icon = "✔" if success else "✘"
        self.status_label.setText(f"{icon} {filename}")
    def _on_error_occurred(self, file_path, error_msg):
        pass
    def _on_finished_all(self, all_success, summary):
        self.action_start.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.status_label.setText("就绪")
        self.last_conversion_summary = summary
        if self.progress_window:
            self.progress_window.set_finished(all_success, summary)
            QTimer.singleShot(1000, self._close_progress_window)
        has_failed = self.worker and len(self.worker.failed_list) > 0
        if all_success:
            QMessageBox.information(self, "✔ 完成", summary)
        else:
            if has_failed:
                QTimer.singleShot(1200, self._show_retry_dialog)
            else:
                QMessageBox.warning(self, "完成（部分失败）", summary)
    def _close_progress_window(self):
        if self.progress_window:
            self.progress_window.close()
            self.progress_window = None
    def _on_log_message(self, message):
        self.log_messages.append(message)
        print(f"[Worker] {message}")

    def _show_retry_dialog(self):
        if not self.worker or not self.worker.failed_list:
            return
        dialog = RetryDialog(self.worker.failed_list, self)
        dialog.retry_finished.connect(self._on_retry_finished)
        dialog.exec_()
    def _on_retry_finished(self, all_success, summary):
        if all_success:
            QMessageBox.information(self, "✔ 重试完成", summary)
        else:
            if self.worker and len(self.worker.failed_list) > 0:
                reply = QMessageBox.warning(
                    self, "重试完成",
                    f"{summary}\n\n仍有 {len(self.worker.failed_list)} 个文件失败。\n是否再次重试？",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self._show_retry_dialog()
            else:
                QMessageBox.warning(self, "重试完成", summary)
    def _retry_failed(self):
        if not self.worker or not self.worker.failed_list:
            QMessageBox.information(self, "提示", "没有失败的文件可以重试。")
            return
        self._show_retry_dialog()

    def _show_log(self):
        dialog = LogDialog(self.log_messages, self)
        dialog.exec_()

    def _export_as_template(self):
        if not self.project_data.root.children:
            QMessageBox.warning(self, "提示", "当前项目没有分组，无法导出模板。")
            return
        if not self.projects_dir:
            QMessageBox.warning(self, "提示", "项目目录未设置，无法导出模板。")
            return
        name, ok1 = QInputDialog.getText(self, "导出模板", "请输入模板名称:")
        if not ok1 or not name.strip():
            return
        description, ok2 = QInputDialog.getText(self, "导出模板", "请输入模板描述（可选）:")
        if not ok2:
            return
        if export_template(self.project_data, name.strip(), description.strip() or "用户自定义模板", self.projects_dir):
            QMessageBox.information(self, "成功", f"模板「{name}」已导出成功！\n可在新建项目时选择此模板。")
            self.status_label.setText(f"✔ 模板已导出: {name}")
        else:
            QMessageBox.critical(self, "错误", "导出模板失败，请检查文件权限。")

    def _sort_by_name(self):
        self._save_undo_state()
        if not self.project_data.root.children:
            return
        def recursive_sort(node):
            node.children.sort(key=lambda g: g.name)
            for child in node.children:
                recursive_sort(child)
        recursive_sort(self.project_data.root)
        self._update_tree()
        self.status_label.setText("✔ 已按名称排序")
        self._save_project()

    def _collapse_all(self):
        self.tree.collapseAll()
        self.expanded_items.clear()

    def _toggle_show_files(self):
        self.show_files = not self.show_files
        if self.show_files:
            self.btn_show_files.setText(" 隐藏文件")
            self.btn_show_files.setIcon(self.icon_mgr.get_icon("folder_new_button"))
        else:
            self.btn_show_files.setText(" 显示文件")
            self.btn_show_files.setIcon(self.icon_mgr.get_icon("file_show_files_button"))
        self._update_tree()

    def _toggle_switch_panel(self):
        if self.switch_panel is None:
            return
        if self.switch_panel.isVisible():
            self.switch_panel.hide_panel()
        else:
            rect = self.btn_switch_project.rect()
            global_rect = self.btn_switch_project.mapToGlobal(rect.topLeft())
            anchor_rect = QRect(global_rect, rect.size())
            self.switch_panel.show_panel(anchor_rect)

    def _on_switch_project(self, file_path):
        from core.project_manager import load_project
        project_data, meta = load_project(file_path)
        if project_data:
            self.project_data = project_data
            self.meta = meta
            self.project_file_path = file_path
            self.setWindowTitle(f"底稿文件整理工具 v2.0.0 - {self.meta.name if self.meta else '未命名'}")
            self._update_tree()
            self.status_label.setText(f"✔ 已切换到项目: {self.meta.name if self.meta else '未知'}")
        else:
            QMessageBox.critical(self, "错误", "加载项目失败，文件可能已损坏。")

    def _tree_drag_enter_event(self, event):
        if event.mimeData().hasUrls():
            self.drag_is_external = True
            event.acceptProposedAction()
        else:
            self.drag_is_external = False
            QTreeWidget.dragEnterEvent(self.tree, event)

    def _tree_drag_move_event(self, event):
        self._clear_all_highlights()
        self.drag_target_item = None
        self.drag_over_blank = False
        if event.mimeData().hasUrls():
            self.drag_is_external = True
            pos = event.pos()
            item = self.tree.itemAt(pos)
            if item:
                group = item.data(0, Qt.UserRole)
                if group is not None:
                    self.drag_target_item = item
                    item.setBackground(0, QBrush(QColor(0, 100, 255, 60)))
                    item.setBackground(1, QBrush(QColor(0, 100, 255, 60)))
            else:
                self.drag_over_blank = True
            self.tree.viewport().update()
            event.acceptProposedAction()
            return
        self.drag_is_external = False
        pos = event.pos()
        item = self.tree.itemAt(pos)
        if not item:
            self.drag_over_blank = True
        else:
            group = item.data(0, Qt.UserRole)
            if group is not None:
                self.drag_target_item = item
                item.setBackground(0, QBrush(QColor(0, 100, 255, 60)))
                item.setBackground(1, QBrush(QColor(0, 100, 255, 60)))
        self.tree.viewport().update()
        event.accept()

    def _tree_drag_leave_event(self, event):
        self.drag_target_item = None
        self.drag_over_blank = False
        self._clear_all_highlights()
        self.tree.viewport().update()
        QTreeWidget.dragLeaveEvent(self.tree, event)

    def _tree_paint_event(self, event):
        QTreeWidget.paintEvent(self.tree, event)
        painter = QPainter(self.tree.viewport())
        painter.setRenderHint(QPainter.Antialiasing)
        if self.drag_target_item:
            rect = self.tree.visualItemRect(self.drag_target_item)
            y = rect.top()
            painter.setPen(QPen(QColor(0, 150, 255, 200), 3))
            painter.drawLine(10, y, self.tree.width() - 10, y)
        if self.drag_over_blank:
            if self.drag_is_external:
                text = "📂 将添加到当前选中分组"
            else:
                text = "📂 将移动到根目录"
            font = painter.font()
            font.setPointSize(11)
            font.setFamily("Microsoft YaHei")
            painter.setFont(font)
            fm = painter.fontMetrics()
            text_width = fm.width(text)
            text_height = fm.height()
            x = (self.tree.width() - text_width) // 2
            y = (self.tree.height() - text_height) // 2
            painter.setPen(QPen(QColor(150, 150, 150, 150), 1.5))
            painter.setBrush(QBrush(QColor(240, 245, 248, 140)))
            painter.drawRoundedRect(x - 20, y - 12, text_width + 40, text_height + 24, 10, 10)
            painter.setPen(QPen(QColor(100, 100, 100, 180)))
            painter.drawText(x, y + fm.ascent(), text)
        painter.end()

    def _clear_all_highlights(self):
        def clear_item(item):
            item.setBackground(0, QBrush(Qt.NoBrush))
            item.setBackground(1, QBrush(Qt.NoBrush))
            for i in range(item.childCount()):
                clear_item(item.child(i))
        for i in range(self.tree.topLevelItemCount()):
            clear_item(self.tree.topLevelItem(i))

    def _tree_drop_event(self, event):
        self._clear_all_highlights()
        self.drag_target_item = None
        self.drag_over_blank = False
        self.tree.viewport().update()
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
            pos = event.pos()
            item = self.tree.itemAt(pos)
            target_group = None
            if item:
                target_group = item.data(0, Qt.UserRole)
            folders = [p for p in paths if os.path.isdir(p)]
            files = [p for p in paths if os.path.isfile(p)]
            if folders:
                if target_group is None:
                    for folder in folders:
                        temp = scan_folder(folder, root_group_name=os.path.basename(folder))
                        for g in temp.root.children:
                            g.remove_from_parent()
                            self.project_data.root.add_child(g)
                    self._update_tree()
                    self.status_label.setText(f"✔ 拖拽导入文件夹（根级）")
                else:
                    for folder in folders:
                        temp = scan_folder(folder, root_group_name=os.path.basename(folder))
                        for g in temp.root.children:
                            g.remove_from_parent()
                            target_group.add_child(g)
                    self._update_tree()
                    if target_group is not None:
                        target_item = self._find_item_by_path(target_group.get_full_path())
                        if target_item:
                            target_item.setExpanded(True)
                    self.status_label.setText(f"✔ 拖拽导入文件夹（子级）")
                event.acceptProposedAction()
                return
            if files:
                if target_group is None:
                    target_group = self.current_group
                if target_group:
                    for path in files:
                        if os.path.isfile(path):
                            target_group.add_file(path)
                    self._update_tree()
                    if target_group is not None:
                        target_item = self._find_item_by_path(target_group.get_full_path())
                        if target_item:
                            target_item.setExpanded(True)
                    self.status_label.setText(f"✔ 拖拽导入 {len(files)} 个文件")
                else:
                    QMessageBox.warning(self, "提示", "请先选中一个分组。")
                event.acceptProposedAction()
                return
        source_item = self.tree.currentItem()
        if not source_item:
            event.ignore()
            return
        source_group = source_item.data(0, Qt.UserRole)
        if not source_group:
            event.ignore()
            return
        pos = event.pos()
        target_item = self.tree.itemAt(pos)
        target_group = None
        if target_item:
            target_group = target_item.data(0, Qt.UserRole)
        if not target_group:
            source_group.remove_from_parent()
            self.project_data.root.add_child(source_group)
            self._update_tree()
            self.status_label.setText("✔ 移动到根目录")
            event.accept()
            return
        if target_group == source_group or target_group in source_group.children:
            event.ignore()
            return
        source_group.remove_from_parent()
        target_group.add_child(source_group)
        self._update_tree()
        self._select_group_in_tree(source_group)
        self.status_label.setText(f"✔ 移动到: {target_group.name}")
        event.accept()

    def _table_drag_enter_event(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def _table_drag_move_event(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def _table_drag_leave_event(self, event):
        event.ignore()

    def _table_drop_event(self, event):
        if not event.mimeData().hasUrls():
            event.ignore()
            return
        target_group = self.current_group
        if not target_group:
            QMessageBox.warning(self, "提示", "请先在左侧选中一个分组。")
            event.ignore()
            return
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        supported_exts = {'.docx', '.xlsx', '.pdf', '.jpg', '.jpeg', '.png', '.doc', '.xls'}
        added_count = 0
        for path in paths:
            if not os.path.isfile(path):
                continue
            ext = os.path.splitext(path)[1].lower()
            if ext not in supported_exts:
                continue
            exists = any(f.path == path for f in target_group.files)
            if not exists:
                target_group.add_file(path)
                added_count += 1
        if added_count > 0:
            self._update_table(target_group)
            self._update_tree()
            self.status_label.setText(f"✔ 拖拽导入 {added_count} 个文件")
            self._save_project()
        else:
            self.status_label.setText("☝ 没有可导入的文件")
        event.acceptProposedAction()

    def _clear_project(self):
        self._save_undo_state()
        if self.project_data.root.children:
            if not self._show_delete_confirmation("所有分组和文件", "当前项目全部内容"):
                return
            self.project_data.clear()
            self._update_tree()
            self.table.clearContents()
            self.table.setRowCount(0)
            self.current_group = None
            self.status_label.setText("🗑 项目已清空")
            self.log_messages.clear()
            self._save_project()

    def _save_undo_state(self):
        if self.is_undoing:
            return
        snapshot = copy.deepcopy(self.project_data)
        self.undo_stack.append(snapshot)
        if len(self.undo_stack) > self.max_undo_steps:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def _undo(self):
        if not self.undo_stack:
            self.status_label.setText("☝ 没有可撤销的操作")
            return
        self.redo_stack.append(copy.deepcopy(self.project_data))
        self.is_undoing = True
        self.project_data = self.undo_stack.pop()
        self._update_tree()
        if self.current_group:
            self._select_group_in_tree(self.current_group)
        self.is_undoing = False
        self.status_label.setText("↩️ 已撤销")

    def _redo(self):
        if not self.redo_stack:
            self.status_label.setText("☝ 没有可重做的操作")
            return
        self.undo_stack.append(copy.deepcopy(self.project_data))
        self.is_undoing = True
        self.project_data = self.redo_stack.pop()
        self._update_tree()
        if self.current_group:
            self._select_group_in_tree(self.current_group)
        self.is_undoing = False
        self.status_label.setText("↪️ 已重做")

    def closeEvent(self, event):
        if self.workspace and self.workspace.isVisible() is False:
            self.workspace.show()
            self.workspace.raise_()
        self.closed.emit()
        event.accept()