"""
后台工作线程 - 执行批量转换和导出，不阻塞UI
v2.0.0 增强（适配真树结构）：
- 支持三种导出模式多选（依次执行）
- 支持导出范围过滤（全部/选中分组/选中文件）
- 支持输出格式选择（PDF/原格式）
- 支持PDF书签生成（模式③）
- 移除 replace_existing 功能（始终生成副本）
"""

import os
import shutil
import tempfile
import csv
from typing import List, Tuple, Dict, Optional
from datetime import datetime

from PyQt5.QtCore import QThread, pyqtSignal

from core.converters import convert_to_pdf
from core.models import ProjectData, GroupItem, FileItem


class ConvertWorker(QThread):
    """后台转换工作线程"""
    
    # 定义信号
    progress_updated = pyqtSignal(int, str)
    progress_detail = pyqtSignal(int, int, str, str, int, int, str)
    file_done = pyqtSignal(str, bool)
    error_occurred = pyqtSignal(str, str)
    finished_all = pyqtSignal(bool, str)
    log_message = pyqtSignal(str)
    mode_progress = pyqtSignal(int, int, str)
    
    def __init__(self, project_data: ProjectData, 
                 modes: List[int],
                 export_scope: str,
                 output_format: str,
                 generate_bookmark: bool,
                 output_path: str,
                 options: dict,
                 selected_groups: List[str] = None,
                 selected_files: List[str] = None):
        super().__init__()
        self.project_data = project_data
        self.modes = modes
        self.export_scope = export_scope
        self.output_format = output_format
        self.generate_bookmark = generate_bookmark
        self.output_path = output_path
        self.options = options
        self.selected_groups = selected_groups or []
        self.selected_files = selected_files or []
        
        # 临时目录
        self.temp_dir = None
        
        # 统计信息
        self.total_files = 0
        self.processed_files = 0
        self.success_files = 0
        self.failed_files = 0
        self.failed_list = []
        self.mode_results = []
        
        # 合并模式需要记录页码（用于书签）
        self.page_records = []
        self.current_page = 1
        self.group_page_map = {}
        
        # 取消标志
        self._is_cancelled = False
    
    def cancel(self):
        self._is_cancelled = True
        self.log_message.emit("⏹ 用户请求取消...")
    
    def is_cancelled(self) -> bool:
        return self._is_cancelled

    # ===== 适配真树结构：递归获取所有包含文件的节点 =====
    def _get_all_groups(self, node: GroupItem = None) -> List[GroupItem]:
        """递归遍历真树，返回所有节点（包括有文件和没文件的）"""
        if node is None:
            node = self.project_data.root
        
        groups = []
        for child in node.children:
            groups.append(child)
            # 递归子节点
            groups.extend(self._get_all_groups(child))
        return groups
    
    def _get_all_items(self):
        """递归获取所有 (节点, 文件) 的二元组列表"""
        all_items = []
        for group in self._get_all_groups():
            for file_item in group.files:
                all_items.append((group, file_item))
        return all_items
    
    def run(self):
        try:
            self.temp_dir = tempfile.mkdtemp(prefix="pdf_converter_")
            self.log_message.emit(f"创建临时目录: {self.temp_dir}")
            
            groups_to_process = self._filter_groups()
            if not groups_to_process:
                self.finished_all.emit(False, "没有匹配的分组或文件可导出。")
                return
            
            # 重新计算总文件数（递归）
            self.total_files = 0
            for g in groups_to_process:
                self.total_files += len(g.files)
            
            if self.total_files == 0:
                self.finished_all.emit(False, "没有找到任何文件，请先导入文件夹。")
                return
            
            self.log_message.emit(f"共找到 {self.total_files} 个文件")
            self.log_message.emit(f"选中的导出模式: {self.modes}")
            
            mode_names = {
                1: "① 导出到单文件夹",
                2: "② 按文件夹结构导出",
                3: "③ 合并为单个PDF"
            }
            
            total_modes = len(self.modes)
            all_success = True
            combined_summary = []
            
            for idx, mode in enumerate(self.modes):
                if self._is_cancelled:
                    self.log_message.emit("⏹ 用户取消，提前结束")
                    break
                
                self.mode_progress.emit(idx + 1, total_modes, mode_names.get(mode, f"模式{mode}"))
                self.log_message.emit(f"🔄 执行 {mode_names.get(mode, f'模式{mode}')} ({idx + 1}/{total_modes})")
                
                if mode == 1:
                    success, summary = self._process_mode1(groups_to_process)
                elif mode == 2:
                    success, summary = self._process_mode2(groups_to_process)
                elif mode == 3:
                    success, summary = self._process_mode3(groups_to_process)
                else:
                    self.log_message.emit(f"⚠️ 未知的模式: {mode}")
                    continue
                
                self.mode_results.append((mode, success, summary))
                if not success:
                    all_success = False
                combined_summary.append(f"  {mode_names.get(mode, f'模式{mode}')}: {summary}")
            
            if self._is_cancelled:
                self.finished_all.emit(False, f"已取消，已执行 {len(self.mode_results)}/{total_modes} 个模式")
            else:
                final_summary = f"共执行 {len(self.mode_results)} 个模式：\n" + "\n".join(combined_summary)
                self.finished_all.emit(all_success, final_summary)
            
        except Exception as e:
            self.log_message.emit(f"❌ 线程异常: {str(e)}")
            self.finished_all.emit(False, f"转换过程中发生异常: {str(e)}")
        finally:
            if self.temp_dir and os.path.exists(self.temp_dir):
                try:
                    shutil.rmtree(self.temp_dir)
                    self.log_message.emit("清理临时目录完成")
                except Exception as e:
                    self.log_message.emit(f"⚠️ 清理临时目录失败: {str(e)}")
    
    def _filter_groups(self):
        """过滤要导出的节点（适配真树结构）"""
        all_groups = self._get_all_groups()
        
        if self.export_scope == 'all':
            return all_groups
        elif self.export_scope == 'selected_groups':
            filtered = []
            for g in all_groups:
                if g.get_full_path() in self.selected_groups:
                    # ✅ 核心修复：递归收集该节点及其所有子孙节点
                    def collect_subtree(node):
                        filtered.append(node)
                        for child in node.children:
                            collect_subtree(child)
                    collect_subtree(g)
                    break  # 找到匹配后收集完毕，跳出循环
            return filtered
        elif self.export_scope == 'selected_files':
            filtered_groups = []
            for g in all_groups:
                filtered_files = [f for f in g.files if f.path in self.selected_files]
                if filtered_files:
                    new_group = GroupItem(g.name, code=g.code, notes=g.notes)
                    new_group.files = filtered_files
                    filtered_groups.append(new_group)
            return filtered_groups
        else:
            return all_groups
    
    def _should_convert_to_pdf(self) -> bool:
        return self.output_format == 'pdf'
    
    def _get_output_path_for_file(self, file_item: FileItem, base_dir: str, prefix: str = None) -> str:
        """生成输出路径（始终生成副本，不覆盖已有文件）"""
        base_name = os.path.splitext(file_item.name)[0]
        if prefix:
            safe_prefix = prefix.replace('/', '_').replace('\\', '_')
            if self._should_convert_to_pdf():
                output_name = f"{safe_prefix}_{base_name}.pdf"
            else:
                ext = os.path.splitext(file_item.name)[1]
                output_name = f"{safe_prefix}_{base_name}{ext}"
        else:
            if self._should_convert_to_pdf():
                output_name = f"{base_name}.pdf"
            else:
                output_name = file_item.name
        
        output_path = os.path.join(base_dir, output_name)
        
        # 始终生成副本，不覆盖已有文件
        if os.path.exists(output_path):
            counter = 1
            name, ext = os.path.splitext(output_name)
            while True:
                new_name = f"{name}({counter}){ext}"
                test_path = os.path.join(base_dir, new_name)
                if not os.path.exists(test_path):
                    output_path = test_path
                    break
                counter += 1
        
        return output_path
    
    # ---------- 模式① ----------
    def _process_mode1(self, groups):
        self.log_message.emit("🔄 模式①：导出到单文件夹")
        
        mode_output_dir = os.path.join(self.output_path, "单文件夹")
        os.makedirs(mode_output_dir, exist_ok=True)
        add_prefix = self.options.get("add_prefix", False)
        
        all_items = []
        for group in groups:
            for file_item in group.files:
                all_items.append((group, file_item))
        
        total = len(all_items)
        if total == 0:
            return True, "无文件可导出"
        
        self.progress_detail.emit(0, 0, "准备开始...", "", 0, total, "正在准备...")
        
        success_count = 0
        fail_count = 0
        
        for idx, (group, file_item) in enumerate(all_items):
            if self._is_cancelled:
                break
            
            self.progress_detail.emit(
                int(idx / total * 100) if total > 0 else 0,
                0, file_item.name, group.get_full_path(), idx + 1, total, "正在处理..."
            )
            
            try:
                output_path = self._get_output_path_for_file(
                    file_item, mode_output_dir, 
                    prefix=group.get_full_path() if add_prefix else None
                )
                
                if self._should_convert_to_pdf():
                    success = convert_to_pdf(file_item.path, output_path)
                else:
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    shutil.copy2(file_item.path, output_path)
                    success = True
                
                if success:
                    success_count += 1
                    self.file_done.emit(file_item.name, True)
                else:
                    fail_count += 1
                    error_msg = "处理失败"
                    self.failed_list.append((file_item.path, error_msg))
                    self.file_done.emit(file_item.name, False)
                    self.error_occurred.emit(file_item.path, error_msg)
            except Exception as e:
                fail_count += 1
                self.failed_list.append((file_item.path, str(e)))
                self.file_done.emit(file_item.name, False)
                self.error_occurred.emit(file_item.path, str(e))
            
            self.processed_files += 1
            progress = int((self.processed_files / self.total_files) * 100) if self.total_files > 0 else 0
            self.progress_updated.emit(progress, f"{self.processed_files}/{self.total_files}")
            self.progress_detail.emit(
                int((idx + 1) / total * 100) if total > 0 else 100,
                100, file_item.name, group.get_full_path(), idx + 1, total, "✅ 已完成"
            )
        
        summary = f"成功 {success_count} 个，失败 {fail_count} 个"
        return fail_count == 0, summary
    
    # ---------- 模式② ----------
    def _process_mode2(self, groups):
        self.log_message.emit("🔄 模式②：按文件夹结构导出")
        
        mode_output_dir = os.path.join(self.output_path, "保持结构")
        os.makedirs(mode_output_dir, exist_ok=True)
        
        all_items = []
        for group in groups:
            for file_item in group.files:
                all_items.append((group, file_item))
        
        total = len(all_items)
        if total == 0:
            return True, "无文件可导出"
        
        self.progress_detail.emit(0, 0, "准备开始...", "", 0, total, "正在准备...")
        
        success_count = 0
        fail_count = 0
        
        for idx, (group, file_item) in enumerate(all_items):
            if self._is_cancelled:
                break
            
            self.progress_detail.emit(
                int(idx / total * 100) if total > 0 else 0,
                0, file_item.name, group.get_full_path(), idx + 1, total, "正在处理..."
            )
            
            try:
                # 使用完整路径生成文件夹结构
                group_dir = os.path.join(mode_output_dir, group.get_full_path())
                os.makedirs(group_dir, exist_ok=True)
                
                output_path = self._get_output_path_for_file(file_item, group_dir, prefix=None)
                
                if self._should_convert_to_pdf():
                    success = convert_to_pdf(file_item.path, output_path)
                else:
                    shutil.copy2(file_item.path, output_path)
                    success = True
                
                if success:
                    success_count += 1
                    self.file_done.emit(file_item.name, True)
                else:
                    fail_count += 1
                    error_msg = "处理失败"
                    self.failed_list.append((file_item.path, error_msg))
                    self.file_done.emit(file_item.name, False)
                    self.error_occurred.emit(file_item.path, error_msg)
            except Exception as e:
                fail_count += 1
                self.failed_list.append((file_item.path, str(e)))
                self.file_done.emit(file_item.name, False)
                self.error_occurred.emit(file_item.path, str(e))
            
            self.processed_files += 1
            progress = int((self.processed_files / self.total_files) * 100) if self.total_files > 0 else 0
            self.progress_updated.emit(progress, f"{self.processed_files}/{self.total_files}")
            self.progress_detail.emit(
                int((idx + 1) / total * 100) if total > 0 else 100,
                100, file_item.name, group.get_full_path(), idx + 1, total, "✅ 已完成"
            )
        
        summary = f"成功 {success_count} 个，失败 {fail_count} 个"
        return fail_count == 0, summary
    
    # ---------- 模式③ ----------
    def _process_mode3(self, groups):
        self.log_message.emit("🔄 模式③：合并为单个PDF")
        
        all_items = []
        for group in groups:
            for file_item in group.files:
                all_items.append((group, file_item))
        
        total = len(all_items)
        if total == 0:
            return True, "无文件可合并"
        
        self.progress_detail.emit(0, 0, "准备开始...", "", 0, total, "正在准备转换...")
        
        converted_pdfs = []
        self.page_records = []
        self.current_page = 1
        self.group_page_map = {}
        
        # ---- 第一阶段：转换 ----
        success_count = 0
        fail_count = 0
        
        for idx, (group, file_item) in enumerate(all_items):
            if self._is_cancelled:
                break
            
            self.progress_detail.emit(
                int(idx / total * 100) if total > 0 else 0,
                0, file_item.name, group.get_full_path(), idx + 1, total, "正在转换..."
            )
            
            if group.get_full_path() not in self.group_page_map:
                self.group_page_map[group.get_full_path()] = self.current_page
            
            temp_pdf = self._convert_to_temp(file_item, group.get_full_path())
            if temp_pdf:
                converted_pdfs.append((group, file_item, temp_pdf))
                success_count += 1
            else:
                fail_count += 1
            
            self.progress_detail.emit(
                int((idx + 1) / total * 100) if total > 0 else 100,
                100, file_item.name, group.get_full_path(), idx + 1, total, "✅ 转换完成"
            )
        
        if self._is_cancelled:
            for _, _, temp_pdf in converted_pdfs:
                try:
                    if os.path.exists(temp_pdf):
                        os.remove(temp_pdf)
                except:
                    pass
            return False, "已取消"
        
        if not converted_pdfs:
            return False, "所有文件转换失败，无法合并"
        
        # ---- 第二阶段：合并 ----
        self.log_message.emit(f"📄 开始合并 {len(converted_pdfs)} 个文件...")
        
        try:
            import fitz
            merged_doc = fitz.open()
            
            merge_total = len(converted_pdfs)
            for merge_idx, (group, file_item, temp_pdf) in enumerate(converted_pdfs):
                if self._is_cancelled:
                    merged_doc.close()
                    for _, _, pdf in converted_pdfs:
                        try:
                            if os.path.exists(pdf):
                                os.remove(pdf)
                        except:
                            pass
                    return False, "已取消"
                
                merge_percent = int((merge_idx + 1) / merge_total * 100)
                self.progress_detail.emit(
                    100, merge_percent,
                    f"合并中: {file_item.name}", group.get_full_path(),
                    merge_idx + 1, merge_total,
                    f"正在合并... ({merge_idx + 1}/{merge_total})"
                )
                
                try:
                    doc = fitz.open(temp_pdf)
                except Exception as e:
                    error_msg = f"PDF打开失败: {str(e)}"
                    self.failed_list.append((file_item.path, error_msg))
                    self.log_message.emit(f"  ❌ 跳过加密/损坏PDF: {file_item.name} - {error_msg}")
                    try:
                        if os.path.exists(temp_pdf):
                            os.remove(temp_pdf)
                    except:
                        pass
                    continue
                
                page_count = len(doc)
                start_page = self.current_page
                end_page = self.current_page + page_count - 1
                self.page_records.append({
                    "group": group.get_full_path(),
                    "file_name": file_item.name,
                    "start_page": start_page,
                    "end_page": end_page,
                    "page_count": page_count
                })
                
                for page_num in range(page_count):
                    merged_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                
                self.current_page += page_count
                doc.close()
                self.log_message.emit(f"  ✅ 合并: {file_item.name} ({page_count}页)")
            
            # 生成书签
            if self.generate_bookmark and self.page_records:
                self.log_message.emit("📑 生成PDF书签...")
                toc = self._build_toc()
                merged_doc.set_toc(toc)
                self.log_message.emit(f"📑 书签生成完成，共 {len(toc)} 个条目")
            
            # 保存
            mode_output_dir = os.path.join(self.output_path, "合并PDF")
            os.makedirs(mode_output_dir, exist_ok=True)
            
            base_name = "合并底稿"
            output_pdf = os.path.join(mode_output_dir, f"{base_name}.pdf")
            
            # 始终生成副本，不覆盖
            if os.path.exists(output_pdf):
                counter = 1
                while True:
                    new_name = f"{base_name}({counter}).pdf"
                    test_path = os.path.join(mode_output_dir, new_name)
                    if not os.path.exists(test_path):
                        output_pdf = test_path
                        break
                    counter += 1
            
            merged_doc.save(output_pdf)
            merged_doc.close()
            self.log_message.emit(f"✅ 合并完成！输出: {output_pdf}")
            
            # 清理
            for _, _, temp_pdf in converted_pdfs:
                try:
                    if os.path.exists(temp_pdf):
                        os.remove(temp_pdf)
                except:
                    pass
            
            # 导出清单
            if self.options.get("export_manifest", True):
                self._export_manifest(mode_output_dir)
            
            summary = f"共 {len(converted_pdfs)} 个文件，{self.current_page - 1} 页"
            if self.failed_list:
                summary += f"，{len(self.failed_list)} 个文件被跳过"
            return len(self.failed_list) == 0, summary
            
        except ImportError:
            return False, "未安装 PyMuPDF (fitz)，请运行: pip install PyMuPDF"
        except Exception as e:
            self.log_message.emit(f"❌ 合并失败: {str(e)}")
            return False, f"合并失败: {str(e)}"
    
    def _build_toc(self):
        toc = []
        current_group = None
        
        for record in self.page_records:
            group_name = record["group"]
            file_name = record["file_name"]
            start_page = record["start_page"]
            
            if group_name != current_group:
                current_group = group_name
                toc.append([1, group_name, start_page])
            toc.append([2, f"  {file_name}", start_page])
        
        return toc
    
    def _export_manifest(self, output_dir):
        if not self.page_records:
            return
        try:
            manifest_path = os.path.join(output_dir, "合并清单.csv")
            with open(manifest_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["分组名", "文件名", "起始页码", "结束页码", "页数"])
                for record in self.page_records:
                    writer.writerow([
                        record["group"],
                        record["file_name"],
                        record["start_page"],
                        record["end_page"],
                        record["page_count"]
                    ])
            self.log_message.emit(f"📋 合并清单已导出: {manifest_path}")
        except Exception as e:
            self.log_message.emit(f"⚠️ 导出清单失败: {str(e)}")
    
    def _convert_to_temp(self, file_item: FileItem, group_name: str = "") -> Optional[str]:
        try:
            base_name = os.path.splitext(file_item.name)[0]
            temp_pdf = os.path.join(self.temp_dir, f"{base_name}_{id(file_item)}.pdf")
            
            self.log_message.emit(f"🔄 转换: {file_item.name} (分组: {group_name})")
            success = convert_to_pdf(file_item.path, temp_pdf)
            
            if success:
                self.success_files += 1
                self.file_done.emit(file_item.name, True)
                self.log_message.emit(f"  ✅ 转换成功")
                return temp_pdf
            else:
                self.failed_files += 1
                error_msg = "转换失败（未知原因）"
                self.failed_list.append((file_item.path, error_msg))
                self.file_done.emit(file_item.name, False)
                self.error_occurred.emit(file_item.path, error_msg)
                self.log_message.emit(f"  ❌ 转换失败")
                return None
                
        except Exception as e:
            self.failed_files += 1
            error_msg = str(e)
            self.failed_list.append((file_item.path, error_msg))
            self.file_done.emit(file_item.name, False)
            self.error_occurred.emit(file_item.path, error_msg)
            self.log_message.emit(f"  ❌ 异常: {str(e)}")
            return None
        
        finally:
            self.processed_files += 1
            progress = int((self.processed_files / self.total_files) * 100) if self.total_files > 0 else 0
            self.progress_updated.emit(progress, f"{self.processed_files}/{self.total_files}")