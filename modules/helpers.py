import json
import logging
import os
import re
from datetime import datetime, timedelta
from random import randint
from time import sleep
from typing import Any, Callable, Iterable

logger = logging.getLogger("linkedin_automation")


def make_directories(paths: Iterable[str]) -> None:
    for path in paths:
        expanded = os.path.expanduser(path)
        if "." in os.path.basename(expanded):
            expanded = os.path.dirname(expanded)
        if expanded:
            os.makedirs(expanded, exist_ok=True)


def find_default_profile_directory() -> str | None:
    candidates = [
        r"%LOCALAPPDATA%\Google\Chrome\User Data",
        r"%USERPROFILE%\AppData\Local\Google\Chrome\User Data",
        r"%USERPROFILE%\Local Settings\Application Data\Google\Chrome\User Data",
    ]
    for location in candidates:
        profile_dir = os.path.expandvars(location)
        if os.path.exists(profile_dir):
            return profile_dir
    return None


def print_lg(*messages: Any, level: str = "info") -> None:
    log = getattr(logger, level, logger.info)
    for message in messages:
        if isinstance(message, dict):
            log(json.dumps(message, default=str))
        else:
            log(str(message))


def critical_error_log(possible_reason: str, stack_trace: Exception) -> None:
    logger.exception("Critical error: %s", possible_reason, exc_info=stack_trace)


def buffer(speed: int = 0) -> None:
    if speed <= 0:
        return
    if speed <= 1:
        sleep(randint(6, 10) * 0.1)
    elif speed <= 2:
        sleep(randint(10, 18) * 0.1)
    else:
        sleep(randint(18, round(speed) * 10) * 0.1)


def manual_login_retry(is_logged_in: Callable[[], bool], limit: int = 2) -> None:
    attempts = 0
    while not is_logged_in() and attempts < limit:
        logger.info("Awaiting manual login confirmation (attempt %s)", attempts + 1)
        sleep(5)
        attempts += 1


def calculate_date_posted(time_string: str) -> datetime | None:
    time_string = time_string.strip()
    now = datetime.now()
    match = re.search(
        r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago",
        time_string,
        re.IGNORECASE,
    )
    if not match:
        return None
    value = int(match.group(1))
    unit = match.group(2).lower()

    if "second" in unit:
        return now - timedelta(seconds=value)
    if "minute" in unit:
        return now - timedelta(minutes=value)
    if "hour" in unit:
        return now - timedelta(hours=value)
    if "day" in unit:
        return now - timedelta(days=value)
    if "week" in unit:
        return now - timedelta(weeks=value)
    if "month" in unit:
        return now - timedelta(days=value * 30)
    if "year" in unit:
        return now - timedelta(days=value * 365)
    return None


def convert_to_lakhs(value: str) -> str:
    value = value.strip()
    digits = re.sub(r"\D", "", value)
    if not digits:
        return "0.00"
    if len(digits) > 5:
        return f"{digits[:-5]}.{digits[-5:-3]}"
    return f"0.{digits.zfill(5)[:2]}"


def convert_to_json(data: str) -> dict[str, Any]:
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return {"error": "Unable to parse the response as JSON", "data": data}


def truncate_for_csv(data: Any, max_length: int = 131000, suffix: str = "...[TRUNCATED]") -> str:
    stringified = str(data) if data is not None else ""
    if len(stringified) <= max_length:
        return stringified
    return stringified[: max_length - len(suffix)] + suffix


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return sanitized or "resume"


def read_text_file(path: str, encoding: str = "utf-8") -> str:
    if not os.path.exists(path):
        logger.warning("File not found: %s", path)
        return ""
    with open(path, "r", encoding=encoding) as file:
        return file.read()


def write_text_file(path: str, content: str, encoding: str = "utf-8") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding=encoding) as file:
        file.write(content)
