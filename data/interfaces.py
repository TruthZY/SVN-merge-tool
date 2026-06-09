"""
数据层接口定义 - 抽象所有与外部系统（SVN、文件系统）的交互边界
遵循依赖倒置原则：GUI/业务层依赖这些接口，而非具体实现
"""
from abc import ABC, abstractmethod
from typing import List, Optional
from models import AppConfig, SvnLogEntry


class IConfigProvider(ABC):
    """配置数据提供者"""

    @abstractmethod
    def list_configs(self) -> List[str]:
        """返回所有配置文件路径列表"""
        pass

    @abstractmethod
    def load_config(self, filepath: str) -> Optional[AppConfig]:
        """加载单个配置文件，失败返回None"""
        pass

    @abstractmethod
    def save_config(self, config: AppConfig, filepath: str) -> None:
        """保存配置到文件"""
        pass

    @abstractmethod
    def create_default_config(self) -> Optional[str]:
        """当没有配置时，创建一个默认配置并返回路径"""
        pass


class ILogProvider(ABC):
    """SVN日志数据提供者"""

    @abstractmethod
    def get_logs(self, url_or_path: str, limit: int = 10) -> List[SvnLogEntry]:
        """
        获取指定路径/URL的最近提交记录
        :param url_or_path: SVN URL 或本地工作副本路径
        :param limit: 最大返回条数
        :return: 提交记录列表，按时间倒序
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """当前提供者是否可用（例如svn命令是否存在）"""
        pass

    def get_eligible_revisions(self, source_url: str, target_path: str) -> set:
        """
        获取源URL对目标工作副本路径"尚未合并"的revision集合（基于 svn mergeinfo --show-revs eligible）。
        默认实现返回空集，表示该 Provider 不支持此能力。
        :param source_url: 源分支SVN URL
        :param target_path: 目标本地工作副本路径
        :return: 未合并的 revision 字符串集合（不含 'r' 前缀）
        """
        return set()


class IMergeProvider(ABC):
    """合并操作提供者"""

    @abstractmethod
    def merge_revision(self, source_url: str, target_path: str, revision: str) -> str:
        """
        将指定revision从source合并到target
        :param source_url: 源URL或路径
        :param target_path: 目标本地工作副本路径
        :param revision: revision号（不含r前缀）
        :return: 操作输出日志文本
        :raises RuntimeError: 合并失败时抛出
        """
        pass


class ICommitDialogProvider(ABC):
    """提交界面提供者"""

    @abstractmethod
    def open_commit_dialog(self, path: str, message: str = "") -> None:
        """
        打开指定路径的SVN提交界面
        :param path: 本地工作副本路径
        :param message: 预填充的提交信息
        """
        pass
