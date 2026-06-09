# SVN 分支合并工具

一款面向 Unity 多分支协同场景的轻量级 SVN 分支合并桌面工具。通过三步式向导（选配置 → 选提交 → 执行合并），将原本繁琐的 `svn merge -c` 操作可视化，并自动打开 TortoiseSVN 提交界面，显著降低 cherry-pick 出错概率。

## ✨ 功能特性

- **三步式 GUI 流程**：选择配置 → 选择源分支提交记录 → 执行规则化合并
- **多目标分支并行合并**：通过 `merge_rules` 一条规则可定义多个合并目标，一次选择自动推送到所有目标
- **已合并状态识别**：基于 `svn mergeinfo --show-eligible` 异步查询，已合并的提交记录自动置灰，避免重复合并
- **源项目日志缓存**：切换源时命中缓存即刻返回，点击“更多记录”可分页加载更多提交
- **配置驱动**：JSON 定义项目 URL/路径、合并规则、日志条数、提交信息模板
- **CLI 模式**：`merge_cli.py` 提供无 GUI 可编程接口，便于 AI / 脚本自动化调用
- **TortoiseSVN 集成**：合并完成后自动打开 TortoiseSVN 提交界面并预填提交信息
- **PyInstaller 打包**：`build.bat` 一键生成可分发的单文件 `.exe`

## 📁 项目结构

```
svn_merge_tool/
├── main.py                 # GUI 入口
├── merge_cli.py            # CLI 入口（AI / 脚本调用）
├── gui.py                  # tkinter 三状态界面
├── config_manager.py       # JSON 配置加载 / 列举 / 生成示例
├── models.py               # AppConfig / Project / SvnLogEntry 等数据模型
├── svn_client.py           # SVN 命令底层封装
├── build.bat               # PyInstaller 打包脚本
├── configs/                # 配置文件目录（首次运行自动生成示例）
│   └── config_dev.json
└── data/
    ├── interfaces.py       # IConfigProvider / ILogProvider / IMergeProvider 抽象
    ├── merge_service.py    # 业务编排层
    └── svn_provider.py     # 真实 SVN 命令实现
```

## 🚀 快速开始

### 环境要求

- Python 3.9+（需包含 `tkinter`，官方安装包默认包含）
- `svn` 命令行工具（已加入系统 PATH）。Windows 用户可安装 [TortoiseSVN](https://tortoisesvn.net/) 并勾选命令行工具选项

### 运行 GUI

```bash
python main.py
```

### 使用 CLI

编辑 `merge_cli.py` 中的 `main()` 参数后直接运行：

```bash
python merge_cli.py
```

核心 API：

```python
from merge_cli import MergeTarget, get_logs, do_merge

logs = get_logs("svn://server/repo/branches/feature", limit=20)
do_merge(
    source_url="svn://server/repo/branches/feature",
    targets=[MergeTarget(name="主干", local_path="E:/Project/trunk")],
    revision="12345",
    commit_message_template="合并了修改版本号{rev} 从 {source}:{msg}......",
    auto_open_commit=True,
    source_log_message="修复了某个bug",
)
```

## ⚙️ 配置文件

配置文件放置在 `configs/` 目录下，扩展名为 `.json`，启动时自动扫描。示例：

```json
{
  "projects": [
    { "name": "开发",     "local_path": "E:/UnityProject/Dev" },
    { "name": "发布",     "local_path": "E:/UnityProject/Release" },
    { "name": "发布外服", "local_path": "E:/UnityProject/Release_Out" }
  ],
  "merge_rules": [
    { "from": "开发", "to": ["发布", "发布外服"] }
  ],
  "log_limit": 30,
  "commit_message_template": "合并了修改版本号{rev} 从 {source}:{msg}......",
  "config_show_name": "代码合并路径",
  "svn_base_url": "http://xxx.com/xx"
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `projects` | 项目列表。`name` 用于显示，`local_path` 为本地工作副本路径。`url` 可选，为空时通过 `svn info --xml` 自动解析 |
| `merge_rules` | 合并规则。`from` 为源项目名称，`to` 为目标项目名称数组（可多目标） |
| `log_limit` | 首次加载的提交记录条数，可在界面点“更多记录”分页加载 |
| `commit_message_template` | 提交信息模板，支持 `{rev}`、`{source}`、`{msg}` 占位符 |
| `config_show_name` | 界面展示名 |
| `svn_base_url` | 可选，SVN 基础 URL |

### 多规则执行逻辑

- 多条规则 `from_project` 相同时，`to_projects` 合并，选该源时一次性推送到所有目标
- `from_project` 不同时，源项目下拉框会显示多个选项
- 一次合并严格为：**一个源项目 + 一个 revision → 该源对应的所有 target**（串行执行，失败隔离）
- 不支持链式传递（如 `G→M→M-Release` 需分两步手动执行）

## 📦 打包为可分发 exe

双击 `build.bat`（内部自动安装 PyInstaller），打包完成后产物位于：

```
dist/
├── SVN分支合并工具.exe
└── configs/
    └── (现有配置文件)
```

使用方式：将 `dist` 目录整体复制到目标机器，在 `dist/configs/` 中放置配置 JSON，双击 `SVN分支合并工具.exe` 即可。

> 打包时已通过 `--hidden-import` 注入 `data.*` 模块，并通过 `subprocess` 参数隐藏 SVN 子进程黑窗。

## 🛠 技术栈

- **语言**：Python 3
- **GUI**：tkinter（纯标准库，零额外 UI 依赖）
- **架构**：分层依赖注入
  - GUI 层：`gui.py`
  - 业务服务层：`data/merge_service.py`
  - 数据接口层：`data/interfaces.py`
  - 数据实现层：`data/svn_provider.py`、`config_manager.py`
- **打包**：PyInstaller
- **版本控制**：SVN（运行时依赖）

## 📝 开发说明

- 切换配置时会自动清空源项目日志缓存，防止不同配置下同名项目误复用
- “更多记录”按钮会在原文本后显示当前已加载条数
- 已合并提交行（即所有目标 `mergeinfo` 均显示 ineligible）会以灰色 `#A0A0A0` 渲染
- 合并过程中 GUI 不会阻塞，每个目标完成后实时回写日志

## 📄 License

本项目仅供学习与内部使用，未附加正式开源协议。如需二次分发请联系作者。
