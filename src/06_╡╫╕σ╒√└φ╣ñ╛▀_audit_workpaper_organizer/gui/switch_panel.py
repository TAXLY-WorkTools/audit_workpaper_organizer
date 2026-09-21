"""
项目切换边栏 - 悬浮面板，VSCode 风格
点击主窗口的“☰ 切换项目”按钮展开，覆盖在条目列之上
"""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QApplication
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QTimer, QSize
from PyQt5.QtGui import QFont, QColor, QPalette
from gui.icon_manager import IconManager


class SwitchPanel(QWidget):
    """项目切换边栏 - 悬浮面板"""
    
    project_selected = pyqtSignal(str)  # 传递项目文件路径
    new_project_requested = pyqtSignal()
    
    def __init__(self, projects_dir: str, parent=None):
        super().__init__(parent)
        self.projects_dir = projects_dir
        # 初始化图标管理器
        self.icon_mgr = IconManager()
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        
        # 阴影效果（使用 QFrame 模拟）
        self.setStyleSheet("""
            QWidget#panel {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
            QListWidget {
                background: transparent;
                border: none;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 3px;
            }
            QListWidget::item:hover {
                background-color: #e0e0e0;
            }
            QListWidget::item:selected {
                background-color: #cce8ff;
            }
            QLabel#title {
                font-weight: bold;
                color: #333;
                padding: 8px 10px;
                background-color: #e8e8e8;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QPushButton#new_btn {
                background-color: transparent;
                border: none;
                color: #0078d4;
                font-weight: bold;
                padding: 5px;
            }
            QPushButton#new_btn:hover {
                background-color: #e0e0e0;
                border-radius: 3px;
            }
        """)
        
        # 主面板
        self.panel = QFrame(self)
        self.panel.setObjectName("panel")
        self.panel.setStyleSheet("background-color: #f5f5f5; border: 1px solid #ccc; border-radius: 4px;")
        
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 标题栏（图标+文字组合）
        title_layout = QHBoxLayout()
        title_layout.setContentsMargins(10, 8, 10, 8)
        title_widget = QWidget()
        title_inner_layout = QHBoxLayout(title_widget)
        title_inner_layout.setContentsMargins(0, 0, 0, 0)
        title_icon = QLabel()
        title_icon.setPixmap(self.icon_mgr.get_icon("folder_switch_panel_title").pixmap(24, 24))
        title = QLabel(" 切换项目")
        title.setObjectName("title")
        title_inner_layout.addWidget(title_icon)
        title_inner_layout.addWidget(title)
        title_layout.addWidget(title_widget)

        title_layout.addStretch()
        close_btn = QPushButton()
        close_btn.setIcon(self.icon_mgr.get_icon("close_panel"))
        close_btn.setIconSize(QSize(20, 20))
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("background: transparent; border: none;")
        close_btn.clicked.connect(self.hide_panel)
        title_layout.addWidget(close_btn)
        close_btn.setIconSize(QSize(20, 20))
        close_btn.setFixedSize(24, 24)
        close_btn.setStyleSheet("background: transparent; border: none;")
        close_btn.clicked.connect(self.hide_panel)
        title_layout.addWidget(close_btn)
        layout.addLayout(title_layout)
        
        # 项目列表
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)
        
        # 底部操作
        bottom_layout = QHBoxLayout()
        bottom_layout.setContentsMargins(10, 8, 10, 8)
        new_btn = QPushButton(self.icon_mgr.get_icon("plus_circle_switch_new"), " 新建项目")
        new_btn.setObjectName("new_btn")
        new_btn.clicked.connect(self._on_new_project)
        bottom_layout.addWidget(new_btn)
        bottom_layout.addStretch()
        layout.addLayout(bottom_layout)
        
        # 大小和位置
        self.panel.setGeometry(0, 0, 300, 400)
        self.setFixedSize(300, 400)
        
        # 加载项目列表
        self._refresh_projects()
    
    def show_panel(self, anchor_rect):
        """在指定位置显示面板"""
        # 计算位置：在锚点矩形下方或上方
        x = anchor_rect.x()
        y = anchor_rect.y() + anchor_rect.height() + 2
        # 如果超出屏幕底部，则显示在上方
        screen = QApplication.primaryScreen().geometry()
        if y + self.height() > screen.height() - 100:
            y = anchor_rect.y() - self.height() - 2
        self.move(x, y)
        self._refresh_projects()
        self.show()
        self.raise_()
    
    def hide_panel(self):
        self.hide()
    
    def _refresh_projects(self):
        """刷新项目列表"""
        self.list_widget.clear()
        if not os.path.exists(self.projects_dir):
            return
        
        from core.project_manager import get_projects_list
        projects = get_projects_list(self.projects_dir)
        
        if not projects:
            item = QListWidgetItem("暂无项目")
            item.setForeground(QColor("#999"))
            self.list_widget.addItem(item)
            return
        
        for p in projects:
            name = p['name']
            file_count = p.get('file_count', 0)
            display_text = f"{name}  ({file_count} 个文件)"
            item = QListWidgetItem(display_text)
            item.setData(Qt.UserRole, p['file_path'])
            self.list_widget.addItem(item)
    
    def _on_item_double_clicked(self, item):
        """双击项目打开"""
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.project_selected.emit(file_path)
            self.hide_panel()
    
    def _on_new_project(self):
        """新建项目"""
        self.hide_panel()
        self.new_project_requested.emit()
    
    def focusOutEvent(self, event):
        """失去焦点时自动隐藏"""
        self.hide_panel()
        super().focusOutEvent(event)