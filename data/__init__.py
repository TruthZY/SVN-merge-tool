"""
data 数据层包
提供配置读写、SVN日志获取、合并操作、提交界面等抽象接口与实现。
"""
from .interfaces import IConfigProvider, ILogProvider, IMergeProvider, ICommitDialogProvider
from .merge_service import MergeService, MergeResult, MergeTask
from .svn_provider import SvnLogProvider, SvnMergeProvider, SvnCommitDialogProvider, SvnAvailability, get_svn_url

__all__ = [
    "IConfigProvider",
    "ILogProvider",
    "IMergeProvider",
    "ICommitDialogProvider",
    "MergeService",
    "MergeResult",
    "MergeTask",
    "SvnLogProvider",
    "SvnMergeProvider",
    "SvnCommitDialogProvider",
    "SvnAvailability",
    "get_svn_url",
]
