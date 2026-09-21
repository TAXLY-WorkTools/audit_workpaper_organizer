"""
导入文件夹选项对话框
一个窗口，两个区域：
- 左侧：文件系统树（支持 Ctrl/Shift 多选，双击添加到列表）
- 右侧：已选文件夹列表（支持单个移除）
- 上方：搜索框（过滤显示包含关键词的文件夹）
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QRadioButton, QPushButton, QLabel, QMessageBox,
    QListWidget, QListWidgetItem, QWidget, QSplitter,
    QTreeView, QAbstractItemView, QFileSystemModel, QLineEdit
)
from PyQt5.QtCore import Qt, QDir, QSortFilterProxyModel, QSize
from PyQt5.QtGui import QIcon
from gui.icon_manager import IconManager


class FolderFilterProxyModel(QSortFilterProxyModel):
    """自定义过滤模型：根据文件夹路径过滤"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.filter_pattern = ""

    def setFilterPattern(self, pattern):
        self.filter_pattern = pattern.lower().strip()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self.filter_pattern:
            return True

        source_model = self.sourceModel()
        if not source_model:
            return True

        index = source_model.index(source_row, 0, source_parent)
        if not index.isValid():
            return True

        file_path = source_model.filePath(index)
        if not file_path:
            return True

        if self.filter_pattern in file_path.lower():
            return True

        return self._has_matching_child(index)

    def _has_matching_child(self, parent_index):
        source_model = self.sourceModel()
        if not source_model:
            return False

        child_count = source_model.rowCount(parent_index)
        for row in range(child_count):
            child_index = source_model.index(row, 0, parent_index)
            if not child_index.isValid():
                continue
            file_path = source_model.filePath(child_index)
            if file_path and self.filter_pattern in file_path.lower():
                return True
            if self._has_matching_child(child_index):
                return True
        return False


class FolderImportDialog(QDialog):
    """导入文件夹选项对话框"""
    
    def __init__(self, has_existing_groups: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导入文件夹")
        self.setModal(True)
        self.setMinimumWidth(850)
        self.setMinimumHeight(550)
        
        self.has_existing_groups = has_existing_groups
        self.selected_folders = []
        self.import_mode = 'append'
        # 初始化图标管理器
        self.icon_mgr = IconManager()
        
        self._init_ui()
        self._update_ui_state()
    
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(10)
        
        # ---------- 顶部提示 ----------
        tip_widget = QWidget()
        tip_layout = QHBoxLayout(tip_widget)
        tip_layout.setContentsMargins(5, 5, 5, 5)
        tip_icon = QLabel()
        tip_icon.setPixmap(self.icon_mgr.get_icon("lightbulb_import_tip").pixmap(16, 16))
        tip_text = QLabel(" 左侧树中双击文件夹添加到列表（Ctrl多选，Shift连续选择）")
        tip_text.setStyleSheet("color: #555; font-size: 9pt;")
        tip_layout.addWidget(tip_icon)
        tip_layout.addWidget(tip_text)
        tip_layout.addStretch()
        tip_widget.setStyleSheet("background-color: #f0f0f0; border-radius: 3px;")
        main_layout.addWidget(tip_widget)
        
        
        # ---------- 主要区域：分割器 ----------
        splitter = QSplitter(Qt.Horizontal)
        
        # === 左侧：文件系统树 ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 5, 0)
        
        left_title_widget = QWidget()
        left_title_layout = QHBoxLayout(left_title_widget)
        left_title_layout.setContentsMargins(0, 0, 0, 0)
        left_title_icon = QLabel()
        left_title_icon.setPixmap(self.icon_mgr.get_icon("folder_dialog_sidebar").pixmap(16, 16))
        left_title_text = QLabel(" 此电脑")
        left_title_text.setStyleSheet("font-weight: bold;")
        left_title_layout.addWidget(left_title_icon)
        left_title_layout.addWidget(left_title_text)
        left_title_layout.addStretch()
        left_layout.addWidget(left_title_widget)
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("🔍"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索文件夹...")
        self.search_input.addAction(self.icon_mgr.get_icon("search_import_dialog"), QLineEdit.LeadingPosition)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)
        
        self.tree_view = QTreeView()
        self.tree_view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree_view.setAnimated(True)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.header().setSortIndicatorShown(True)
        
        # 文件系统模型
        self.source_model = QFileSystemModel()
        self.source_model.setRootPath("")
        self.source_model.setFilter(QDir.AllDirs | QDir.NoDotAndDotDot)
        
        # 代理模型（用于搜索过滤）
        self.proxy_model = FolderFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.source_model)
        
        self.tree_view.setModel(self.proxy_model)
        
        root_index = self.source_model.index("")
        proxy_root = self.proxy_model.mapFromSource(root_index)
        self.tree_view.setRootIndex(proxy_root)
        
        self.tree_view.setColumnWidth(0, 250)
        for i in range(1, self.source_model.columnCount()):
            self.tree_view.hideColumn(i)
        
        # ===== 修改点：双击添加到列表（而非单击） =====
        self.tree_view.doubleClicked.connect(self._on_tree_double_clicked)
        
        left_layout.addWidget(self.tree_view)
        
        self.selected_count_label = QLabel("已选 0 个文件夹")
        self.selected_count_label.setStyleSheet("color: #666;")
        left_layout.addWidget(self.selected_count_label)
        
        splitter.addWidget(left_widget)
        
        # === 右侧：已选文件夹列表 ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(5, 0, 0, 0)
        
        right_title_widget = QWidget()
        right_title_layout = QHBoxLayout(right_title_widget)
        right_title_layout.setContentsMargins(0, 0, 0, 0)
        right_title_icon = QLabel()
        right_title_icon.setPixmap(self.icon_mgr.get_icon("list_dialog_selected").pixmap(16, 16))
        right_title_text = QLabel(" 已选文件夹列表")
        right_title_text.setStyleSheet("font-weight: bold;")
        right_title_layout.addWidget(right_title_icon)
        right_title_layout.addWidget(right_title_text)
        right_title_layout.addStretch()
        right_layout.addWidget(right_title_widget)
        
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        right_layout.addWidget(self.list_widget)
        
        btn_layout = QHBoxLayout()
        self.btn_remove_selected = QPushButton(self.icon_mgr.get_icon("times_remove_dialog"), " 移除选中")
        self.btn_remove_selected.clicked.connect(self._remove_selected)
        btn_layout.addWidget(self.btn_remove_selected)
        
        self.btn_clear = QPushButton(self.icon_mgr.get_icon("trash_clear_dialog"), " 清空全部")
        self.btn_clear.clicked.connect(self._clear_all)
        btn_layout.addWidget(self.btn_clear)
        
        btn_layout.addStretch()
        right_layout.addLayout(btn_layout)
        
        self.list_count_label = QLabel("共 0 个文件夹")
        self.list_count_label.setStyleSheet("color: #666;")
        right_layout.addWidget(self.list_count_label)
        
        splitter.addWidget(right_widget)
        
        splitter.setSizes([500, 350])
        main_layout.addWidget(splitter, 1)
        
        # ---------- 导入模式 ----------
        if self.has_existing_groups:
            mode_group = QGroupBox("导入模式")
            mode_layout = QVBoxLayout(mode_group)
            
            self.radio_append = QRadioButton("追加模式（推荐）")
            self.radio_append.setChecked(True)
            self.radio_append.setToolTip("新文件夹作为新分组添加到现有项目，不影响已有内容")
            mode_layout.addWidget(self.radio_append)
            
            desc_append = QLabel("  将新文件夹的内容作为新分组添加到现有项目末尾")
            desc_append.setStyleSheet("color: #666; font-size: 9pt; margin-left: 20px;")
            desc_append.setWordWrap(True)
            mode_layout.addWidget(desc_append)
            
            self.radio_replace = QRadioButton("替换模式")
            self.radio_replace.setToolTip("清空现有分组，用新文件夹结构替换")
            mode_layout.addWidget(self.radio_replace)
            
            desc_replace = QLabel("  清空当前所有分组，用导入的文件夹结构替换")
            desc_replace.setStyleSheet("color: #ff6b6b; font-size: 9pt; margin-left: 20px;")
            desc_replace.setWordWrap(True)
            mode_layout.addWidget(desc_replace)
            
            main_layout.addWidget(mode_group)
        
        # ---------- 确认/取消 ----------
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_ok = QPushButton("开始导入")
        self.btn_ok.setDefault(True)
        self.btn_ok.clicked.connect(self._on_ok)
        btn_layout.addWidget(self.btn_ok)
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        main_layout.addLayout(btn_layout)
        
        self._update_ui_state()
    
    def _on_search_text_changed(self, text):
        self.proxy_model.setFilterPattern(text)
        self.tree_view.expandAll()
    
    def _on_tree_double_clicked(self, index):
        """双击树节点时添加到右侧列表"""
        if not index.isValid():
            return
        
        # 通过代理模型获取源模型的索引
        source_idx = self.proxy_model.mapToSource(index)
        if not source_idx.isValid():
            return
        
        # 只处理第一列
        if index.column() != 0:
            return
        
        path = self.source_model.filePath(source_idx)
        if not path or not os.path.isdir(path):
            return
        
        if path not in self.selected_folders:
            self.selected_folders.append(path)
            item = QListWidgetItem(path)
            self.list_widget.addItem(item)
            self._update_ui_state()
    
    def _remove_selected(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            QMessageBox.information(self, "提示", "请先在右侧列表中选中要移除的文件夹。")
            return
        for item in selected_items:
            path = item.text()
            self.list_widget.takeItem(self.list_widget.row(item))
            if path in self.selected_folders:
                self.selected_folders.remove(path)
        self._update_ui_state()
    
    def _clear_all(self):
        if self.list_widget.count() == 0:
            return
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有已选文件夹吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.list_widget.clear()
            self.selected_folders.clear()
            self._update_ui_state()
    
    def _update_ui_state(self):
        count = self.list_widget.count()
        self.selected_count_label.setText(f"已选 {self.list_widget.count()} 个文件夹")
        self.list_count_label.setText(f"共 {count} 个文件夹")
        self.btn_ok.setEnabled(count > 0)
    
    def _on_ok(self):
        if self.list_widget.count() == 0:
            QMessageBox.warning(self, "提示", "请至少选择一个文件夹。")
            return
        
        if self.has_existing_groups:
            if self.radio_append.isChecked():
                self.import_mode = 'append'
            else:
                self.import_mode = 'replace'
        else:
            self.import_mode = 'append'
        
        self.selected_folders = []
        for i in range(self.list_widget.count()):
            self.selected_folders.append(self.list_widget.item(i).text())
        
        self.accept()
    
    def get_result(self):
        return self.selected_folders, self.import_mode