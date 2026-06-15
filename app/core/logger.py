import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_dir: str, level: str = "INFO"):
    logger.remove()

    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    logger.add(
        sys.stdout,
        level=level,
        format=console_format,
        colorize=True,
        backtrace=True,
        diagnose=True
    )

    file_format = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <8} | "
        "{name}:{function}:{line} | "
        "{message}"
    )

    logger.add(
        log_path / "app_{time:YYYY-MM-DD}.log",
        level=level,
        format=file_format,
        rotation="00:00",
        retention="30 days",
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=True
    )

    logger.add(
        log_path / "error_{time:YYYY-MM-DD}.log",
        level="ERROR",
        format=file_format,
        rotation="00:00",
        retention="90 days",
        compression="zip",
        encoding="utf-8",
        backtrace=True,
        diagnose=True
    )

    return logger
