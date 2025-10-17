from __future__ import annotations

import logging
import os
import pickle
from dataclasses import dataclass
from typing import Optional

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

SESSION_COOKIE_PATH = os.path.join("outputs", "session_cookies.pkl")

logger = logging.getLogger(__name__)


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

    def launch(self) -> tuple[WebDriver, WebDriverWait]:
        options = uc.ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        # Modern undetected_chromedriver compatibility
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-features=AutomationControlled")
        options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")

        if self.settings.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            logger.info("Headless login bypass active.")
            print_lg("Headless login bypass active.")

        if self.settings.disable_extensions:
            options.add_argument("--disable-extensions")

        if self.settings.safe_mode:
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

    def safe_login(self, email: str, password: str) -> None:
        if not self.driver or not self.wait:
            raise RuntimeError("Browser not launched.")

        if self._load_session_from_cookies():
            if self._wait_for_feed():
                print_lg("LinkedIn session restored from cookies.")
                return
            logger.info("Session cookies were invalid; continuing with credential login.")

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
                self._save_session_cookies()
                return

            self.logger.logger.warning(
                "LinkedIn login did not reach feed (attempt %s/%s). Possible CAPTCHA.",
                attempt,
                max_attempts,
            )
            self._capture_failed_login()

            if attempt == 1 and self.settings.headless:
                self.logger.logger.warning(
                    "Headless login failed; retrying once with visible Chrome."
                )
                self._restart_driver(headless=False)
                if self._load_session_from_cookies() and self._wait_for_feed():
                    print_lg("LinkedIn session restored from cookies.")
                    return
                continue

        if not self.settings.headless and not self.ui.headless:
            prompt_response = self.ui.confirm(
                "LinkedIn login was not detected. Complete login manually and press OK.",
                title="LinkedIn Login Required",
                buttons=["OK", "Abort"],
            )
            if prompt_response != "Abort":
                if self._wait_for_feed():
                    print_lg("LinkedIn login detected after manual intervention.")
                    self._save_session_cookies()
                    return
            self.logger.logger.warning("Manual login was not completed.")

        raise RuntimeError("Unable to authenticate with LinkedIn.")

    def _wait_for_feed(self) -> bool:
        if not self.driver or not self.wait:
            return False
        try:
            self.wait.until(EC.url_contains("https://www.linkedin.com/feed"))
            return True
        except TimeoutException:
            return False

    def _restart_driver(self, headless: bool) -> None:
        original_headless = self.settings.headless
        try:
            self.close()
        finally:
            self.settings.headless = headless
            if not headless and self.ui.headless:
                self.ui.headless = False
        driver, wait = self.launch()
        self.driver = driver
        self.wait = wait
        self.actions = ActionChains(driver)
        if original_headless != headless:
            logger.info("Browser relaunched with headless=%s for login retry.", headless)

    def _save_session_cookies(self) -> None:
        if not self.driver:
            return
        try:
            os.makedirs(os.path.dirname(SESSION_COOKIE_PATH), exist_ok=True)
            with open(SESSION_COOKIE_PATH, "wb") as cookie_file:
                pickle.dump(self.driver.get_cookies(), cookie_file)
            logger.info("Session cookies saved to %s", SESSION_COOKIE_PATH)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.log_exception("Failed to save session cookies", exc)

    def _load_session_from_cookies(self) -> bool:
        if not self.driver or not os.path.exists(SESSION_COOKIE_PATH):
            return False
        try:
            with open(SESSION_COOKIE_PATH, "rb") as cookie_file:
                cookies = pickle.load(cookie_file)
            self.driver.get("https://www.linkedin.com/")
            for cookie in cookies:
                cookie_dict = cookie.copy()
                cookie_dict.pop("expiry", None)
                self.driver.add_cookie(cookie_dict)
            self.driver.get("https://www.linkedin.com/feed")
            logger.info("Session cookies loaded, attempting feed redirect.")
            return True
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.log_exception("Failed to load session cookies", exc)
            return False

    def _capture_failed_login(self) -> None:
        if not self.driver:
            return
        try:
            os.makedirs(os.path.join("outputs", "logs"), exist_ok=True)
            screenshot_path = os.path.join("outputs", "logs", "failed_login.png")
            self.driver.save_screenshot(screenshot_path)
            logger.warning("Saved failed login screenshot to %s", screenshot_path)
        except WebDriverException as exc:
            self.logger.log_exception("Failed to capture login screenshot", exc)
