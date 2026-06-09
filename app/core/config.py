from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent
load_dotenv(PROJECT_DIR / ".env")


def env_str(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


NOTION_TOKEN = env_str("NOTION_TOKEN") or env_str("NOTION_API_KEY")
NOTION_VERSION = env_str("NOTION_VERSION", "2022-06-28")
NOTION_ROOT_PAGE_ID = env_str("NOTION_ROOT_PAGE_ID", "1fa73fbd195180a59f39d3ae80362936")

SESSION_SECRET = env_str("SESSION_SECRET", "local-dev-secret-change-me")
TEMP_ID = env_str("TEMP_ID", "qa")
TEMP_PW = env_str("TEMP_PW", "qa")
AUTH_REQUIRED = env_bool("AUTH_REQUIRED", False)
STARTUP_SYNC_PRIORITY = env_bool("STARTUP_SYNC_PRIORITY", False)
STARTUP_SYNC_MAX_INDEX_AGE_HOURS = env_float("STARTUP_SYNC_MAX_INDEX_AGE_HOURS", 12.0)

QA_INDEX_PATH = Path(env_str("QA_INDEX_PATH", "data/qa_notion_index.json"))
if not QA_INDEX_PATH.is_absolute():
    QA_INDEX_PATH = PROJECT_DIR / QA_INDEX_PATH

QA_TOP_K = env_int("QA_TOP_K", 5)
NOTION_MAX_PAGES = env_int("NOTION_MAX_PAGES", 200)
NOTION_MAX_DEPTH = env_int("NOTION_MAX_DEPTH", 8)
NOTION_MAX_DATABASES = env_int("NOTION_MAX_DATABASES", 30)
QA_PRIORITY_RESULT_PAGE_ID = env_str("QA_PRIORITY_RESULT_PAGE_ID", "2a173fbd1951800089f0ebf677d48a5b")
QA_PRIORITY_PLAN_PAGE_ID = env_str("QA_PRIORITY_PLAN_PAGE_ID", "2a173fbd195180598125db0fd8558bde")
QA_PRIORITY_DEFECT_PAGE_ID = env_str("QA_PRIORITY_DEFECT_PAGE_ID", "21473fbd1951800d8321fc2e34c2548e")
QA_PRIORITY_WORKSPACE_DB_ID = env_str("QA_PRIORITY_WORKSPACE_DB_ID", "2a473fbd1951807d8d8bcfb4d8c3edc5")
QA_PRIORITY_MISC_DB_ID = env_str("QA_PRIORITY_MISC_DB_ID", "2a473fbd19518020bceac16cf319f4e8")
QA_PRIORITY_PROGRESS_DB_ID = env_str("QA_PRIORITY_PROGRESS_DB_ID", "2a773fbd19518018af97e393d017f526")
QA_ISSUE_MIN_TARGET_VERSION = env_str("QA_ISSUE_MIN_TARGET_VERSION", "5.18.0")
HANPASS_BUG_REPORT_DB_ID = env_str("HANPASS_BUG_REPORT_DB_ID", "36073fbd19518054b59ae4de5c74baeb")
VISIT_HOME_BUG_REPORT_DB_ID = env_str("VISIT_HOME_BUG_REPORT_DB_ID", "36073fbd19518003b5caebbdb84839fb")
SLACK_WEBHOOK_URL = env_str("SLACK_WEBHOOK_URL")
SLACK_CHANNEL_NAME = env_str("SLACK_CHANNEL_NAME", "slice_gh-test")
SLACK_NOTIFY_ENABLED = env_bool("SLACK_NOTIFY_ENABLED", True)
USE_GEMINI = env_bool("USE_GEMINI", True)
GEMINI_CLI_BIN = env_str("GEMINI_CLI_BIN", "gemini")
GEMINI_MODEL = env_str("GEMINI_MODEL")
