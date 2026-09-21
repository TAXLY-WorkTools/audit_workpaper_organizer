"""
程序入口 - v2.0.0
"""

import sys
import os
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon
from PyQt5.QtCore import Qt

# 获取基础目录（兼容 PyInstaller 6.x _internal 结构）
def get_base_dir():
    if getattr(sys, 'frozen', False):
        # 打包成 exe 后：先找到 exe 所在目录
        base_path = os.path.dirname(sys.executable)
        # 判断是否存在 _internal 文件夹（PyInstaller 6.x 默认结构）
        internal_path = os.path.join(base_path, "_internal")
        if os.path.exists(internal_path):
            return internal_path
        return base_path
    else:
        # 开发模式：返回 main.py 所在的目录
        return os.path.dirname(os.path.abspath(__file__))

def main():
    # High DPI 设置必须在 QApplication 创建之前
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)

    # 设置窗口图标（打包后生效）
    icon_path = os.path.join(get_base_dir(), "app.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # ===== 加载样式表 =====
    styles_dir = os.path.join(get_base_dir(), "resources", "styles")
    style_file = os.path.join(styles_dir, "light_theme.qss")
    if os.path.exists(style_file):
        with open(style_file, 'r', encoding='utf-8') as f:
            app.setStyleSheet(f.read())
        print(f"✔ 已加载样式: {style_file}")
    else:
        print(f"✘ 样式文件不存在: {style_file}")

    # 项目目录：exe所在目录下的 Projects 文件夹
    base_dir = get_base_dir()
    projects_dir = os.path.join(base_dir, "Projects")
    os.makedirs(projects_dir, exist_ok=True)

    # 创建工作台
    from gui.project_workspace import ProjectWorkspace
    workspace = ProjectWorkspace(projects_dir)

    # 保存工作台引用到 app，便于全局访问
    app.workspace = workspace

    def open_editor(project_data, meta, project_file_path):
        """打开主窗口编辑器"""
        from gui.main_window import MainWindow
        window = MainWindow(
            project_data=project_data,
            meta=meta,
            project_file_path=project_file_path,
            workspace=workspace,
            projects_dir=projects_dir
        )
        # 保存到 app，防止被垃圾回收
        app.main_window = window
        # 连接关闭信号：主窗口关闭时，重新显示工作台
        window.closed.connect(lambda: show_workspace())
        window.show()
        # 隐藏工作台
        workspace.hide()

    def show_workspace():
        """显示工作台（主窗口关闭后调用）"""
        if not workspace.isVisible():
            workspace.show()
            workspace.raise_()
        # 刷新项目列表
        workspace._refresh_projects()

    # 连接信号
    workspace.project_opened.connect(open_editor)
    # 退出信号：完全退出程序
    workspace.exit_app.connect(lambda: app.quit())

    # 显示工作台
    workspace.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()