"""
重试对话框 - 显示转换失败的文件列表，支持重试和跳过
"""

import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QHeaderView,
    QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from core.converters import convert_to_pdf


class RetryDialog(QDialog):
    """重试对话框"""
    
    # 信号：重试完成时发射，参数为 (是否全部成功, 总结信息)
    retry_finished = pyqtSignal(bool, str)
    
    def __init__(self, failed_list, parent=None):
        """
        :param failed_list: 失败文件列表，格式为 [(file_path, error_msg), ...]
        """
        super().__init__(parent)
        self.failed_list = failed_list  # [(file_path, error_msg), ...]
        self.parent_window = parent
        self.retry_results = []  # [(file_path, success), ...]
        self.setWindowTitle("❌ 重试失败文件")
        self.setModal(True)
        self.setMinimumWidth(700)
        self.setMinimumHeight(400)
        
        self._init_ui()
        self._load_failed_list()
    
    def _init_ui(self):
        """构建界面"""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # 标题
        title = QLabel("以下文件转换失败，请选择操作：")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        layout.addWidget(title)
        
        # 文件列表表格
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["文件名", "错误信息", "状态"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.table)
        
        # 统计信息
        self.label_stats = QLabel()
        self.label_stats.setStyleSheet("color: #666;")
        layout.addWidget(self.label_stats)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.btn_retry_all = QPushButton("全部重试")
        self.btn_retry_all.clicked.connect(self._retry_all)
        btn_layout.addWidget(self.btn_retry_all)
        
        self.btn_retry_selected = QPushButton("重试选中")
        self.btn_retry_selected.clicked.connect(self._retry_selected)
        btn_layout.addWidget(self.btn_retry_selected)
        
        self.btn_skip_selected = QPushButton("跳过选中")
        self.btn_skip_selected.clicked.connect(self._skip_selected)
        btn_layout.addWidget(self.btn_skip_selected)
        
        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self._on_close)
        btn_layout.addWidget(self.btn_close)
        
        layout.addLayout(btn_layout)
        
        self._update_stats()
    
    def _load_failed_list(self):
        """加载失败文件列表到表格"""
        self.table.setRowCount(len(self.failed_list))
        for row, (file_path, error_msg) in enumerate(self.failed_list):
            # 文件名
            name_item = QTableWidgetItem(os.path.basename(file_path))
            name_item.setData(Qt.UserRole, file_path)
            self.table.setItem(row, 0, name_item)
            
            # 错误信息
            error_item = QTableWidgetItem(error_msg if error_msg else "未知错误")
            error_item.setForeground(Qt.red)
            self.table.setItem(row, 1, error_item)
            
            # 状态（初始为"待处理"）
            status_item = QTableWidgetItem("待处理")
            status_item.setForeground(Qt.darkGray)
            self.table.setItem(row, 2, status_item)
    
    def _update_stats(self):
        """更新统计信息"""
        total = len(self.failed_list)
        pending = 0
        success = 0
        failed = 0
        skipped = 0
        
        for row in range(self.table.rowCount()):
            status = self.table.item(row, 2).text()
            if status == "待处理":
                pending += 1
            elif status == "✅ 成功":
                success += 1
            elif status == "❌ 失败":
                failed += 1
            elif status == "⏭ 跳过":
                skipped += 1
        
        self.label_stats.setText(f"总计: {total} 个失败文件 | 待处理: {pending} | 成功: {success} | 失败: {failed} | 跳过: {skipped}")
        
        # 更新按钮状态
        has_pending = pending > 0
        has_selected = len(self.table.selectedIndexes()) > 0
        self.btn_retry_all.setEnabled(has_pending)
        self.btn_retry_selected.setEnabled(has_pending and has_selected)
        self.btn_skip_selected.setEnabled(has_pending and has_selected)
    
    def _get_selected_rows(self):
        """获取选中的行索引列表"""
        selected = set()
        for index in self.table.selectedIndexes():
            selected.add(index.row())
        return sorted(selected)
    
    def _get_pending_rows(self):
        """获取所有待处理的行索引"""
        pending = []
        for row in range(self.table.rowCount()):
            if self.table.item(row, 2).text() == "待处理":
                pending.append(row)
        return pending
    
    def _retry_file(self, row):
        """重试单个文件，返回 (success, error_msg)"""
        file_path = self.table.item(row, 0).data(Qt.UserRole)
        file_name = os.path.basename(file_path)
        
        # 更新状态为"正在重试..."
        self.table.item(row, 2).setText("⏳ 重试中...")
        self.table.item(row, 2).setForeground(Qt.blue)
        
        # 强制刷新
        QDialog.repaint(self)
        
        # 尝试转换
        try:
            # 生成输出路径（与原文件同目录，加 _retry.pdf 后缀）
            dir_name = os.path.dirname(file_path)
            base_name = os.path.splitext(file_name)[0]
            output_path = os.path.join(dir_name, f"{base_name}_retry.pdf")
            
            # 如果输出文件已存在，避免覆盖
            counter = 1
            while os.path.exists(output_path):
                output_path = os.path.join(dir_name, f"{base_name}_retry({counter}).pdf")
                counter += 1
            
            success = convert_to_pdf(file_path, output_path)
            
            if success:
                # 成功
                self.table.item(row, 2).setText("✅ 成功")
                self.table.item(row, 2).setForeground(Qt.green)
                self.retry_results.append((file_path, True))
                return True, None
            else:
                # 转换失败
                error_msg = "转换失败（未知原因）"
                self.table.item(row, 2).setText("❌ 失败")
                self.table.item(row, 2).setForeground(Qt.red)
                self.retry_results.append((file_path, False))
                return False, error_msg
                
        except Exception as e:
            error_msg = str(e)
            self.table.item(row, 2).setText("❌ 失败")
            self.table.item(row, 2).setForeground(Qt.red)
            self.retry_results.append((file_path, False))
            return False, error_msg
        
        finally:
            self._update_stats()
    
    def _retry_all(self):
        """重试所有待处理的文件"""
        pending_rows = self._get_pending_rows()
        if not pending_rows:
            return
        
        # 确认
        reply = QMessageBox.question(
            self, "确认重试",
            f"确定要重试 {len(pending_rows)} 个失败文件吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        # 禁用按钮，防止操作冲突
        self._set_buttons_enabled(False)
        
        success_count = 0
        fail_count = 0
        
        for row in pending_rows:
            success, error_msg = self._retry_file(row)
            if success:
                success_count += 1
            else:
                fail_count += 1
        
        # 恢复按钮
        self._set_buttons_enabled(True)
        
        # 更新父窗口的失败列表
        self._update_parent_failed_list()
        
        # 显示结果
        if fail_count == 0:
            QMessageBox.information(self, "重试完成", f"✅ 全部重试成功！共 {success_count} 个文件。")
            self.retry_finished.emit(True, f"重试全部成功，共 {success_count} 个文件。")
        elif success_count == 0:
            QMessageBox.warning(self, "重试失败", f"❌ 所有文件重试失败，共 {fail_count} 个文件。")
            self.retry_finished.emit(False, f"重试全部失败，共 {fail_count} 个文件。")
        else:
            QMessageBox.warning(self, "重试完成", f"⚠️ 部分成功：{success_count} 个成功，{fail_count} 个失败。")
            self.retry_finished.emit(False, f"重试完成：{success_count} 个成功，{fail_count} 个失败。")
    
    def _retry_selected(self):
        """重试选中的文件"""
        selected_rows = self._get_selected_rows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选中要重试的文件。")
            return
        
        # 过滤出待处理的行
        pending_rows = [r for r in selected_rows if self.table.item(r, 2).text() == "待处理"]
        if not pending_rows:
            QMessageBox.warning(self, "提示", "选中的文件都已处理。")
            return
        
        # 确认
        reply = QMessageBox.question(
            self, "确认重试",
            f"确定要重试 {len(pending_rows)} 个选中文件吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        self._set_buttons_enabled(False)
        
        success_count = 0
        fail_count = 0
        
        for row in pending_rows:
            success, error_msg = self._retry_file(row)
            if success:
                success_count += 1
            else:
                fail_count += 1
        
        self._set_buttons_enabled(True)
        self._update_parent_failed_list()
        
        # 显示结果
        if fail_count == 0:
            QMessageBox.information(self, "重试完成", f"✅ 全部重试成功！共 {success_count} 个文件。")
        elif success_count == 0:
            QMessageBox.warning(self, "重试失败", f"❌ 所有文件重试失败，共 {fail_count} 个文件。")
        else:
            QMessageBox.warning(self, "重试完成", f"⚠️ 部分成功：{success_count} 个成功，{fail_count} 个失败。")
    
    def _skip_selected(self):
        """跳过选中的文件"""
        selected_rows = self._get_selected_rows()
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选中要跳过的文件。")
            return
        
        pending_rows = [r for r in selected_rows if self.table.item(r, 2).text() == "待处理"]
        if not pending_rows:
            QMessageBox.warning(self, "提示", "选中的文件都已处理。")
            return
        
        # 确认
        reply = QMessageBox.question(
            self, "确认跳过",
            f"确定要跳过 {len(pending_rows)} 个文件吗？\n（跳过意味着这些文件将不参与后续合并）",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        
        for row in pending_rows:
            self.table.item(row, 2).setText("⏭ 跳过")
            self.table.item(row, 2).setForeground(Qt.gray)
            self.retry_results.append((self.table.item(row, 0).data(Qt.UserRole), False))
        
        self._update_stats()
        self._update_parent_failed_list()
    
    def _update_parent_failed_list(self):
        """更新父窗口的失败文件列表"""
        if self.parent_window and hasattr(self.parent_window, '_update_failed_list'):
            # 获取仍处于失败状态的文件
            remaining_failed = []
            for row in range(self.table.rowCount()):
                status = self.table.item(row, 2).text()
                if status == "❌ 失败" or status == "待处理":
                    file_path = self.table.item(row, 0).data(Qt.UserRole)
                    error_msg = self.table.item(row, 1).text()
                    remaining_failed.append((file_path, error_msg))
            
            if hasattr(self.parent_window, 'worker') and self.parent_window.worker:
                self.parent_window.worker.failed_list = remaining_failed
    
    def _set_buttons_enabled(self, enabled):
        """启用/禁用所有操作按钮"""
        self.btn_retry_all.setEnabled(enabled)
        self.btn_retry_selected.setEnabled(enabled)
        self.btn_skip_selected.setEnabled(enabled)
        self.btn_close.setEnabled(enabled)
    
    def _on_close(self):
        """关闭对话框"""
        # 检查是否还有待处理的文件
        pending = self._get_pending_rows()
        if pending:
            reply = QMessageBox.question(
                self, "确认关闭",
                f"还有 {len(pending)} 个文件未处理。\n确定要关闭吗？（未处理的文件将保持失败状态）",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
        
        self.accept()