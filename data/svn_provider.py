"""
SVN命令行实现 - 基于 interfaces 的具体实现
封装所有 subprocess 调用，统一错误处理
"""
import subprocess
import sys
import platform
import os
import xml.etree.ElementTree as ET
from typing import List, Optional, Set

from data.interfaces import ILogProvider, IMergeProvider, ICommitDialogProvider
from models import SvnLogEntry


# Windows 下隐藏子进程控制台窗口（避免打包成 exe 后频繁弹黑窗）
# CREATE_NO_WINDOW = 0x08000000
if sys.platform == "win32":
    _NO_WINDOW_FLAGS = subprocess.CREATE_NO_WINDOW
else:
    _NO_WINDOW_FLAGS = 0


class SvnAvailability:
    """SVN环境可用性检查（单例缓存）"""
    _available: bool = False
    _checked: bool = False

    @classmethod
    def check(cls) -> bool:
        if cls._checked:
            return cls._available
        try:
            subprocess.run(
                ["svn", "--version"],
                capture_output=True,
                check=True,
                timeout=5,
                creationflags=_NO_WINDOW_FLAGS
            )
            cls._available = True
        except Exception:
            cls._available = False
        cls._checked = True
        return cls._available

    @classmethod
    def reset(cls):
        cls._checked = False


def get_svn_url(local_path: str) -> str:
    """
    通过 svn info 获取本地工作副本对应的远程URL
    失败时抛出 RuntimeError
    """
    xml_output = _run_svn(["info", "--xml", local_path], timeout=10)
    try:
        root = ET.fromstring(xml_output)
        url_elem = root.find(".//url")
        if url_elem is not None and url_elem.text:
            return url_elem.text.strip()
    except ET.ParseError:
        pass
    raise RuntimeError(f"无法从本地路径获取SVN URL: {local_path}")


def _run_svn(args: List[str], cwd: Optional[str] = None, timeout: int = 30) -> str:
    """执行svn命令并返回标准输出"""
    cmd = ["svn"] + args
    print(f"[SVN命令] 执行: {' '.join(cmd)} (cwd={cwd}, timeout={timeout})")
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,  # 防止svn等待输入导致永久阻塞
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd,
            timeout=timeout,
            creationflags=_NO_WINDOW_FLAGS
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"SVN命令超时 ({timeout}秒): {' '.join(cmd)}\n{e}")
    except Exception as e:
        raise RuntimeError(f"无法执行SVN命令: {' '.join(cmd)}\n{e}")

    if result.returncode != 0:
        err = result.stderr.strip() if result.stderr else "未知错误"
        raise RuntimeError(f"SVN命令失败 [exit={result.returncode}]: {' '.join(cmd)}\n{err}")

    # 防御性处理：确保返回字符串而非 None
    stdout = result.stdout
    if stdout is None:
        stdout = ""
    print(f"[SVN命令] 成功，输出长度 {len(stdout)}")
    return stdout


class SvnLogProvider(ILogProvider):
    """基于svn log命令的日志提供者"""

    def is_available(self) -> bool:
        return SvnAvailability.check()

    def get_logs(self, url_or_path: str, limit: int = 10) -> List[SvnLogEntry]:
        if not self.is_available():
            raise RuntimeError("SVN命令不可用，请检查环境变量")

        print(f"[SVN调试] 正在获取日志: {url_or_path} (limit={limit})")
        xml_output = _run_svn(["log", "--xml", "-v", "-l", str(limit), url_or_path])
        # 调试输出：把原始XML打印到控制台，方便诊断
        if not xml_output or not xml_output.strip():
            print(f"[SVN调试] svn log --xml 返回空输出，路径: {url_or_path}")
        else:
            print(f"[SVN调试] svn log --xml 输出长度: {len(xml_output)}")
        return self._parse_xml(xml_output)

    @staticmethod
    def _parse_xml(xml_text: str) -> List[SvnLogEntry]:
        """使用ElementTree解析svn log --xml输出"""
        entries = []

        # 防御性处理空输入
        if not xml_text or not xml_text.strip():
            print("[SVN调试] XML输入为空，返回空列表")
            return entries

        # SVN输出的XML可能没有声明，直接包在<log>根节点中
        # 但有些版本可能有多余的空格或BOM，先清理
        xml_text = xml_text.strip()
        if xml_text.startswith("\ufeff"):
            xml_text = xml_text[1:]

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            # 如果解析失败，尝试包裹在临时根节点中（处理可能的片段）
            print(f"[SVN调试] XML解析失败，尝试包裹根节点: {e}")
            try:
                wrapped = f"<root>{xml_text}</root>"
                root = ET.fromstring(wrapped)
            except ET.ParseError as e2:
                raise RuntimeError(f"无法解析SVN日志XML: {e2}\n原始输出前500字符:\n{xml_text[:500]}")

        # svn log --xml 的根节点是 <log>
        if root.tag == "log":
            logentries = root.findall("logentry")
        else:
            # 如果包裹了临时根节点，需要再往下找
            logentries = root.findall(".//logentry")

        for entry_elem in logentries:
            rev = entry_elem.get("revision", "")
            author = ""
            date = ""
            message = ""

            author_elem = entry_elem.find("author")
            if author_elem is not None and author_elem.text:
                author = author_elem.text.strip()

            date_elem = entry_elem.find("date")
            if date_elem is not None and date_elem.text:
                date = date_elem.text.strip()

            msg_elem = entry_elem.find("msg")
            if msg_elem is not None and msg_elem.text:
                message = msg_elem.text.strip()

            # 解析变更文件路径
            changed_paths = []
            paths_elem = entry_elem.find("paths")
            if paths_elem is not None:
                for path_elem in paths_elem.findall("path"):
                    action = path_elem.get("action", "?")
                    path_text = path_elem.text.strip() if path_elem.text else ""
                    if path_text:
                        changed_paths.append(f"{action} {path_text}")

            entries.append(SvnLogEntry(
                revision=rev,
                author=author or "unknown",
                date=date,
                message=message,
                changed_paths=changed_paths
            ))

        print(f"[SVN调试] 解析到 {len(entries)} 条提交记录")
        return entries

    def get_eligible_revisions(self, source_url: str, target_path: str) -> Set[str]:
        """
        调用 svn mergeinfo --show-revs eligible，返回该目标工作副本从source_url未合并的revision集合。
        输出示例：
            r1023
            r1027
            r1031
        失败时抛 RuntimeError。
        """
        if not self.is_available():
            raise RuntimeError("SVN命令不可用")
        if not source_url or not target_path:
            return set()

        print(f"[SVN调试] mergeinfo eligible: source={source_url}, target={target_path}")
        output = _run_svn(
            ["mergeinfo", "--show-revs", "eligible", source_url, target_path],
            timeout=60
        )
        revs: Set[str] = set()
        for line in output.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("r") or line.startswith("R"):
                line = line[1:]
            if line.isdigit():
                revs.add(line)
        print(f"[SVN调试] eligible 共 {len(revs)} 个 revision")
        return revs


class SvnMergeProvider(IMergeProvider):
    """基于svn merge命令的合并提供者"""

    def merge_revision(self, source_url: str, target_path: str, revision: str) -> str:
        if not SvnAvailability.check():
            raise RuntimeError("SVN命令不可用")

        print(f"[SvnMergeProvider] 开始合并: source={source_url}, target={target_path}, rev={revision}")

        # 先 update 目标工作副本到最新，避免基于旧版本合并产生冲突
        print(f"[SvnMergeProvider] 步骤1/2: svn update {target_path}")
        update_output = _run_svn(["update"], cwd=target_path, timeout=30)
        print(f"[SvnMergeProvider] update 完成")

        # 再执行 merge
        print(f"[SvnMergeProvider] 步骤2/2: svn merge -c {revision} {source_url}")
        merge_output = _run_svn(
            ["merge", "-c", revision, source_url],
            cwd=target_path,
            timeout=30
        )
        print(f"[SvnMergeProvider] merge 完成")

        return (
            f"=== svn update ===\n"
            f"{update_output.strip()}\n\n"
            f"=== svn merge -c {revision} ===\n"
            f"{merge_output.strip()}"
        )


class SvnCommitDialogProvider(ICommitDialogProvider):
    """尝试打开图形化SVN提交界面"""

    def open_commit_dialog(self, path: str, message: str = "") -> None:
        abs_path = os.path.abspath(path)
        system = platform.system()

        if system == "Windows":
            try:
                if message:
                    # TortoiseSVN /logmsg 参数需要用引号包裹整个值，防止空格/换行截断
                    escaped_msg = message.replace('"', '\\"')
                    cmd_str = f'TortoiseProc.exe /command:commit /path:"{abs_path}" /logmsg:"{escaped_msg}"'
                    subprocess.Popen(
                        cmd_str,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        shell=True,
                        creationflags=_NO_WINDOW_FLAGS  # shell=True 时隐藏 cmd 中转窗口
                    )
                else:
                    subprocess.Popen(
                        ["TortoiseProc.exe", "/command:commit", f"/path:{abs_path}"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=_NO_WINDOW_FLAGS
                    )
                return
            except Exception:
                pass

            try:
                subprocess.Popen(
                    ["svn", "commit", abs_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=_NO_WINDOW_FLAGS
                )
                return
            except Exception:
                pass

        elif system == "Darwin":
            try:
                subprocess.Popen(
                    ["svn", "commit", abs_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return
            except Exception:
                pass

        print(f"[提示] 请手动在 {abs_path} 执行 svn commit")
