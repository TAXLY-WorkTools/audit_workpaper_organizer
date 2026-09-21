"""
进度窗口 - 7zip风格，显示总进度和当前文件进度
v2.0.0 增强：SVG图标集成
"""

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget,
    QProgressBar, QPushButton, QMessageBox
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont

from gui.icon_manager import IconManager


class ProgressWindow(QDialog):
    """进度窗口，显示总进度和当前文件进度"""
    
    # 取消信号
    cancel_requested = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("正在转换...")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.setFixedHeight(320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        
        # 初始化图标管理器
        self.icon_mgr = IconManager()
        
        self._init_ui()
        self._reset()
    
    def _init_ui(self):
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # ----- 标题栏（组合图标 + 文字） -----
        title_widget = QWidget()
        title_layout = QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        title_icon = QLabel()
        title_icon.setPixmap(self.icon_mgr.get_icon("hourglass_progress_title").pixmap(24, 24))
        title_text = QLabel(" 正在转换...")
        title_text.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        
        title_layout.addWidget(title_icon)
        title_layout.addWidget(title_text)
        title_layout.addStretch()
        layout.addWidget(title_widget)
        
        # ----- 模式进度 -----
        self.label_mode = QLabel("模式进度")
        self.label_mode.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self.label_mode)
        
        self.progress_mode = QProgressBar()
        self.progress_mode.setRange(0, 100)
        self.progress_mode.setValue(0)
        self.progress_mode.setTextVisible(True)
        self.progress_mode.setFormat("%p%")
        layout.addWidget(self.progress_mode)
        
        self.label_mode_text = QLabel("等待开始...")
        self.label_mode_text.setFont(QFont("Microsoft YaHei", 9))
        self.label_mode_text.setStyleSheet("color: #555;")
        layout.addWidget(self.label_mode_text)
        
        layout.addSpacing(5)
        
        # ----- 总进度 -----
        self.label_total = QLabel("总进度")
        self.label_total.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self.label_total)
        
        self.progress_total = QProgressBar()
        self.progress_total.setRange(0, 100)
        self.progress_total.setValue(0)
        self.progress_total.setTextVisible(True)
        self.progress_total.setFormat("%p%")
        layout.addWidget(self.progress_total)
        
        # 总进度文字
        self.label_total_text = QLabel("准备开始...")
        self.label_total_text.setFont(QFont("Microsoft YaHei", 9))
        self.label_total_text.setStyleSheet("color: #555;")
        layout.addWidget(self.label_total_text)
        
        layout.addSpacing(5)
        
        # ----- 当前文件进度 -----
        self.label_current = QLabel("当前文件")
        self.label_current.setFont(QFont("Microsoft YaHei", 9))
        layout.addWidget(self.label_current)
        
        self.progress_current = QProgressBar()
        self.progress_current.setRange(0, 100)
        self.progress_current.setValue(0)
        self.progress_current.setTextVisible(True)
        self.progress_current.setFormat("%p%")
        layout.addWidget(self.progress_current)
        
        # 当前文件信息
        self.label_file_name = QLabel("文件名: -")
        self.label_file_name.setFont(QFont("Microsoft YaHei", 9))
        self.label_file_name.setStyleSheet("color: #333;")
        layout.addWidget(self.label_file_name)
        
        self.label_group_name = QLabel("分组: -")
        self.label_group_name.setFont(QFont("Microsoft YaHei", 9))
        self.label_group_name.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(self.label_group_name)
        
        # ----- 底部按钮 -----
        layout.addStretch()
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        # 取消按钮（保持原样，无需加图标）
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedWidth(100)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        
        self._reset()
    
    def _reset(self):
        """重置所有进度显示"""
        self.progress_mode.setValue(0)
        self.label_mode_text.setText("等待开始...")
        self.progress_total.setValue(0)
        self.progress_current.setValue(0)
        self.label_total_text.setText("准备开始...")
        self.label_file_name.setText("文件名: -")
        self.label_group_name.setText("分组: -")
        self.btn_cancel.setEnabled(True)
        self.btn_cancel.setText("取消")
    
    # ===== 更新方法 =====
    def update_mode_progress(self, current: int, total: int, mode_name: str):
        """更新模式进度"""
        percent = int(current / total * 100) if total > 0 else 0
        self.progress_mode.setValue(percent)
        self.label_mode_text.setText(f"正在执行 {mode_name} ({current}/{total})")
        self.repaint()
    
    def update_progress(self, total_percent: int, current_percent: int,
                        file_name: str, group_name: str,
                        current_idx: int, total_files: int,
                        status_text: str = ""):
        """更新进度显示"""
        self.progress_total.setValue(total_percent)
        self.progress_current.setValue(current_percent)
        
        if status_text:
            self.label_total_text.setText(f"{status_text}  ({current_idx} / {total_files} 文件)")
        else:
            self.label_total_text.setText(f"{current_idx} / {total_files} 文件")
        
        self.label_file_name.setText(f"文件名: {file_name}")
        self.label_group_name.setText(f"分组: {group_name}")
        
        self.repaint()
    
    def update_merge_progress(self, total_percent: int, merged_count: int, total_files: int):
        """合并阶段专用更新"""
        self.progress_total.setValue(total_percent)
        self.progress_current.setValue(100)
        self.label_total_text.setText(f"正在合并... ({merged_count} / {total_files})")
        self.label_file_name.setText("文件名: 合并中...")
        self.label_group_name.setText("分组: -")
        self.repaint()
    
    def set_finished(self, all_success: bool, summary: str):
        """标记完成"""
        self.progress_current.setValue(100)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("已完成")
        
        if all_success:
            self.label_total_text.setText("✅ " + summary)
        else:
            self.label_total_text.setText("⚠️ " + summary)
        
        self.repaint()
    
    def set_cancelled(self):
        """标记为已取消"""
        self.progress_current.setValue(0)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText("已取消")
        self.label_total_text.setText("⏹ 已取消")
        self.repaint()
    
    def _on_cancel_clicked(self):
        """点击取消按钮"""
        reply = QMessageBox.question(
            self, "确认取消",
            "确定要取消当前转换任务吗？\n已转换的文件将被保留，未完成的将被跳过。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.btn_cancel.setEnabled(False)
            self.btn_cancel.setText("正在取消...")
            self.label_total_text.setText("⏹ 正在取消...")
            self.repaint()
            self.cancel_requested.emit()
    
    def closeEvent(self, event):
        """关闭窗口时阻止直接关闭"""
        if self.btn_cancel.isEnabled() and self.btn_cancel.text() != "已完成" and self.btn_cancel.text() != "已取消":
            reply = QMessageBox.question(
                self, "确认关闭",
                "转换任务正在进行中，关闭窗口将取消任务。\n确定要关闭吗？",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.cancel_requested.emit()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()