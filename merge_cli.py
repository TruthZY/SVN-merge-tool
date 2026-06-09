"""
SVN合并CLI脚本 - 供AI直接调用，无需GUI
用法示例：
    python merge_cli.py

使用方式：修改下方 main() 中的参数即可执行合并
"""
import subprocess
import os
import xml.etree.ElementTree as ET
from typing import List, Optional
from dataclasses import dataclass


# ============== 数据结构 ==============

@dataclass
class MergeTarget:
    """合并目标"""
    name: str          # 目标名称（仅用于显示）
    local_path: str    # 目标本地工作副本路径


# ============== 核心SVN操作函数 ==============

def run_svn(args: List[str], cwd: Optional[str] = None, timeout: int = 60) -> str:
    """执行svn命令并返回输出"""
    cmd = ["svn"] + args
    print(f"[执行] {' '.join(cmd)}" + (f"  (cwd={cwd})" if cwd else ""))
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=cwd,
        timeout=timeout
    )
    if result.returncode != 0:
        err = result.stderr.strip() if result.stderr else "未知错误"
        raise RuntimeError(f"SVN命令失败 [exit={result.returncode}]: {' '.join(cmd)}\n{err}")
    return result.stdout or ""


def get_svn_url(local_path: str) -> str:
    """从本地工作副本路径获取远程SVN URL"""
    xml_output = run_svn(["info", "--xml", local_path], timeout=10)
    root = ET.fromstring(xml_output)
    url_elem = root.find(".//url")
    if url_elem is not None and url_elem.text:
        return url_elem.text.strip()
    raise RuntimeError(f"无法获取SVN URL: {local_path}")


def get_logs(url_or_path: str, limit: int = 20) -> list:
    """获取SVN提交日志，返回 [{revision, author, date, message, changed_paths}]"""
    xml_output = run_svn(["log", "--xml", "-v", "-l", str(limit), url_or_path])
    entries = []
    root = ET.fromstring(xml_output.strip())
    for entry_elem in root.findall(".//logentry"):
        rev = entry_elem.get("revision", "")
        author = (entry_elem.findtext("author") or "unknown").strip()
        date = (entry_elem.findtext("date") or "").strip()
        message = (entry_elem.findtext("msg") or "").strip()
        changed_paths = []
        paths_elem = entry_elem.find("paths")
        if paths_elem is not None:
            for p in paths_elem.findall("path"):
                action = p.get("action", "?")
                path_text = (p.text or "").strip()
                if path_text:
                    changed_paths.append(f"{action} {path_text}")
        entries.append({
            "revision": rev,
            "author": author,
            "date": date,
            "message": message,
            "changed_paths": changed_paths
        })
    return entries


def merge_revision(source_url: str, target_path: str, revision: str, update_first: bool = True) -> str:
    """
    核心合并函数：将source_url的指定revision合并到target_path
    
    参数:
        source_url:    源分支的SVN URL（或本地路径）
        target_path:   目标分支的本地工作副本路径
        revision:      要合并的版本号（纯数字，不含r前缀）
        update_first:  合并前是否先update目标（推荐True）
    
    返回: 合并输出日志
    """
    output_parts = []

    if update_first:
        print(f"\n[步骤1] svn update 目标: {target_path}")
        update_out = run_svn(["update"], cwd=target_path, timeout=60)
        output_parts.append(f"=== svn update ===\n{update_out.strip()}")

    print(f"\n[步骤2] svn merge -c {revision} {source_url}")
    merge_out = run_svn(["merge", "-c", revision, source_url], cwd=target_path, timeout=60)
    output_parts.append(f"=== svn merge -c {revision} ===\n{merge_out.strip()}")

    return "\n\n".join(output_parts)


def open_commit_dialog(target_path: str, message: str = "") -> None:
    """打开TortoiseSVN提交界面（Windows）"""
    abs_path = os.path.abspath(target_path)
    try:
        if message:
            escaped_msg = message.replace('"', '\\"')
            cmd_str = f'TortoiseProc.exe /command:commit /path:"{abs_path}" /logmsg:"{escaped_msg}"'
            subprocess.Popen(cmd_str, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=True)
        else:
            subprocess.Popen(
                ["TortoiseProc.exe", "/command:commit", f"/path:{abs_path}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        print(f"[提交] 已打开TortoiseSVN提交界面: {abs_path}")
    except Exception as e:
        print(f"[提示] 无法打开提交界面，请手动执行 svn commit: {abs_path}\n  错误: {e}")


# ============== 高层便捷函数 ==============

def do_merge(
    source_url: str,
    targets: List[MergeTarget],
    revision: str,
    commit_message_template: str = "Merge r{rev} from {source}: {msg}",
    auto_open_commit: bool = True,
    source_log_message: str = ""
):
    """
    执行一次完整的合并流程
    
    参数:
        source_url:               源分支SVN URL
        targets:                  目标列表 [MergeTarget(name, local_path), ...]
        revision:                 要合并的版本号（纯数字）
        commit_message_template:  提交信息模板，支持 {rev}, {source}, {msg} 占位符
        auto_open_commit:         合并成功后是否自动打开提交界面
        source_log_message:       源提交的原始消息（用于填充模板中的{msg}）
    """
    commit_msg = commit_message_template.format(
        rev=revision,
        source=source_url,
        msg=source_log_message.replace('\n', ' ').replace('\r', '')
    )

    print("=" * 60)
    print(f"合并计划:")
    print(f"  源: {source_url}")
    print(f"  版本号: r{revision}")
    print(f"  目标数量: {len(targets)}")
    for t in targets:
        print(f"    - {t.name}: {t.local_path}")
    print(f"  提交信息: {commit_msg}")
    print("=" * 60)

    success_targets = []
    for target in targets:
        print(f"\n{'─' * 40}")
        print(f"正在合并到: {target.name} ({target.local_path})")
        print(f"{'─' * 40}")
        try:
            output = merge_revision(source_url, target.local_path, revision)
            print(f"\n[成功] {target.name} 合并完成")
            print(output)
            success_targets.append(target)
        except Exception as e:
            print(f"\n[失败] {target.name} 合并失败: {e}")

    # 汇总
    print(f"\n{'=' * 60}")
    print(f"合并结果: {len(success_targets)}/{len(targets)} 成功")
    if success_targets and auto_open_commit:
        print(f"\n正在打开提交界面...")
        for t in success_targets:
            open_commit_dialog(t.local_path, commit_msg)


# ============== 使用示例 ==============

def main():
    """
    === AI调用说明 ===
    
    用法1: 直接合并指定版本号
        修改下面的参数直接运行即可
    
    用法2: 先查看日志再合并
        logs = get_logs("svn://your-svn-url/branch", limit=10)
        for log in logs:
            print(f"r{log['revision']} | {log['author']} | {log['message']}")
        # 选择要合并的版本号后调用 do_merge
    """
    
    # ===== 参数配置区（修改这里即可） =====
    
    # 源分支SVN URL（从哪里合并）
    source_url = "svn://your-server/repo/branches/feature-x"
    
    # 目标分支列表（合并到哪里，需要是本地checkout的路径）
    targets = [
        MergeTarget(name="主干", local_path="E:/Project/trunk"),
        # MergeTarget(name="release", local_path="E:/Project/release"),
    ]
    
    # 要合并的版本号（纯数字）
    revision = "12345"
    
    # 提交信息模板
    commit_template = "合并了修改版本号{rev} 从 {source}:{msg}......"
    
    # 源提交的原始信息（可选，用于填充模板）
    source_msg = "修复了某个bug"
    
    # ===== 执行 =====
    do_merge(
        source_url=source_url,
        targets=targets,
        revision=revision,
        commit_message_template=commit_template,
        auto_open_commit=True,
        source_log_message=source_msg
    )


if __name__ == "__main__":
    main()
