"""
GUI界面层 - 基于tkinter实现三状态流程界面
依赖注入：通过构造函数接收 ConfigProvider 和 Service工厂，完全不依赖具体实现
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import List, Optional

from models import AppConfig, Project, SvnLogEntry
from data.interfaces import IConfigProvider
from data.merge_service import MergeService, MergeResult, MergeTask, MergeTargetResult
from config_manager import load_config, list_configs, create_demo_config


class SvnMergeToolGUI:
    """SVN合并工具主界面"""

    def __init__(
        self,
        root: tk.Tk,
        config_provider: IConfigProvider,
        merge_service: MergeService
    ):
        self.root = root
        self.root.title("SVN分支合并工具")
        self.root.geometry("720x600")
        self.root.minsize(600, 480)

        # 注入的数据层依赖
        self.config_provider = config_provider
        self.merge_service = merge_service

        # 界面状态数据
        self.current_config: Optional[AppConfig] = None
        self.source_project: Optional[Project] = None
        self.selected_log: Optional[SvnLogEntry] = None
        self.log_entries: list[SvnLogEntry] = []

        # 异步合并状态查询的防抖 id：每次重新拉取 log 时 +1，
        # 后台线程回调时校验不一致则丢弃结果，避免给旧列表打错标记。
        self._merge_status_task_id: int = 0
        # 当前考察的目标名顺序，供 _format_log_display 使用
        self._current_target_names: List[str] = []
        # 源项目维度的日志缓存：key=_source_cache_key(project)，value=log_entries。
        # 缓存生命周期仅限本次运行，点“刷新日志”可强制失效重拉。
        self._source_cache: dict = {}
        # 源项目维度的 log_limit 覆盖值：点“更多记录”后记录当前加载过多少条
        self._source_limit_override: dict = {}

        self._build_ui()
        self._switch_state("CONFIG_SELECT")

    # ---------- UI框架 ----------

    def _build_ui(self):
        self.main_frame = ttk.Frame(self.root, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # 顶部信息栏
        top_frame = ttk.Frame(self.main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(
            top_frame, text="SVN分支合并工具", font=("Microsoft YaHei", 16, "bold")
        ).pack(side=tk.LEFT)

        # 状态指示器
        self.status_frame = ttk.Frame(self.main_frame)
        self.status_frame.pack(fill=tk.X, pady=(0, 8))
        self.status_labels = {}
        steps = [
            ("CONFIG_SELECT", "① 选择配置"),
            ("COMMIT_SELECT", "② 选择提交记录"),
            ("MERGE_RESULT", "③ 执行合并"),
        ]
        for i, (key, text) in enumerate(steps):
            lbl = ttk.Label(self.status_frame, text=text, font=("Microsoft YaHei", 10))
            lbl.pack(side=tk.LEFT, padx=(0 if i == 0 else 24, 0))
            self.status_labels[key] = lbl

        ttk.Separator(self.main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # 动态内容区
        self.content_frame = ttk.Frame(self.main_frame)
        self.content_frame.pack(fill=tk.BOTH, expand=True)

        # 底部按钮区
        self.btn_frame = ttk.Frame(self.main_frame)
        self.btn_frame.pack(fill=tk.X, pady=(10, 0))

    def _clear_content(self):
        for widget in self.content_frame.winfo_children():
            widget.destroy()
        for widget in self.btn_frame.winfo_children():
            widget.destroy()

    def _update_status_indicator(self, active_state: str):
        for key, lbl in self.status_labels.items():
            if key == active_state:
                lbl.configure(foreground="#0078D4", font=("Microsoft YaHei", 10, "bold"))
            else:
                lbl.configure(foreground="#666666", font=("Microsoft YaHei", 10))

    # ---------- 状态1: 选择配置 ----------

    def _show_config_select(self):
        frame = ttk.Frame(self.content_frame)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="请选择合并配置:", font=("Microsoft YaHei", 11)).pack(anchor=tk.W, pady=(0, 5))

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.config_listbox = tk.Listbox(list_frame, font=("Microsoft YaHei", 10), selectmode=tk.SINGLE)
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.config_listbox.yview)
        self.config_listbox.configure(yscrollcommand=scrollbar.set)
        self.config_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 加载配置（通过数据层接口）
        self.config_paths = self.config_provider.list_configs()
        self.config_map = {}
        self.config_errors = []  # 记录加载失败的文件及原因

        if not self.config_paths:
            default_path = self.config_provider.create_default_config()
            if default_path:
                self.config_paths = [default_path]

        for path in self.config_paths:
            try:
                cfg = self.config_provider.load_config(path)
                if cfg:
                    display = f"{cfg.config_show_name}  ({cfg.name})"
                    self.config_listbox.insert(tk.END, display)
                    self.config_map[display] = (path, cfg)
                else:
                    self.config_errors.append(os.path.basename(path))
            except Exception as e:
                self.config_errors.append(f"{os.path.basename(path)}: {e}")

        self.config_listbox.bind("<Double-Button-1>", lambda e: self._on_config_confirm())

        # 配置目录路径 + 状态信息
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=tk.X, pady=(8, 0))

        config_dir = getattr(self.config_provider, 'config_dir', '未知')
        dir_label = ttk.Label(info_frame, text=f"配置目录: {config_dir}", font=("Microsoft YaHei", 8), foreground="#666666")
        dir_label.pack(side=tk.LEFT)

        count_text = f"共扫描 {len(self.config_paths)} 个JSON文件"
        if self.config_errors:
            count_text += f"，{len(self.config_errors)} 个加载失败"
        count_label = ttk.Label(info_frame, text=count_text, font=("Microsoft YaHei", 8), foreground="#666666")
        count_label.pack(side=tk.RIGHT)

        # 配置详情预览
        self.config_detail = tk.Text(frame, height=6, wrap=tk.WORD, state=tk.DISABLED, bg="#f5f5f5")
        self.config_detail.pack(fill=tk.X, pady=(8, 0))
        self.config_listbox.bind("<<ListboxSelect>>", self._on_config_select_change)

        # 底部按钮
        ttk.Button(self.btn_frame, text="下一步", command=self._on_config_confirm).pack(side=tk.RIGHT)
        ttk.Button(self.btn_frame, text="刷新列表", command=lambda: self._switch_state("CONFIG_SELECT")).pack(side=tk.RIGHT, padx=(0, 10))
        ttk.Button(self.btn_frame, text="打开配置目录", command=self._open_config_dir).pack(side=tk.LEFT)

    def _on_config_select_change(self, event=None):
        selection = self.config_listbox.curselection()
        if not selection:
            return
        display = self.config_listbox.get(selection[0])
        path, cfg = self.config_map.get(display, (None, None))
        if not cfg:
            return

        detail = f"配置名称: {cfg.config_show_name}\n"
        detail += f"项目数量: {len(cfg.projects)}\n"
        detail += "项目列表:\n"
        for p in cfg.projects:
            detail += f"  - {p.name}: {p.local_path}\n"
        detail += "\n合并规则:\n"
        for r in cfg.merge_rules:
            detail += f"  - {r.from_project} -> {', '.join(r.to_projects)}\n"
        detail += f"\n日志限制: {cfg.log_limit} 条"

        self.config_detail.configure(state=tk.NORMAL)
        self.config_detail.delete("1.0", tk.END)
        self.config_detail.insert(tk.END, detail)
        self.config_detail.configure(state=tk.DISABLED)

    def _open_config_dir(self):
        """打开配置目录（Windows用explorer，其他用os.open）"""
        import platform
        import subprocess
        config_dir = getattr(self.config_provider, 'config_dir', '')
        if not config_dir or not os.path.exists(config_dir):
            messagebox.showwarning("提示", f"配置目录不存在: {config_dir}")
            return
        system = platform.system()
        try:
            if system == "Windows":
                subprocess.Popen(["explorer", config_dir])
            elif system == "Darwin":
                subprocess.Popen(["open", config_dir])
            else:
                subprocess.Popen(["xdg-open", config_dir])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开目录: {e}\n路径: {config_dir}")

    def _on_config_confirm(self):
        selection = self.config_listbox.curselection()
        if not selection:
            messagebox.showwarning("提示", "请先选择一个配置")
            return
        display = self.config_listbox.get(selection[0])
        path, cfg = self.config_map.get(display, (None, None))
        if cfg:
            # 切换配置时清空日志缓存，避免不同配置下同名项目误复用
            if self.current_config is not cfg:
                self._source_cache.clear()
                self._source_limit_override.clear()
            self.current_config = cfg
            self._switch_state("COMMIT_SELECT")

    # ---------- 状态2: 选择提交记录 ----------

    def _show_commit_select(self):
        frame = ttk.Frame(self.content_frame)
        frame.pack(fill=tk.BOTH, expand=True)

        # 源项目选择
        proj_frame = ttk.Frame(frame)
        proj_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(proj_frame, text="源项目:").pack(side=tk.LEFT)
        self.source_var = tk.StringVar()

        source_projects = self.merge_service.get_source_projects(self.current_config)
        source_names = [p.name for p in source_projects]
        if not source_names:
            messagebox.showerror("错误", "当前配置中没有有效的合并源项目")
            self._switch_state("CONFIG_SELECT")
            return

        self.source_combo = ttk.Combobox(
            proj_frame, textvariable=self.source_var,
            values=source_names, state="readonly", width=30
        )
        self.source_combo.pack(side=tk.LEFT, padx=(10, 0))
        self.source_combo.current(0)
        self.source_combo.bind("<<ComboboxSelected>>", self._on_source_change)

        # 目标项目显示
        self.targets_frame = ttk.LabelFrame(frame, text="将合并到以下目标", padding="5")
        self.targets_frame.pack(fill=tk.X, pady=(0, 10))
        self.targets_label = ttk.Label(self.targets_frame, text="", foreground="#0078D4", wraplength=600)
        self.targets_label.pack(anchor=tk.W)

        # 提交记录列表
        ttk.Label(frame, text="选择要合并的提交记录:").pack(anchor=tk.W, pady=(0, 5))
        log_frame = ttk.Frame(frame)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self.log_listbox = tk.Listbox(log_frame, font=("Consolas", 10), selectmode=tk.SINGLE)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_listbox.yview)
        self.log_listbox.configure(yscrollcommand=log_scroll.set)
        self.log_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 提交信息详情（可滚动，显示变更文件）
        self.log_detail = scrolledtext.ScrolledText(frame, height=8, wrap=tk.WORD, state=tk.DISABLED, bg="#f5f5f5")
        self.log_detail.pack(fill=tk.BOTH, pady=(10, 0))
        self.log_listbox.bind("<<ListboxSelect>>", self._on_log_select_change)

        # 底部按钮
        ttk.Button(self.btn_frame, text="上一步", command=lambda: self._switch_state("CONFIG_SELECT")).pack(side=tk.LEFT)
        ttk.Button(self.btn_frame, text="刷新日志", command=lambda: self._load_logs(force=True)).pack(side=tk.LEFT, padx=(10, 0))
        self.more_btn = ttk.Button(self.btn_frame, text="更多记录", command=self._load_more_logs)
        self.more_btn.pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(self.btn_frame, text="执行合并", command=self._on_merge_confirm).pack(side=tk.RIGHT)

        self._on_source_change()

    def _on_source_change(self, event=None):
        source_name = self.source_var.get()
        if not source_name or not self.current_config:
            return

        self.source_project = self.current_config.get_project_by_name(source_name)
        targets = self.merge_service.get_merge_targets(self.current_config, source_name)

        target_text = ", ".join([t.name for t in targets]) if targets else "无"
        self.targets_label.configure(text=target_text)

        self._load_logs()

    def _source_cache_key(self, project: Project) -> str:
        """生成源项目的缓存 key，避免不同配置或重名项目撞车。"""
        return f"{project.name}|{project.local_path}"

    def _get_effective_limit(self, project: Project) -> int:
        """返回当前 source 生效的 log limit（override > config.log_limit）"""
        cache_key = self._source_cache_key(project)
        if cache_key in self._source_limit_override:
            return self._source_limit_override[cache_key]
        return self.current_config.log_limit if self.current_config else 10

    def _load_more_logs(self):
        """在当前 limit 基础上加一档（默认 = config.log_limit），重拉日志。"""
        if not self.source_project or not self.current_config:
            return
        cache_key = self._source_cache_key(self.source_project)
        step = max(self.current_config.log_limit, 10)
        current = self._source_limit_override.get(cache_key, self.current_config.log_limit)
        self._source_limit_override[cache_key] = current + step
        self._load_logs(force=True)

    def _update_more_btn_text(self):
        """更新“更多记录”按钮文本，显示当前已加载条数。"""
        if not hasattr(self, "more_btn") or not self.source_project:
            return
        try:
            limit = self._get_effective_limit(self.source_project)
            self.more_btn.configure(text=f"更多记录 (已加载 {limit})")
        except tk.TclError:
            pass

    def _load_logs(self, force: bool = False):
        if not self.source_project or not self.current_config:
            return

        targets = self.merge_service.get_merge_targets(
            self.current_config, self.source_project.name
        )
        self._current_target_names = [t.name for t in targets]
        cache_key = self._source_cache_key(self.source_project)
        effective_limit = self._get_effective_limit(self.source_project)

        # 命中缓存且未强制刷新：直接复用上次的 log_entries（包含已查到的 merge_status）
        if not force and cache_key in self._source_cache:
            self.log_entries = self._source_cache[cache_key]
            # 取消可能仍在进行的后台查询，以入缓存为准
            self._merge_status_task_id += 1
            self._refresh_log_listbox()
            self._update_more_btn_text()
            return

        # 未命中或强制刷新：清空该 source 的缓存后重拉
        self._source_cache.pop(cache_key, None)

        self.log_listbox.delete(0, tk.END)
        self.log_entries = []

        try:
            self.log_entries = self.merge_service.get_logs(
                self.current_config, self.source_project, limit=effective_limit
            )
        except Exception as e:
            messagebox.showerror("获取日志失败", str(e))
            return

        # 初始化每条记录的合并状态为 None（查询中）
        for entry in self.log_entries:
            entry.merge_status = {t.name: None for t in targets}

        # 写入缓存（存的是同一个 list 引用，后续 mergeinfo 回调会就地更新其 merge_status）
        self._source_cache[cache_key] = self.log_entries

        # 先同步展示列表（后缀会是“查询中…”）
        for entry in self.log_entries:
            self.log_listbox.insert(tk.END, self._format_log_display(entry))

        self._update_more_btn_text()

        # 启动后台线程查询 mergeinfo eligible，不阻塞 UI
        self._merge_status_task_id += 1
        task_id = self._merge_status_task_id
        revisions = [e.revision for e in self.log_entries]
        source_project = self.source_project

        if not targets or not revisions:
            return

        def worker():
            for target in targets:
                # 每个目标独立查询，任一失败不影响其他目标
                try:
                    status = self.merge_service.get_merge_status_for_target(
                        source_project, target, revisions
                    )
                    err = None
                except Exception as e:
                    print(f"[mergeinfo] 查询失败 {target.name}: {e}")
                    status = {}
                    err = str(e)
                # 投递回主线程应用
                self.root.after(
                    0,
                    lambda t=target, s=status, e=err: self._apply_merge_status(task_id, t, s, e)
                )

        threading.Thread(target=worker, daemon=True).start()

    def _apply_merge_status(
        self,
        task_id: int,
        target: Project,
        status: dict,
        err: Optional[str]
    ):
        """主线程回调：应用某个目标分支的合并状态查询结果并刷新 listbox。"""
        if task_id != self._merge_status_task_id:
            # 用户已切换源项目/重新加载，旧结果丢弃
            return
        if err is not None:
            # 查询异常：将该目标下所有还是 None 的 entry 标为未知（保持 None），但可以考虑提示
            print(f"[GUI] 目标 {target.name} mergeinfo 查询失败：{err}")
            return
        for entry in self.log_entries:
            if entry.revision in status:
                entry.merge_status[target.name] = status[entry.revision]
        self._refresh_log_listbox()

    def _refresh_log_listbox(self):
        """全量刷新 listbox 内容，保留选中项与滚动位置。已合并行置灰。"""
        if not hasattr(self, "log_listbox"):
            return
        try:
            sel = self.log_listbox.curselection()
            yview = self.log_listbox.yview()
        except tk.TclError:
            return
        self.log_listbox.delete(0, tk.END)
        for entry in self.log_entries:
            self.log_listbox.insert(tk.END, self._format_log_display(entry))
        # 根据合并状态设置每行颜色：全部已合并 → 灰色，其余 → 默认色
        for idx, entry in enumerate(self.log_entries):
            try:
                if entry.is_fully_merged(self._current_target_names):
                    self.log_listbox.itemconfig(idx, foreground="#A0A0A0")
                else:
                    self.log_listbox.itemconfig(idx, foreground="#000000")
            except tk.TclError:
                pass
        for s in sel:
            try:
                self.log_listbox.selection_set(s)
            except tk.TclError:
                pass
        try:
            self.log_listbox.yview_moveto(yview[0])
        except tk.TclError:
            pass

    def _format_log_display(self, entry: SvnLogEntry) -> str:
        """在原始 display_text 后拼接合并状态后缀。"""
        suffix = entry.get_merge_status_text(self._current_target_names)
        return entry.display_text + suffix

    def _on_log_select_change(self, event=None):
        selection = self.log_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if 0 <= idx < len(self.log_entries):
            entry = self.log_entries[idx]
            self.selected_log = entry

            detail = f"Revision: r{entry.revision}\n"
            detail += f"Author: {entry.author}\n"
            detail += f"Date: {entry.date}\n"
            detail += f"Message:\n{entry.message}\n"

            if entry.changed_paths:
                detail += f"\n变更文件 ({len(entry.changed_paths)}):\n"
                for path in entry.changed_paths:
                    detail += f"  {path}\n"

            self.log_detail.configure(state=tk.NORMAL)
            self.log_detail.delete("1.0", tk.END)
            self.log_detail.insert(tk.END, detail)
            self.log_detail.configure(state=tk.DISABLED)

    def _on_merge_confirm(self):
        if not self.selected_log:
            messagebox.showwarning("提示", "请先选择一条提交记录")
            return
        self._switch_state("MERGE_RESULT")

    # ---------- 状态3: 合并结果 ----------

    def _show_merge_result(self):
        frame = ttk.Frame(self.content_frame)
        frame.pack(fill=tk.BOTH, expand=True)

        # 摘要信息
        targets = self.merge_service.get_merge_targets(self.current_config, self.source_project.name)
        summary = f"源项目: {self.source_project.name}\n"
        summary += f"提交记录: r{self.selected_log.revision}\n"
        summary += f"提交信息: {self.selected_log.message}\n"
        summary += f"目标项目: {', '.join([t.name for t in targets])}\n"

        ttk.Label(frame, text="合并摘要:", font=("Microsoft YaHei", 11, "bold")).pack(anchor=tk.W, pady=(0, 5))
        summary_text = tk.Text(frame, height=3, wrap=tk.WORD, state=tk.DISABLED, bg="#f5f5f5")
        summary_text.pack(fill=tk.X, pady=(0, 10))
        summary_text.configure(state=tk.NORMAL)
        summary_text.insert(tk.END, summary)
        summary_text.configure(state=tk.DISABLED)

        # 结果输出区
        ttk.Label(frame, text="合并日志:").pack(anchor=tk.W, pady=(0, 5))
        self.result_text = scrolledtext.ScrolledText(frame, wrap=tk.WORD, state=tk.DISABLED)
        self.result_text.pack(fill=tk.BOTH, expand=True)

        # 底部按钮（复选框移入按钮栏，避免被日志区挤出可视区域）
        ttk.Button(self.btn_frame, text="上一步", command=lambda: self._switch_state("COMMIT_SELECT")).pack(side=tk.LEFT)
        self.auto_commit_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.btn_frame, text="合并后自动打开SVN提交界面",
            variable=self.auto_commit_var
        ).pack(side=tk.LEFT, padx=(15, 0))
        self.merge_btn = ttk.Button(self.btn_frame, text="▶ 开始合并", command=self._execute_merge)
        self.merge_btn.pack(side=tk.RIGHT)

    def _execute_merge(self):
        if not self.current_config or not self.source_project or not self.selected_log:
            print("[GUI调试] _execute_merge 前置条件不满足，直接返回")
            return

        tasks = self.merge_service.build_merge_tasks(
            self.current_config, self.source_project, self.selected_log
        )
        print(f"[GUI调试] 构造了 {len(tasks)} 个合并任务")
        for i, t in enumerate(tasks):
            print(f"  任务{i+1}: r{t.revision} 从 {t.source.name}({t.source_url}) -> {t.target.name}({t.target.local_path})")

        if not tasks:
            messagebox.showwarning("提示", "没有可合并的目标项目")
            return

        self.merge_btn.configure(state=tk.DISABLED, text="合并中...")
        self.root.update_idletasks()

        self.result_text.configure(state=tk.NORMAL)
        self.result_text.delete("1.0", tk.END)
        self.result_text.insert(tk.END, f"=== 开始合并 r{self.selected_log.revision} ===\n")
        self.result_text.configure(state=tk.DISABLED)

        def on_start(task: MergeTask):
            print(f"[GUI调试] on_start: {task.target.name}")
            self.result_text.configure(state=tk.NORMAL)
            self.result_text.insert(tk.END, f"\n[{task.target.name}] {task.target.local_path}\n")
            self.result_text.configure(state=tk.DISABLED)
            self.result_text.see(tk.END)
            self.root.update_idletasks()

        def on_complete(res: MergeTargetResult):
            err_preview = ""
            if res.error:
                try:
                    err_preview = res.error[:100]
                except Exception:
                    err_preview = str(res.error)[:100]
            print(f"[GUI调试] on_complete: {res.target.name}, success={res.success}, error={err_preview}")
            self.result_text.configure(state=tk.NORMAL)
            if res.success:
                out = res.output if res.output else "(无输出)"
                self.result_text.insert(tk.END, out + "\n")
            else:
                err = res.error if res.error else "未知错误"
                self.result_text.insert(tk.END, f"[错误] {err}\n")
            self.result_text.configure(state=tk.DISABLED)
            self.result_text.see(tk.END)
            self.root.update_idletasks()

        try:
            result = self.merge_service.execute_merge_with_callback(tasks, on_start, on_complete)
            print(f"[GUI调试] execute_merge_with_callback 返回，all_success={result.all_success}")
        except Exception as e:
            print(f"[GUI调试] execute_merge_with_callback 抛出异常: {e}")
            import traceback
            traceback.print_exc()
            self.result_text.configure(state=tk.NORMAL)
            self.result_text.insert(tk.END, f"\n[严重错误] {e}\n")
            self.result_text.configure(state=tk.DISABLED)
            result = None

        self.result_text.configure(state=tk.NORMAL)
        if result:
            status = "全部成功" if result.all_success else "部分失败"
        else:
            status = "执行异常"
        self.result_text.insert(tk.END, f"\n=== 合并完成 ({status}) ===\n")
        self.result_text.configure(state=tk.DISABLED)

        self.merge_btn.configure(state=tk.NORMAL, text="开始合并")

        # 打开提交界面
        if result and self.auto_commit_var.get():
            success_targets = result.get_success_targets()
            if success_targets:
                self.result_text.configure(state=tk.NORMAL)
                for t in success_targets:
                    self.result_text.insert(tk.END, f"\n[打开提交界面] {t.name}")
                self.result_text.insert(tk.END, "\n")
                self.result_text.configure(state=tk.DISABLED)
                commit_message = result.tasks[0].commit_message if result.tasks else ""
                self.merge_service.open_commit_dialogs(success_targets, commit_message)

    # ---------- 状态机 ----------

    def _switch_state(self, state: str):
        """切换界面状态"""
        self._clear_content()
        self._update_status_indicator(state)

        if state == "CONFIG_SELECT":
            self._show_config_select()
        elif state == "COMMIT_SELECT":
            self._show_commit_select()
        elif state == "MERGE_RESULT":
            self._show_merge_result()
