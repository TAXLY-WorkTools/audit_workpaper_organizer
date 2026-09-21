"""
对话框模块 - 包含导出模式选择对话框
v2.0.0 增强：
- 导出模式多选（复选框）
- 导出范围选择（全部/选中的分组/选中的文件）
- 处理方式选择（转换为PDF / 保持原格式）
- PDF书签生成（模式③专属）
- 保持原格式时自动固定为"按文件夹结构导出"
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QCheckBox, QRadioButton, QPushButton, QLabel,
    QFileDialog, QMessageBox, QWidget
)
from PyQt5.QtCore import Qt

from gui.icon_manager import IconManager


class ExportModeDialog(QDialog):
    """导出模式选择对话框"""
    
    # 模式常量
    MODE_SINGLE_FOLDER = 1      # 模式①：全部转PDF导出到单文件夹
    MODE_KEEP_STRUCTURE = 2     # 模式②：按原文件夹结构导出
    MODE_MERGE_SINGLE = 3       # 模式③：全部合并为单个PDF
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出")
        self.setModal(True)
        self.setMinimumWidth(550)
        self.setMinimumHeight(400)
        
        # 初始化图标管理器
        self.icon_mgr = IconManager()
        
        # 初始化变量
        self.selected_modes = [self.MODE_MERGE_SINGLE]
        self.export_scope = 'all'
        self.output_format = 'pdf'      # 'pdf' | 'original'
        self.generate_bookmark = False
        self.output_path = ""
        self.selected_groups = []
        self.selected_files = []
        self.add_prefix = False
        
        self._init_ui()
        self._update_ui_state()
    
    def set_selected_info(self, selected_groups, selected_files):
        """接收主窗口传递的选中分组和文件信息"""
        self.selected_groups = selected_groups
        self.selected_files = selected_files
        self._update_scope_labels()
    
    def _init_ui(self):
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        
        # ---------- ① 导出范围 ----------
        group_scope = QGroupBox("① 导出范围")
        scope_layout = QVBoxLayout(group_scope)
        
        self.radio_all = QRadioButton("全部文件")
        self.radio_all.setChecked(True)
        self.radio_all.toggled.connect(self._on_scope_changed)
        scope_layout.addWidget(self.radio_all)
        
        self.radio_selected_groups = QRadioButton("选中的分组")
        self.radio_selected_groups.toggled.connect(self._on_scope_changed)
        scope_layout.addWidget(self.radio_selected_groups)
        
        self.radio_selected_files = QRadioButton("选中的文件")
        self.radio_selected_files.toggled.connect(self._on_scope_changed)
        scope_layout.addWidget(self.radio_selected_files)
        
        # ★ 修复：QLabel不能直接放QIcon，改用组合布局 ★
        self.label_scope_widget = QWidget()
        self.label_scope_layout = QHBoxLayout(self.label_scope_widget)
        self.label_scope_layout.setContentsMargins(20, 0, 0, 0)
        
        self.label_scope_icon = QLabel()
        self.label_scope_text = QLabel()
        self.label_scope_text.setStyleSheet("color: #666; font-style: italic;")
        
        self.label_scope_layout.addWidget(self.label_scope_icon)
        self.label_scope_layout.addWidget(self.label_scope_text)
        
        scope_layout.addWidget(self.label_scope_widget)
        
        layout.addWidget(group_scope)
        
        # ---------- ② 处理方式 ----------
        group_format = QGroupBox("② 处理方式")
        format_layout = QVBoxLayout(group_format)
        
        self.radio_pdf = QRadioButton("转换为PDF（统一格式，适合合并/归档）")
        self.radio_pdf.setChecked(True)
        self.radio_pdf.toggled.connect(self._on_format_changed)
        format_layout.addWidget(self.radio_pdf)
        
        self.radio_original = QRadioButton("保持原格式（直接复制，保持文件夹结构）")
        self.radio_original.toggled.connect(self._on_format_changed)
        format_layout.addWidget(self.radio_original)
        
        layout.addWidget(group_format)
        
        # ---------- ③ 输出结构（仅当选择"转换为PDF"时显示） ----------
        self.group_mode = QGroupBox("③ 输出结构")
        self.group_mode.setCheckable(False)
        mode_layout = QVBoxLayout(self.group_mode)
        
        # 模式①
        self.check_mode1 = QCheckBox("① 导出到单文件夹")
        self.check_mode1.toggled.connect(self._on_mode_toggled)
        mode_layout.addWidget(self.check_mode1)
        
        # 模式①的子选项
        self.check_add_prefix = QCheckBox("  添加分组名作为文件名前缀（避免重名）")
        self.check_add_prefix.setEnabled(False)
        mode_layout.addWidget(self.check_add_prefix)
        
        # 模式②
        self.check_mode2 = QCheckBox("② 按文件夹结构导出")
        self.check_mode2.toggled.connect(self._on_mode_toggled)
        mode_layout.addWidget(self.check_mode2)
        
        # 模式③
        self.check_mode3 = QCheckBox("③ 合并为单个PDF")
        self.check_mode3.toggled.connect(self._on_mode_toggled)
        mode_layout.addWidget(self.check_mode3)
        
        # 模式③的子选项
        self.check_bookmark = QCheckBox("  生成PDF书签（目录）")
        self.check_bookmark.setEnabled(False)
        mode_layout.addWidget(self.check_bookmark)
        
        # 模式计数标签
        self.label_mode_count = QLabel("已选 1 个模式")
        self.label_mode_count.setStyleSheet("color: #666;")
        mode_layout.addWidget(self.label_mode_count)
        
        # 默认选中模式③
        self.check_mode3.blockSignals(True)
        self.check_mode3.setChecked(True)
        self.check_mode3.blockSignals(False)
        self.check_bookmark.setChecked(True)
        
        layout.addWidget(self.group_mode)
        
        # ---------- ④ 输出位置 ----------
        path_layout = QHBoxLayout()
        path_layout.addWidget(QLabel("④ 输出位置:"))
        
        self.label_output = QLabel("未选择")
        self.label_output.setStyleSheet("border: 1px solid #ccc; padding: 4px; background: #f8f8f8;")
        self.label_output.setMinimumWidth(250)
        path_layout.addWidget(self.label_output, 1)
        
        self.btn_select_path = QPushButton("选择...")
        self.btn_select_path.clicked.connect(self._select_output_path)
        path_layout.addWidget(self.btn_select_path)
        
        layout.addLayout(path_layout)
        
        # ---------- 按钮区域 ----------
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_start = QPushButton("开始导出")
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._on_start)
        btn_layout.addWidget(self.btn_start)
        
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        layout.addLayout(btn_layout)
        
        self._update_ui_state()
    
    def _update_ui_state(self):
        """更新UI状态"""
        # 判断当前处理方式
        is_pdf = self.radio_pdf.isChecked()
        
        # 显示/隐藏输出结构区域
        self.group_mode.setVisible(is_pdf)
        
        # 更新模式计数（只统计可见的模式）
        count = 0
        if is_pdf:
            if self.check_mode1.isChecked():
                count += 1
            if self.check_mode2.isChecked():
                count += 1
            if self.check_mode3.isChecked():
                count += 1
        else:
            # 保持原格式：只有模式②有效（强制选中，不可取消）
            count = 1
        
        self.label_mode_count.setText(f"已选 {count} 个模式")
        
        # 模式①子选项：仅当模式①选中时启用
        self.check_add_prefix.setEnabled(self.check_mode1.isChecked() and is_pdf)
        
        # 模式③子选项：仅当模式③选中时启用
        self.check_bookmark.setEnabled(self.check_mode3.isChecked() and is_pdf)
        
        # 更新范围标签
        self._update_scope_labels()
        
        # 更新路径按钮文本
        self._update_path_hint()
    
    def _update_scope_labels(self):
        """更新导出范围的辅助信息（加入图标）"""
        # 先清空图标
        self.label_scope_icon.clear()
        
        if self.radio_all.isChecked():
            self.label_scope_text.setText("将导出所有分组和文件")
        elif self.radio_selected_groups.isChecked():
            if self.selected_groups:
                self.label_scope_text.setText(f"将导出选中的 {len(self.selected_groups)} 个分组")
            else:
                self.label_scope_icon.setPixmap(self.icon_mgr.get_icon("warning_export_dialog").pixmap(16, 16))
                self.label_scope_text.setText("未选中任何分组，请在左侧树中选中分组")
        elif self.radio_selected_files.isChecked():
            if self.selected_files:
                self.label_scope_text.setText(f"将导出选中的 {len(self.selected_files)} 个文件")
            else:
                self.label_scope_icon.setPixmap(self.icon_mgr.get_icon("warning_export_dialog").pixmap(16, 16))
                self.label_scope_text.setText("未选中任何文件，请在右侧表格中选中文件")
    
    def _update_path_hint(self):
        """根据当前模式调整路径选择提示"""
        is_pdf = self.radio_pdf.isChecked()
        if is_pdf and self.check_mode3.isChecked() and not self.check_mode1.isChecked() and not self.check_mode2.isChecked():
            self.btn_select_path.setText("选择PDF文件...")
        else:
            self.btn_select_path.setText("选择文件夹...")
    
    def _on_format_changed(self):
        """处理方式切换"""
        is_pdf = self.radio_pdf.isChecked()
        if not is_pdf:
            # 保持原格式：强制选中模式②，禁用其他模式
            self.check_mode1.blockSignals(True)
            self.check_mode1.setChecked(False)
            self.check_mode1.blockSignals(False)
            self.check_mode2.blockSignals(True)
            self.check_mode2.setChecked(True)
            self.check_mode2.blockSignals(False)
            self.check_mode3.blockSignals(True)
            self.check_mode3.setChecked(False)
            self.check_mode3.blockSignals(False)
            self.check_bookmark.setChecked(False)
        self._update_ui_state()
    
    def _on_mode_toggled(self):
        """模式切换时更新UI"""
        is_pdf = self.radio_pdf.isChecked()
        if not is_pdf:
            # 保持原格式：模式②强制选中，不可取消
            self.check_mode2.blockSignals(True)
            self.check_mode2.setChecked(True)
            self.check_mode2.blockSignals(False)
            self._update_ui_state()
            return
        
        # 确保至少选中一个模式
        if not self.check_mode1.isChecked() and not self.check_mode2.isChecked() and not self.check_mode3.isChecked():
            sender = self.sender()
            if sender == self.check_mode1:
                self.check_mode1.blockSignals(True)
                self.check_mode1.setChecked(True)
                self.check_mode1.blockSignals(False)
            elif sender == self.check_mode2:
                self.check_mode2.blockSignals(True)
                self.check_mode2.setChecked(True)
                self.check_mode2.blockSignals(False)
            elif sender == self.check_mode3:
                self.check_mode3.blockSignals(True)
                self.check_mode3.setChecked(True)
                self.check_mode3.blockSignals(False)
            else:
                self.check_mode3.setChecked(True)
            QMessageBox.warning(self, "提示", "请至少选择一种输出结构。")
            return
        
        self._update_ui_state()
    
    def _on_scope_changed(self):
        """导出范围切换"""
        if self.radio_all.isChecked():
            self.export_scope = 'all'
        elif self.radio_selected_groups.isChecked():
            self.export_scope = 'selected_groups'
        elif self.radio_selected_files.isChecked():
            self.export_scope = 'selected_files'
        self._update_scope_labels()
    
    def _select_output_path(self):
        """选择输出路径"""
        is_pdf = self.radio_pdf.isChecked()
        
        if is_pdf and self.check_mode3.isChecked() and not self.check_mode1.isChecked() and not self.check_mode2.isChecked():
            # 仅模式③选中：选择PDF文件
            file_path, _ = QFileDialog.getSaveFileName(
                self, "保存合并PDF文件", "",
                "PDF文件 (*.pdf);;所有文件 (*.*)"
            )
            if file_path:
                if not file_path.lower().endswith('.pdf'):
                    file_path += '.pdf'
                self.output_path = file_path
                self.label_output.setText(file_path)
        else:
            folder = QFileDialog.getExistingDirectory(
                self, "选择输出文件夹", "",
                QFileDialog.ShowDirsOnly
            )
            if folder:
                self.output_path = folder
                self.label_output.setText(folder)
    
    def _on_start(self):
        """点击开始导出"""
        if not self.output_path:
            QMessageBox.warning(self, "提示", "请先选择输出位置。")
            return
        
        is_pdf = self.radio_pdf.isChecked()
        modes = []
        
        if is_pdf:
            if self.check_mode1.isChecked():
                modes.append(self.MODE_SINGLE_FOLDER)
            if self.check_mode2.isChecked():
                modes.append(self.MODE_KEEP_STRUCTURE)
            if self.check_mode3.isChecked():
                modes.append(self.MODE_MERGE_SINGLE)
        else:
            # 保持原格式：固定为模式②
            modes.append(self.MODE_KEEP_STRUCTURE)
        
        if not modes:
            QMessageBox.warning(self, "提示", "请至少选择一种输出结构。")
            return
        
        if self.export_scope == 'selected_groups' and not self.selected_groups:
            QMessageBox.warning(self, "提示", "未选中任何分组，请先在左侧树中选中分组。")
            return
        if self.export_scope == 'selected_files' and not self.selected_files:
            QMessageBox.warning(self, "提示", "未选中任何文件，请先在右侧表格中选中文件。")
            return
        
        self.selected_modes = modes
        self.output_format = 'pdf' if is_pdf else 'original'
        self.generate_bookmark = self.check_bookmark.isChecked() and self.check_mode3.isChecked() and is_pdf
        self.add_prefix = self.check_add_prefix.isChecked() and self.check_mode1.isChecked() and is_pdf
        
        self.accept()
    
    def get_result(self):
        """返回用户选择结果"""
        return {
            'modes': self.selected_modes,
            'export_scope': self.export_scope,
            'output_format': self.output_format,
            'generate_bookmark': self.generate_bookmark,
            'output_path': self.output_path,
            'add_prefix': self.add_prefix
        }