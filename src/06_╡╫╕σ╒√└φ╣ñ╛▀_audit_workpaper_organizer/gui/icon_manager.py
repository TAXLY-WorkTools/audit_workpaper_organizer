"""
图标管理器模块 - 统一管理SVG图标的加载、颜色替换与映射
"""
import os
import sys
import re
from PyQt5.QtGui import QIcon, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import QByteArray, Qt, QSize


class IconManager:
    def __init__(self, base_dir=None):
        # 默认图标目录：项目根目录/resources/icons
        if base_dir is None:
            # ★ 关键修复：兼容 PyInstaller 6.x 新结构 (_internal)
            if getattr(sys, 'frozen', False):
                base_path = os.path.dirname(sys.executable)
                # 1. 先找 exe 旁边有没有 resources
                if os.path.exists(os.path.join(base_path, "resources")):
                    base_dir = os.path.join(base_path, "resources", "icons")
                else:
                    # 2. 没有的话，去 PyInstaller 6.x 默认的 _internal 里找
                    base_dir = os.path.join(base_path, "_internal", "resources", "icons")
            else:
                base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "icons")
        self.base_dir = base_dir
        
        # ★ 默认颜色（其余图标使用这个莫兰迪深绿） ★
        self.default_color = "#3D5C3D"
        
        # ★ 特殊颜色映射（您要求指定的颜色） ★
        self.color_map = {
            # 深绿 #375830
            "check_circle_status_success": "#375830",
            "check_circle_table_exists": "#375830",
            "check_circle_retry_success": "#375830",
            "plus_add_subgroup": "#375830",
            "plus_add_file": "#375830",
            
            # 深红 #54211d
            "times_circle_status_fail": "#54211d",
            "times_circle_table_missing": "#54211d",
            "times_circle_retry_title": "#54211d",
            "times_circle_retry_fail": "#54211d",
            "times_delete_group": "#54211d",
            "times_remove_file": "#54211d",
            "times_remove_dialog": "#54211d",
            "sign_out_exit": "#54211d",
            
            # 橙黄 #fdb933
            "warning_status": "#fdb933",
            "warning_export_dialog": "#fdb933",
            
            # 深蓝 #11264f
            "sync_refresh": "#11264f",
            "sort_button": "#11264f",
        }

    def get_icon(self, icon_name, size=24):
        """
        获取动态变色后的 QIcon（默认为24x24）
        """
        color = self.color_map.get(icon_name, self.default_color)
        return self._load_svg_icon(icon_name, color, size)

    def get_table_icon(self, icon_name, size=16):
        """
        获取表格中使用的更小尺寸的图标（如状态列），默认为16x16
        """
        color = self.color_map.get(icon_name, self.default_color)
        return self._load_svg_icon(icon_name, color, size)

    def _load_svg_icon(self, icon_name, color, size):
        filepath = os.path.join(self.base_dir, f"{icon_name}.svg")
        if not os.path.exists(filepath):
            print(f"❌ 找不到文件: {filepath}")
            return QIcon()
        
        with open(filepath, 'r', encoding='utf-8') as f:
            svg_str = f.read()
        
        # 智能替换所有常见的黑色/透明写法
        svg_str = svg_str.replace("#000000", color)
        svg_str = svg_str.replace("#000", color)
        svg_str = svg_str.replace("currentColor", color)
        svg_str = svg_str.replace("black", color)
        
        # 新增：替换 style="fill:#XXXXXX" 这种写法
        svg_str = re.sub(r'style="fill:#[0-9a-fA-F]{3,6}"', f'fill="{color}"', svg_str)
        
        renderer = QSvgRenderer(QByteArray(svg_str.encode('utf-8')))
        if renderer.isValid() is False:
            print(f"❌ 无法解析 SVG 文件: {filepath}")
            return QIcon()
        
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)