"""
日志窗口 - 显示运行日志
SVG图标已集成
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QLabel,
    QTextEdit, QPushButton, QFileDialog,
    QMessageBox
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from gui.icon_manager import IconManager


class LogDialog(QDialog):
    """日志显示窗口"""
    
    def __init__(self, log_messages, parent=None):
        """
        :param log_messages: 日志消息列表，每个元素为字符串
        """
        super().__init__(parent)
        self.log_messages = log_messages
        
        # 初始化图标管理器
        self.icon_mgr = IconManager()
        
        # 移除窗口标题的 Emoji，交由系统渲染
        self.setWindowTitle("运行日志")
        self.setModal(False)
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        
        self._init_ui()
        self._load_logs()
    
    def _init_ui(self):
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # ===== 标题栏（组合图标 + 文字） =====
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        title_icon = QLabel()
        title_icon.setPixmap(self.icon_mgr.get_icon("list_log_title").pixmap(24, 24))
        title_text = QLabel(" 运行日志")
        title_text.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_text)
        title_layout.addStretch()
        layout.addWidget(title_widget)
        
        # 日志内容（只读）
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 9))
        self.text_edit.setLineWrapMode(QTextEdit.NoWrap)
        layout.addWidget(self.text_edit)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # ★ 清空日志按钮（带图标） ★
        self.btn_clear = QPushButton(self.icon_mgr.get_icon("trash_clear_button"), " 清空日志")
        self.btn_clear.clicked.connect(self._clear_logs)
        btn_layout.addWidget(self.btn_clear)
        
        # ★ 导出日志按钮（带图标） ★
        self.btn_export = QPushButton(self.icon_mgr.get_icon("list_log_button"), " 导出日志...")
        self.btn_export.clicked.connect(self._export_logs)
        btn_layout.addWidget(self.btn_export)
        
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
    
    def _load_logs(self):
        """加载日志消息到文本框"""
        if not self.log_messages:
            self.text_edit.setText("暂无日志记录。")
            return
        
        # 所有日志消息用换行分隔
        content = "\n".join(self.log_messages)
        self.text_edit.setText(content)
        
        # 自动滚动到底部（最新日志）
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.text_edit.setTextCursor(cursor)
    
    def append_log(self, message: str):
        """追加一条日志（用于实时更新）"""
        self.log_messages.append(message)
        self.text_edit.append(message)
        
        # 自动滚动到底部
        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.End)
        self.text_edit.setTextCursor(cursor)
    
    def _clear_logs(self):
        """清空日志"""
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有日志记录吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.log_messages.clear()
            self.text_edit.clear()
    
    def _export_logs(self):
        """导出日志到文件"""
        if not self.log_messages:
            QMessageBox.warning(self, "提示", "没有日志可以导出。")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "保存日志文件", "", "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not file_path:
            return
        
        # 确保扩展名为 .txt
        if not file_path.lower().endswith('.txt'):
            file_path += '.txt'
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(self.log_messages))
            QMessageBox.information(self, "导出成功", f"日志已导出到：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", f"导出日志时发生错误：\n{str(e)}")