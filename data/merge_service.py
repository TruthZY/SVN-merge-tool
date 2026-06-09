"""
合并业务服务层 - 编排配置、日志、合并等操作，提供高层业务接口
GUI层直接调用此类，无需关心底层是SVN还是Mock
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Set

from models import AppConfig, Project, SvnLogEntry
from data.interfaces import ILogProvider, IMergeProvider, ICommitDialogProvider
from data.svn_provider import get_svn_url


@dataclass
class MergeTask:
    """单次合并任务描述"""
    source: Project
    target: Project
    revision: str
    commit_message: str = ""
    source_url: str = ""  # 合并时的源路径/URL，优先使用URL以确保能访问到目标revision


@dataclass
class MergeTargetResult:
    """单个目标项目的合并结果"""
    target: Project
    success: bool
    output: str = ""
    error: str = ""


@dataclass
class MergeResult:
    """整体合并结果"""
    tasks: List[MergeTask] = field(default_factory=list)
    results: List[MergeTargetResult] = field(default_factory=list)
    all_success: bool = False

    def get_success_targets(self) -> List[Project]:
        return [r.target for r in self.results if r.success]


class MergeService:
    """
    合并服务
    职责：
    1. 根据配置解析合并规则
    2. 加载提交日志
    3. 生成合并任务
    4. 执行批量合并
    5. 触发提交界面
    """

    def __init__(
        self,
        log_provider: ILogProvider,
        merge_provider: IMergeProvider,
        commit_provider: ICommitDialogProvider
    ):
        self.log_provider = log_provider
        self.merge_provider = merge_provider
        self.commit_provider = commit_provider

    # ---------- 内部工具 ----------

    def _resolve_url(self, project: Project) -> str:
        """获取项目的SVN URL，url为空时自动从long local_path 解析并缓存"""
        if project.url:
            return project.url
        # 通过 svn info 获取并缓存到 project 对象
        resolved = get_svn_url(project.local_path)
        project.url = resolved
        return resolved

    # ---------- 查询方法 ----------

    def get_source_projects(self, config: AppConfig) -> List[Project]:
        """获取配置中可作为合并源的项目列表"""
        result = []
        for p in config.projects:
            if config.get_merge_targets(p.name):
                result.append(p)
        return result

    def get_logs(self, config: AppConfig, project: Project, limit: Optional[int] = None) -> List[SvnLogEntry]:
        """
        获取指定项目的提交日志
        优先使用项目URL（直接查询仓库最新状态，不受本地工作副本是否update影响）
        URL为空时自动从本地路径解析
        :param limit: 可选覆盖 config.log_limit，用于“加载更多记录”场景
        """
        source = self._resolve_url(project)
        effective_limit = limit if (limit is not None and limit > 0) else config.log_limit
        return self.log_provider.get_logs(source, effective_limit)

    def get_merge_targets(self, config: AppConfig, source_name: str) -> List[Project]:
        """获取指定源项目需要合并到的目标项目"""
        return config.get_merge_targets(source_name)

    def get_merge_status_for_target(
        self,
        source_project: Project,
        target: Project,
        revisions: List[str]
    ) -> Dict[str, bool]:
        """
        查询一组 revision 在指定目标分支上的合并状态。
        返回 {revision: is_merged}，True表示已合并、False表示未合并。
        底层基于 svn mergeinfo --show-revs eligible 判断：
            在 eligible 集合中 → 未合并
            不在 eligible 集合中 → 已合并
        """
        if not revisions:
            return {}
        source_url = self._resolve_url(source_project)
        eligible: Set[str] = self.log_provider.get_eligible_revisions(
            source_url, target.local_path
        )
        return {rev: (rev not in eligible) for rev in revisions}

    # ---------- 任务构造 ----------

    def build_merge_tasks(
        self,
        config: AppConfig,
        source_project: Project,
        log_entry: SvnLogEntry
    ) -> List[MergeTask]:
        """
        根据选中的配置、源项目和提交记录，构造合并任务列表
        """
        targets = self.get_merge_targets(config, source_project.name)
        tasks = []
        source_url = self._resolve_url(source_project)
        source_identifier = source_url or source_project.name
        if config.svn_base_url and source_identifier.startswith(config.svn_base_url):
            source_identifier = source_identifier[len(config.svn_base_url):]

        msg = config.commit_message_template.format(
            rev=log_entry.revision,
            source=source_identifier,
            msg=log_entry.message.replace('\n', ' ').replace('\r', '')
        )
        for target in targets:
            tasks.append(MergeTask(
                source=source_project,
                target=target,
                revision=log_entry.revision,
                commit_message=msg,
                source_url=source_url
            ))
        return tasks

    # ---------- 执行方法 ----------

    def execute_merge(self, tasks: List[MergeTask]) -> MergeResult:
        """
        执行批量合并任务
        每个任务独立执行，失败不影响其他任务
        """
        result = MergeResult(tasks=tasks)

        for task in tasks:
            target_result = MergeTargetResult(target=task.target, success=False)
            try:
                # 优先使用 source_url（URL更可靠，不受本地update状态影响）
                merge_source = task.source_url if task.source_url else task.source.local_path
                output = self.merge_provider.merge_revision(
                    merge_source,
                    task.target.local_path,
                    task.revision
                )
                target_result.success = True
                target_result.output = output
            except Exception as e:
                target_result.success = False
                target_result.error = str(e)

            result.results.append(target_result)

        result.all_success = all(r.success for r in result.results)
        return result

    def open_commit_dialogs(self, targets: List[Project], commit_message: str = "") -> None:
        """为指定目标项目依次打开提交界面"""
        for target in targets:
            try:
                self.commit_provider.open_commit_dialog(target.local_path, commit_message)
            except Exception as e:
                print(f"[打开提交界面失败] {target.name}: {e}")

    # ---------- 便捷方法：一键合并 ----------

    def merge_single_revision(
        self,
        config: AppConfig,
        source_project: Project,
        log_entry: SvnLogEntry
    ) -> MergeResult:
        """
        一键合并：构造任务并立即执行
        """
        tasks = self.build_merge_tasks(config, source_project, log_entry)
        return self.execute_merge(tasks)

    # ---------- 进度回调扩展 ----------

    def execute_merge_with_callback(
        self,
        tasks: List[MergeTask],
        on_task_start: Optional[Callable[[MergeTask], None]] = None,
        on_task_complete: Optional[Callable[[MergeTargetResult], None]] = None
    ) -> MergeResult:
        """
        带进度回调的批量合并，适用于GUI实时刷新
        """
        print(f"[MergeService] execute_merge_with_callback 开始，共 {len(tasks)} 个任务")
        result = MergeResult(tasks=tasks)

        for idx, task in enumerate(tasks):
            print(f"[MergeService] 任务 {idx+1}/{len(tasks)}: {task.target.name}")
            if on_task_start:
                try:
                    on_task_start(task)
                    print(f"[MergeService] on_task_start 回调成功")
                except Exception as e:
                    print(f"[MergeService] on_task_start 回调异常: {e}")

            target_result = MergeTargetResult(target=task.target, success=False)
            try:
                merge_source = task.source_url if task.source_url else task.source.local_path
                print(f"[MergeService] 调用 merge_revision: source={merge_source}, target={task.target.local_path}, rev={task.revision}")
                output = self.merge_provider.merge_revision(
                    merge_source,
                    task.target.local_path,
                    task.revision
                )
                target_result.success = True
                target_result.output = output
                print(f"[MergeService] merge_revision 成功")
            except Exception as e:
                target_result.success = False
                target_result.error = str(e)
                print(f"[MergeService] merge_revision 失败: {e}")

            result.results.append(target_result)

            if on_task_complete:
                try:
                    on_task_complete(target_result)
                    print(f"[MergeService] on_task_complete 回调成功")
                except Exception as e:
                    print(f"[MergeService] on_task_complete 回调异常: {e}")

        result.all_success = all(r.success for r in result.results)
        print(f"[MergeService] 全部完成，all_success={result.all_success}")
        return result
