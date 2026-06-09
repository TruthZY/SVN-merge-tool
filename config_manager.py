"""
配置管理层 - 负责加载、保存、管理多个配置文件
同时提供 JsonConfigProvider 实现 IConfigProvider 接口
"""
import json
import os
from typing import List, Optional

from models import AppConfig, Project, MergeRule
from data.interfaces import IConfigProvider


def _get_app_dir() -> str:
    """获取应用程序所在目录（兼容PyInstaller打包后的exe环境）"""
    import sys
    if getattr(sys, 'frozen', False):
        # PyInstaller打包后，使用exe所在目录
        return os.path.dirname(sys.executable)
    else:
        # 开发环境，使用脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))


CONFIG_DIR = os.path.join(_get_app_dir(), "configs")


def ensure_config_dir():
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)


def load_config(filepath: str) -> Optional[AppConfig]:
    """从JSON文件加载配置"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        projects = [Project(
            name=p["name"],
            local_path=p["local_path"],
            url=p.get("url", "")
        ) for p in data.get("projects", [])]

        merge_rules = [MergeRule(
            from_project=r["from"],
            to_projects=r["to"]
        ) for r in data.get("merge_rules", [])]

        return AppConfig(
            name=os.path.splitext(os.path.basename(filepath))[0],
            projects=projects,
            merge_rules=merge_rules,
            log_limit=data.get("log_limit", 10),
            commit_message_template=data.get("commit_message_template", "Merge r{rev} from {source}: {msg}"),
            config_show_name=data.get("config_show_name", "未命名配置"),
            svn_base_url=data.get("svn_base_url", "")
        )
    except Exception as e:
        print(f"[ConfigManager] 加载配置失败 {filepath}: {e}")
        return None


def save_config(config: AppConfig, filepath: str):
    """保存配置到JSON文件"""
    data = {
        "projects": [
            {k: v for k, v in [("name", p.name), ("url", p.url), ("local_path", p.local_path)] if v}
            for p in config.projects
        ],
        "merge_rules": [
            {"from": r.from_project, "to": r.to_projects}
            for r in config.merge_rules
        ],
        "log_limit": config.log_limit,
        "commit_message_template": config.commit_message_template,
        "config_show_name": config.config_show_name,
        "svn_base_url": config.svn_base_url
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def list_configs() -> List[str]:
    """列出所有配置文件路径"""
    ensure_config_dir()
    files = []
    for f in os.listdir(CONFIG_DIR):
        if f.endswith('.json'):
            files.append(os.path.join(CONFIG_DIR, f))
    return sorted(files)


def create_demo_config():
    """创建示例配置文件。如果已存在则不再覆盖，避免误删用户配置。"""
    ensure_config_dir()
    path = os.path.join(CONFIG_DIR, "demo_config.json")

    # 若已存在则直接返回，绝不覆盖
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"[ConfigManager] demo_config.json 已存在，跳过创建: {path}")
        return path

    demo = {
        "projects": [
            {"name": "外服版", "url": "https://svn.example.com/repo/branches/waifu", "local_path": "D:/projects/waifu"},
            {"name": "内服版", "url": "https://svn.example.com/repo/branches/neifu", "local_path": "D:/projects/neifu"},
            {"name": "外服发布版", "url": "https://svn.example.com/repo/branches/waifu_release", "local_path": "D:/projects/waifu_release"},
            {"name": "内服发布版", "url": "https://svn.example.com/repo/branches/neifu_release", "local_path": "D:/projects/neifu_release"}
        ],
        "merge_rules": [
            {"from": "外服版", "to": ["内服版", "外服发布版"]},
            {"from": "内服版", "to": ["内服发布版"]}
        ],
        "log_limit": 10,
        "commit_message_template": "Merge r{rev} from {source}: {msg}",
        "config_show_name": "预制体合并路径"
    }
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(demo, f, ensure_ascii=False, indent=2)
    print(f"[ConfigManager] 已创建示例配置: {path}")
    return path


class JsonConfigProvider(IConfigProvider):
    """
    JSON配置文件提供者
    实现IConfigProvider接口，面向接口编程
    """

    def __init__(self, config_dir: Optional[str] = None):
        raw_dir = config_dir or CONFIG_DIR
        self.config_dir = os.path.abspath(raw_dir)

    def _ensure_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def list_configs(self) -> List[str]:
        self._ensure_dir()
        files = []
        for f in os.listdir(self.config_dir):
            if f.endswith('.json'):
                files.append(os.path.join(self.config_dir, f))
        return sorted(files)

    def load_config(self, filepath: str) -> Optional[AppConfig]:
        return load_config(filepath)

    def save_config(self, config: AppConfig, filepath: str) -> None:
        save_config(config, filepath)

    def create_default_config(self) -> Optional[str]:
        return create_demo_config()
