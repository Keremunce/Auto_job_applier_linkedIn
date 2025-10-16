import argparse
import os
import sys

from dotenv import load_dotenv

from modules.automation.browser_utils import BrowserController, BrowserSettings
from modules.automation.apply_linkedin import LinkedInApplier, LinkedInCredentials
from modules.ai.resume_rewriter import ResumeRewriter, ResumeRewriterConfig
from modules.logger import AutomationLogger
from modules.ui import UIController
from modules.validator import validate_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Automate LinkedIn job applications."
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run automation without GUI popups.",
    )
    return parser.parse_args()


def load_credentials() -> LinkedInCredentials:
    email = os.getenv("LINKEDIN_EMAIL") or ""
    password = os.getenv("LINKEDIN_PASSWORD") or ""
    if not email or not password:
        raise ValueError("LINKEDIN_EMAIL and LINKEDIN_PASSWORD must be set in .env")
    return LinkedInCredentials(email=email, password=password)


def build_resume_rewriter(logger: AutomationLogger) -> ResumeRewriter:
    api_key = os.getenv("OPENAI_API_KEY")
    api_base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    base_resume_path = os.path.join("config", "base_resume.md")
    config = ResumeRewriterConfig(
        base_resume_path=base_resume_path,
        model=model,
    )
    return ResumeRewriter(config, logger, api_key=api_key, api_base=api_base)


def main() -> None:
    load_dotenv()
    args = parse_args()
    logger = AutomationLogger()
    ui = UIController(headless=args.headless)

    validate_config()
    resume_rewriter = build_resume_rewriter(logger)
    credentials = load_credentials()

    browser_settings = BrowserSettings(
        disable_extensions=False,
        safe_mode=True,
        stealth_mode=os.getenv("CHROME_STEALTH_MODE", "false").lower() == "true",
        headless=args.headless,
    )
    browser = BrowserController(logger=logger, ui=ui, settings=browser_settings)

    applier = LinkedInApplier(
        browser=browser,
        credentials=credentials,
        logger=logger,
        ui=ui,
        resume_rewriter=resume_rewriter,
    )
    applier.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - top level guard
        logger = AutomationLogger()
        logger.log_exception("Automation failed", exc)
        sys.exit(1)
