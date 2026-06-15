import os
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict
import yaml
from loguru import logger

from app.config.settings import get_settings

settings = get_settings()


class HyperParams:
    def __init__(self, config: Dict[str, Any]):
        self._config = config

    def get(self, key: str, default: Any = None) -> Any:
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    @property
    def resampling(self) -> Dict[str, Any]:
        return self._config.get("resampling", {})

    @property
    def spectrum(self) -> Dict[str, Any]:
        return self._config.get("spectrum", {})

    @property
    def feature_extraction(self) -> Dict[str, Any]:
        return self._config.get("feature_extraction", {})

    @property
    def preprocessing(self) -> Dict[str, Any]:
        return self._config.get("preprocessing", {})

    @property
    def performance(self) -> Dict[str, Any]:
        return self._config.get("performance", {})

    @property
    def failure_preservation(self) -> Dict[str, Any]:
        return self._config.get("failure_preservation", {})


@lru_cache(maxsize=1)
def load_hyperparams() -> HyperParams:
    config_path = Path(settings.hyperparams_config_path)

    if not config_path.exists():
        project_root = Path(__file__).resolve().parent.parent.parent
        alt_path = project_root / "config" / "hyperparams.yaml"
        if alt_path.exists():
            config_path = alt_path
        else:
            logger.warning(f"超参数配置文件不存在: {config_path}, 将使用默认值")
            return HyperParams({})

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        logger.info(f"超参数配置加载成功: {config_path}")
        return HyperParams(config)
    except Exception as e:
        logger.error(f"超参数配置加载失败: {e}")
        return HyperParams({})
