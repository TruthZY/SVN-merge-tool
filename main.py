"""
SVN分支合并工具 - 入口文件
职责：组装数据层依赖（ConfigProvider / MergeService）并注入GUI
"""
import tkinter as tk
from tkinter import messagebox

from config_manager import JsonConfigProvider
from data.svn_provider import SvnAvailability, SvnLogProvider, SvnMergeProvider, SvnCommitDialogProvider
from data.merge_service import MergeService
from gui import SvnMergeToolGUI


def create_service() -> MergeService:
    """
    工厂函数：创建并返回 MergeService
    """
    log_provider = SvnLogProvider()
    merge_provider = SvnMergeProvider()
    commit_provider = SvnCommitDialogProvider()
    return MergeService(log_provider, merge_provider, commit_provider)


def main():
    root = tk.Tk()

    # Windows高分辨率适配
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # 检测SVN环境
    if not SvnAvailability.check():
        messagebox.showerror(
            "SVN不可用",
            "未检测到svn命令行工具。\n"
            "请确保已安装SVN命令行工具并添加到系统PATH中。\n"
            "Windows用户可安装TortoiseSVN并勾选命令行工具选项。"
        )
        root.destroy()
        return

    # 组装依赖
    config_provider = JsonConfigProvider()
    merge_service = create_service()

    # 启动GUI
    app = SvnMergeToolGUI(root, config_provider, merge_service)

    root.mainloop()


if __name__ == "__main__":
    main()
