"""
SVN客户端层 - 负责与SVN命令行交互
支持 Mock 模式（无SVN环境时模拟数据）
"""
import subprocess
import re
from datetime import datetime, timedelta
from typing import List, Optional
from models import SvnLogEntry

USE_MOCK = False  # 设为True可强制使用模拟数据调试GUI


def _run_svn(args: List[str], cwd: Optional[str] = None) -> str:
    """执行svn命令并返回输出"""
    cmd = ["svn"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        raise RuntimeError(f"SVN命令失败: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def is_svn_available() -> bool:
    """检查svn命令是否可用"""
    try:
        subprocess.run(["svn", "--version"], capture_output=True, check=True)
        return True
    except Exception:
        return False


def get_logs(url_or_path: str, limit: int = 10) -> List[SvnLogEntry]:
    """获取SVN提交日志"""
    if USE_MOCK or not is_svn_available():
        return _mock_logs(limit)

    # svn log --xml -l 10 <url>
    xml_output = _run_svn(["log", "--xml", "-l", str(limit), url_or_path])
    return _parse_log_xml(xml_output)


def merge_revision(source_url: str, target_path: str, revision: str) -> str:
    """
    将指定revision从source_url合并到target_path
    返回svn merge的输出信息
    """
    if USE_MOCK or not is_svn_available():
        return f"[MOCK] 合并 r{revision} 从 {source_url} 到 {target_path}"

    # svn merge -c <revision> <source_url> <target_path>
    output = _run_svn([
        "merge", "-c", revision,
        source_url, target_path
    ], cwd=target_path)
    return output


def get_working_copy_info(path: str) -> dict:
    """获取工作副本信息"""
    if USE_MOCK or not is_svn_available():
        return {"url": "mock://url", "revision": "1234"}

    info_xml = _run_svn(["info", "--xml", path])
    url_match = re.search(r'<url>(.*?)</url>', info_xml)
    rev_match = re.search(r'revision="(\d+)"', info_xml)
    return {
        "url": url_match.group(1) if url_match else "",
        "revision": rev_match.group(1) if rev_match else ""
    }


def open_commit_dialog(path: str):
    """
    打开SVN提交界面（TortoiseSVN或命令行）
    Windows下尝试使用TortoiseSVN，否则打印提示
    """
    import platform
    import os

    if USE_MOCK or not is_svn_available():
        print(f"[MOCK] 将打开提交界面: {path}")
        return

    system = platform.system()
    if system == "Windows":
        # 尝试TortoiseSVN
        try:
            subprocess.Popen(["TortoiseProc.exe", "/command:commit", f"/path:{os.path.abspath(path)}"])
            return
        except Exception:
            pass
    # 回退：提示用户手动提交
    print(f"请手动在 {path} 执行 svn commit")


# ---------- 内部解析方法 ----------

def _parse_log_xml(xml_text: str) -> List[SvnLogEntry]:
    """解析svn log --xml 输出"""
    entries = []
    logentry_pattern = re.compile(
        r'<logentry\s+revision="(\d+)">\s*'
        r'<author>(.*?)</author>\s*'
        r'<date>(.*?)</date>\s*'
        r'<msg>(.*?)</msg>\s*'
        r'</logentry>',
        re.DOTALL
    )
    for m in logentry_pattern.finditer(xml_text):
        entries.append(SvnLogEntry(
            revision=m.group(1),
            author=m.group(2).strip(),
            date=m.group(3).strip(),
            message=m.group(4).strip()
        ))
    return entries


def _mock_logs(limit: int) -> List[SvnLogEntry]:
    """生成模拟日志数据用于界面调试"""
    logs = []
    authors = ["张三", "李四", "王五", "developer_a", "developer_b"]
    messages = [
        "修复战斗系统崩溃bug",
        "新增活动105荣誉墙界面",
        "调整天赋树数值平衡",
        "优化资源加载性能",
        "合并主线修复到分支",
        "更新本地化文本",
        "修复UI显示异常",
        "增加新手引导流程",
        "调整副本难度系数",
        "修复网络同步问题"
    ]
    now = datetime.now()
    for i in range(limit):
        dt = now - timedelta(hours=i * 3)
        logs.append(SvnLogEntry(
            revision=str(1000 - i),
            author=authors[i % len(authors)],
            date=dt.strftime("%Y-%m-%d %H:%M"),
            message=messages[i % len(messages)]
        ))
    return logs
