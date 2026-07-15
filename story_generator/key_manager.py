"""API Key 管理器 - 统一管理所有服务商的 API Key"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any


class KeyManager:
    """
    统一管理所有API Key的加载、验证、切换

    支持多种配置来源（优先级从高到低）：
    1. 环境变量
    2. .env 文件
    3. 配置文件 config.yaml
    4. 交互式输入
    """

    # 所有支持的服务商
    PROVIDERS = {
        "deepseek": {
            "env_var": "DEEPSEEK_API_KEY",
            "base_url": "https://api.deepseek.com",
            "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        },
        "agnes": {
            "env_var": "AGNES_API_KEY",
            "base_url": "https://apihub.agnes-ai.com/v1",
            "models": ["agnes-image-2.1-flash", "agnes-video-v2.0"],
        },
        "volcengine": {
            "env_var_access": "VOLCENGINE_ACCESS_KEY",
            "env_var_secret": "VOLCENGINE_SECRET_KEY",
        },
        "jina": {
            "env_var": "JINA_TOKEN",
        },
    }

    def __init__(self, config_dir: str = None):
        self.config_dir = Path(config_dir) if config_dir else Path(__file__).parent.parent
        self.keys: Dict[str, str] = {}
        self._load_keys()

    def _load_keys(self):
        """从 .env 文件和环境变量加载所有Key"""
        # 1. 先加载 .env 文件
        env_file = self.config_dir / ".env"
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        self.keys[key.strip()] = value.strip()

        # 2. 环境变量覆盖（优先级更高）
        for provider, config in self.PROVIDERS.items():
            env_var = config.get("env_var")
            if env_var and os.environ.get(env_var):
                self.keys[env_var] = os.environ[env_var]

            # volcengine 需要两个key
            access_key = config.get("env_var_access")
            secret_key = config.get("env_var_secret")
            if access_key and secret_key:
                if os.environ.get(access_key):
                    self.keys[access_key] = os.environ[access_key]
                if os.environ.get(secret_key):
                    self.keys[secret_key] = os.environ[secret_key]

    def get_key(self, provider: str, key_name: Optional[str] = None) -> Optional[str]:
        """获取指定服务商的API Key"""
        if provider == "deepseek":
            return self.keys.get("DEEPSEEK_API_KEY")
        elif provider == "agnes":
            return self.keys.get("AGNES_API_KEY")
        elif provider == "volcengine":
            return {
                "access_key": self.keys.get("VOLCENGINE_ACCESS_KEY"),
                "secret_key": self.keys.get("VOLCENGINE_SECRET_KEY"),
            }
        elif provider == "jina":
            return self.keys.get("JINA_TOKEN")
        return None

    def set_key(self, provider: str, key_value: str):
        """设置指定服务商的API Key（写入.env文件）"""
        env_mapping = {
            "deepseek": "DEEPSEEK_API_KEY",
            "agnes": "AGNES_API_KEY",
            "jina": "JINA_TOKEN",
        }
        env_var = env_mapping.get(provider)
        if not env_var:
            raise ValueError(f"不支持的服务商: {provider}")

        self.keys[env_var] = key_value

        # 写入.env文件
        env_file = self.config_dir / ".env"
        content = ""
        if env_file.exists():
            with open(env_file, "r", encoding="utf-8") as f:
                content = f.read()

        # 更新或追加
        lines = content.split("\n")
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f"{env_var}="):
                lines[i] = f"{env_var}={key_value}"
                updated = True
                break

        if not updated:
            lines.append(f"\n# {provider} API Key\n{env_var}={key_value}")

        with open(env_file, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        print(f"[KeyManager] {provider} API Key 已保存")

    def list_providers(self) -> Dict[str, bool]:
        """列出所有服务商及其Key状态"""
        status = {}
        for provider in self.PROVIDERS:
            key = self.get_key(provider)
            if isinstance(key, dict):
                has_all = all(key.values())
                status[provider] = has_all
            else:
                status[provider] = bool(key)
        return status

    def validate_keys(self) -> Dict[str, bool]:
        """验证所有Key是否有效"""
        results = {}
        for provider, config in self.PROVIDERS.items():
            key = self.get_key(provider)
            if isinstance(key, dict):
                results[provider] = all(key.values())
            else:
                results[provider] = bool(key)
        return results

    def add_custom_provider(self, name: str, env_var: str, base_url: str = ""):
        """添加自定义服务商"""
        self.PROVIDERS[name] = {
            "env_var": env_var,
            "base_url": base_url,
        }
