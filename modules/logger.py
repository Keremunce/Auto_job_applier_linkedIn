import csv
import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Optional

LOG_BASE_DIR = os.path.join("outputs", "logs")
SUCCESS_LOG = "success.csv"
FAILURE_LOG = "failure.csv"
ERROR_LOG = "errors.log"


def _ensure_directories() -> None:
    os.makedirs(LOG_BASE_DIR, exist_ok=True)


def _configure_logging() -> logging.Logger:
    logger = logging.getLogger("linkedin_automation")
    if logger.handlers:
        return logger

    _ensure_directories()
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        os.path.join(LOG_BASE_DIR, ERROR_LOG), maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.WARNING)
    logger.addHandler(file_handler)

    return logger


class AutomationLogger:
    """
    Centralized logging helper that records structured CSV outputs alongside
    standard logging messages.
    """

    def __init__(self) -> None:
        _ensure_directories()
        self.logger = _configure_logging()
        self.success_path = os.path.join(LOG_BASE_DIR, SUCCESS_LOG)
        self.failure_path = os.path.join(LOG_BASE_DIR, FAILURE_LOG)

    @staticmethod
    def _write_row(path: str, row: list[str]) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        file_exists = os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            if not file_exists:
                writer.writerow(
                    [
                        "timestamp",
                        "job_title",
                        "company",
                        "job_url",
                        "applied",
                        "resume_path",
                        "error_message",
                    ]
                )
            writer.writerow(row)

    def log_success(
        self,
        job_title: str,
        company: str,
        job_url: str,
        resume_path: Optional[str],
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        self._write_row(
            self.success_path,
            [timestamp, job_title, company, job_url, True, resume_path or "", ""],
        )
        self.logger.info("Applied successfully | %s | %s", company, job_title)

    def log_failure(
        self,
        job_title: str,
        company: str,
        job_url: str,
        error_message: str,
        resume_path: Optional[str] = None,
    ) -> None:
        timestamp = datetime.utcnow().isoformat()
        self._write_row(
            self.failure_path,
            [
                timestamp,
                job_title,
                company,
                job_url,
                False,
                resume_path or "",
                error_message,
            ],
        )
        self.logger.warning(
            "Application failed | %s | %s | %s", company, job_title, error_message
        )

    def log_exception(self, message: str, exc: Exception) -> None:
        self.logger.exception("%s: %s", message, exc)
