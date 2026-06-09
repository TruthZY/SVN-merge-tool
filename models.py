"""
数据模型层 - 定义配置、项目、提交记录等核心数据结构
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class Project:
    """SVN项目配置"""
    name: str
    local_path: str
    url: str = ""  # 可选，空时自动从 local_path 通过 svn info 获取


@dataclass
class MergeRule:
    """合并规则：从源项目合并到目标项目列表"""
    from_project: str
    to_projects: List[str]


@dataclass
class AppConfig:
    """应用配置（对应一个JSON配置文件）"""
    name: str                          # 配置显示名称
    projects: List[Project]            # 项目列表
    merge_rules: List[MergeRule]       # 合并规则
    log_limit: int = 10                # 日志条数限制
    commit_message_template: str = "Merge r{rev} from {source}: {msg}"
    config_show_name: str = "默认配置"  # 配置展示名
    svn_base_url: str = ""              # SVN基础URL前缀，用于生成提交信息中的相对路径

    def get_project_by_name(self, name: str) -> Optional[Project]:
        for p in self.projects:
            if p.name == name:
                return p
        return None

    def get_merge_targets(self, source_name: str) -> List[Project]:
        """根据源项目名称，获取需要合并到的目标项目列表"""
        targets = []
        for rule in self.merge_rules:
            if rule.from_project == source_name:
                for target_name in rule.to_projects:
                    proj = self.get_project_by_name(target_name)
                    if proj:
                        targets.append(proj)
        return targets


@dataclass
class SvnLogEntry:
    """SVN提交记录"""
    revision: str
    author: str
    date: str
    message: str
    changed_paths: List[str] = field(default_factory=list)  # 变更文件路径列表，如 ["M /trunk/Lua/xxx.lua"]
    # 合并状态：target_name -> True(已合并) / False(未合并) / None(未知或查询中)
    merge_status: Dict[str, Optional[bool]] = field(default_factory=dict)

    @property
    def display_text(self) -> str:
        msg = self.message.replace('\n', ' ').replace('\r', '')
        if len(msg) > 40:
            msg = msg[:37] + "..."
        return f"r{self.revision} | {self.author} | {self.date} | {msg}"

    def get_merge_status_text(self, target_names: List[str]) -> str:
        """
        基于 merge_status 生成后缀文本。设计原则：
          - 全部已合并：返回空（靠整行置灰提示，不拼接文字）
          - 全部未合并：返回空（默认待合并状态，无需额外提示）
          - 混合：仅列出已合并的目标，让用户一眼看出剩下哪些需要合并
          - 查询中：全部 None 时显示 [查询中…]
        """
        if not target_names:
            return ""
        statuses = [self.merge_status.get(n) for n in target_names]
        if all(s is None for s in statuses):
            return "  [查询中…]"
        if all(s is True for s in statuses):
            return ""
        if all(s is False for s in statuses):
            return ""
        # 混合：列出已合并的目标，未查询完的单独提示
        merged = [n for n, s in zip(target_names, statuses) if s is True]
        unknown = [n for n, s in zip(target_names, statuses) if s is None]
        parts = []
        if merged:
            parts.append("已合并: " + ",".join(merged))
        if unknown:
            parts.append("查询中: " + ",".join(unknown))
        return "  [" + " | ".join(parts) + "]" if parts else ""

    def is_fully_merged(self, target_names: List[str]) -> bool:
        """是否所有目标都已合并（任一未知或未合并都返回 False）。"""
        if not target_names:
            return False
        return all(self.merge_status.get(n) is True for n in target_names)
