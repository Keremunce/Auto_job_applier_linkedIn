from __future__ import annotations

import json
import logging
import os
import signal
import time
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Sequence

import undetected_chromedriver as uc
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from modules.helpers import find_default_profile_directory, print_lg
from modules.logger import AutomationLogger
from modules.ui import UIController

COOKIE_DIR = os.path.join("outputs", "cookies")
COOKIE_FILE = os.path.join(COOKIE_DIR, "linkedin_cookies.json")
SHUTDOWN_SIGNALS = (signal.SIGINT, signal.SIGTERM)
ENABLE_SCREENSHOTS = True

logger = logging.getLogger(__name__)


def _ensure_cookie_dir() -> None:
    os.makedirs(COOKIE_DIR, exist_ok=True)


def save_cookies(driver: WebDriver, path: str = COOKIE_FILE) -> None:
    """
    Persist LinkedIn session cookies in JSON format with only Selenium-safe keys.
    """
    if not driver:
        return
    _ensure_cookie_dir()
    allowed_keys: Sequence[str] = (
        "name",
        "value",
        "domain",
        "path",
        "expiry",
        "httpOnly",
        "secure",
        "sameSite",
    )
    cleaned_cookies: list[dict] = []
    for cookie in driver.get_cookies():
        cleaned_cookie = {key: cookie[key] for key in allowed_keys if key in cookie}
        if cleaned_cookie:
            cleaned_cookies.append(cleaned_cookie)
    try:
        with open(path, "w", encoding="utf-8") as cookie_file:
            json.dump(cleaned_cookies, cookie_file, ensure_ascii=False, indent=2)
        logger.info("Saved %s cookies to %s", len(cleaned_cookies), path)
    except OSError as exc:  # pragma: no cover - disk write issues
        logger.warning("Failed to write cookies to %s: %s", path, exc)


def load_cookies(path: str = COOKIE_FILE) -> list[dict]:
    """
    Load cookies from disk, returning an empty list when nothing is stored.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as cookie_file:
            data = json.load(cookie_file)
        if isinstance(data, list):
            logger.info("Loaded %s cookies from %s", len(data), path)
            return data
        logger.warning("Cookie data in %s is not a list; ignoring contents.", path)
    except (OSError, json.JSONDecodeError) as exc:  # pragma: no cover - defensive guard
        logger.warning("Failed to load cookies from %s: %s", path, exc)
    return []


def apply_cookies(driver: WebDriver, cookies: Sequence[dict]) -> int:
    """
    Apply cookies to the current Selenium driver session.
    """
    if not driver or not cookies:
        return 0
    applied = 0
    for cookie in cookies:
        try:
            driver.add_cookie(cookie)
            applied += 1
        except Exception as exc:  # pragma: no cover - browser quirks
            logger.warning("Failed to apply cookie %s: %s", cookie.get("name"), exc)
    logger.info("Applied %s cookies to the browser session.", applied)
    return applied


def save_failed_login_screenshot(driver: Optional[WebDriver], path: Optional[str] = None) -> Optional[str]:
    """
    Capture a screenshot on login failure for debugging.
    """
    if not driver:
        return None
    if not ENABLE_SCREENSHOTS:
        logger.info("Screenshot skipped (disabled).")
        return None
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    logs_dir = os.path.join("outputs", "logs")
    os.makedirs(logs_dir, exist_ok=True)
    screenshot_path = path or os.path.join(logs_dir, f"failed_login_{timestamp}.png")
    try:
        driver.save_screenshot(screenshot_path)
        logger.warning("Saved failed login screenshot to %s", screenshot_path)
        return screenshot_path
    except WebDriverException as exc:  # pragma: no cover - driver quirks
        logger.warning("Failed to capture login screenshot: %s", exc)
        return None


@dataclass
class BrowserSettings:
    driver_wait_seconds: int = 10
    disable_extensions: bool = False
    safe_mode: bool = True
    stealth_mode: bool = False
    headless: bool = False


class BrowserController:
    """
    Encapsulates browser setup and login flow for LinkedIn.
    """

    def __init__(
        self,
        logger: AutomationLogger,
        ui: UIController,
        settings: BrowserSettings,
    ) -> None:
        self.logger = logger
        self.ui = ui
        self.settings = settings
        self.driver: Optional[WebDriver] = None
        self.wait: Optional[WebDriverWait] = None
        self.actions: Optional[ActionChains] = None

    def launch(
        self,
        headless: Optional[bool] = None,
        user_data_dir: Optional[str] = None,
    ) -> tuple[WebDriver, WebDriverWait]:
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        # Modern undetected_chromedriver compatibility
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-features=AutomationControlled")
        options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")

        effective_headless = self.settings.headless if headless is None else headless
        self.settings.headless = effective_headless

        if effective_headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            logger.info("Headless login bypass active.")
            print_lg("Headless login bypass active.")

        if self.settings.disable_extensions:
            options.add_argument("--disable-extensions")

        profile_argument = user_data_dir or None
        if profile_argument:
            options.add_argument(f"--user-data-dir={profile_argument}")
            logger.info("Using provided Chrome profile directory: %s", profile_argument)
            print_lg(f"Using provided Chrome profile directory: {profile_argument}")
        elif self.settings.safe_mode:
            print_lg("Launching Chrome in guest (safe) mode.")
        else:
            profile_dir = find_default_profile_directory()
            if profile_dir:
                options.add_argument(f"--user-data-dir={profile_dir}")
                print_lg(f"Using Chrome profile directory: {profile_dir}")
            else:
                print_lg("Chrome profile not found. Continuing in guest mode.")

        try:
            driver = uc.Chrome(options=options)
        except WebDriverException as exc:
            self.logger.log_exception("Failed to launch Chrome", exc)
            raise

        try:
            driver.maximize_window()
        except WebDriverException:
            driver.set_window_size(1920, 1080)

        driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {
                "source": (
                    "Object.defineProperty(navigator, 'webdriver', "
                    "{get: () => undefined})"
                )
            },
        )

        self.driver = driver
        self.wait = WebDriverWait(driver, self.settings.driver_wait_seconds)
        self.actions = ActionChains(driver)
        print_lg("Chrome launched successfully.")
        return driver, self.wait

    def close(self) -> None:
        if self.driver:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
        self.driver = None
        self.wait = None
        self.actions = None

    def is_logged_in(self) -> bool:
        if not self.driver:
            return False
        current_url = self.driver.current_url
        if current_url.startswith("https://www.linkedin.com/feed"):
            return True
        try:
            self.driver.find_element(By.LINK_TEXT, "Sign in")
            return False
        except NoSuchElementException:
            pass
        return "linkedin.com" in current_url

    def login(self, email: str, password: str) -> None:
        self.safe_login(email, password)

    def safe_launch_and_login(
        self,
        email: str,
        password: str,
        headless: bool = True,
        use_profile_dir: Optional[str] = None,
    ) -> bool:
        """
        Launch the browser, try cookie-based authentication first, and fallback to credentials.
        """
        self.launch(headless=headless, user_data_dir=use_profile_dir)
        assert self.driver is not None  # for type checkers

        self.driver.get("https://www.linkedin.com")
        cookies = load_cookies()
        if cookies:
            apply_cookies(self.driver, cookies)
            self.driver.refresh()
            if self._wait_for_feed(timeout=10):
                logger.info("Authenticated with LinkedIn using saved cookies.")
                return True
            logger.info("Stored cookies did not restore LinkedIn session; retrying with credentials.")

        try:
            self.safe_login(email, password)
            save_cookies(self.driver)
            return True
        except RuntimeError as exc:
            logger.warning("Credential login failed in headless=%s mode: %s", headless, exc)
            save_failed_login_screenshot(self.driver)
            if headless:
                self.close()
                self.launch(headless=False, user_data_dir=use_profile_dir)
                self.ui.headless = False
                assert self.driver is not None
                self.driver.get("https://www.linkedin.com")
                try:
                    self.safe_login(email, password)
                    save_cookies(self.driver)
                    return True
                except RuntimeError as second_exc:
                    save_failed_login_screenshot(self.driver)
                    raise RuntimeError("Unable to authenticate with LinkedIn.") from second_exc
            raise RuntimeError("Unable to authenticate with LinkedIn.") from exc

    def safe_login(self, email: str, password: str) -> None:
        if not self.driver or not self.wait:
            raise RuntimeError("Browser not launched.")

        max_attempts = 2
        attempt = 0

        while attempt < max_attempts:
            attempt += 1
            self.driver.get("https://www.linkedin.com/login")
            try:
                username_input = self.wait.until(
                    EC.presence_of_element_located((By.ID, "username"))
                )
                password_input = self.wait.until(
                    EC.presence_of_element_located((By.ID, "password"))
                )
                username_input.clear()
                username_input.send_keys(email)
                password_input.clear()
                password_input.send_keys(password)
                submit_button = self.driver.find_element(
                    By.XPATH, '//button[@type="submit" and contains(text(), "Sign in")]'
                )
                submit_button.click()
            except TimeoutException:
                self.logger.logger.warning(
                    "Login fields timed out waiting for interaction."
                )
            except NoSuchElementException as exc:
                self.logger.log_exception("Login fields not found", exc)

            if self._wait_for_feed():
                print_lg("LinkedIn login successful.")
                return

            self.logger.logger.warning(
                "LinkedIn login did not reach feed (attempt %s/%s). Possible CAPTCHA.",
                attempt,
                max_attempts,
            )
            save_failed_login_screenshot(self.driver)

        if not self.settings.headless and not self.ui.headless:
            prompt_response = self.ui.confirm(
                "LinkedIn login was not detected. Complete login manually and press OK.",
                title="LinkedIn Login Required",
                buttons=["OK", "Abort"],
            )
            if prompt_response != "Abort":
                if self._wait_for_feed():
                    print_lg("LinkedIn login detected after manual intervention.")
                    return
            self.logger.logger.warning("Manual login was not completed.")

        raise RuntimeError("Unable to authenticate with LinkedIn.")

    def _wait_for_feed(self, timeout: Optional[int] = None) -> bool:
        if not self.driver:
            return False
        try:
            if timeout is None and self.wait:
                wait_obj = self.wait
            else:
                wait_obj = WebDriverWait(self.driver, timeout or self.settings.driver_wait_seconds)
            wait_obj.until(EC.url_contains("https://www.linkedin.com/feed"))
            return True
        except TimeoutException:
            return False
