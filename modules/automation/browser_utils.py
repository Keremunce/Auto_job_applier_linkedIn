from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from modules.logger import AutomationLogger
from modules.ui import UIController
from modules.helpers import find_default_profile_directory, print_lg

try:
    import undetected_chromedriver as uc
except ImportError:  # pragma: no cover - optional dependency
    uc = None


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
        self.driver: Optional[webdriver.Chrome] = None
        self.wait: Optional[WebDriverWait] = None
        self.actions: Optional[ActionChains] = None

    def launch(self) -> None:
        if self.settings.stealth_mode:
            if uc is None:
                raise RuntimeError(
                    "undetected-chromedriver is required for stealth mode."
                )
            options = uc.ChromeOptions()
        else:
            options = Options()

        if self.settings.headless:
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")

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
            if self.settings.stealth_mode and uc:
                options.add_argument("--no-first-run")
                options.add_argument("--no-default-browser-check")
                driver = uc.Chrome(options=options)
            else:
                driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            self.logger.log_exception("Failed to launch Chrome", exc)
            raise

        driver.maximize_window()
        self.driver = driver
        self.wait = WebDriverWait(driver, self.settings.driver_wait_seconds)
        self.actions = ActionChains(driver)
        print_lg("Chrome launched successfully.")

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
        if not self.driver or not self.wait:
            raise RuntimeError("Browser not launched.")

        self.driver.get("https://www.linkedin.com/login")
        try:
            self.wait.until(
                EC.presence_of_element_located((By.ID, "username"))
            ).send_keys(Keys.CONTROL + "a")
            self.driver.find_element(By.ID, "username").send_keys(email)
            self.driver.find_element(By.ID, "password").send_keys(password)
            self.driver.find_element(
                By.XPATH, '//button[@type="submit" and contains(text(), "Sign in")]'
            ).click()
        except (TimeoutException, NoSuchElementException):
            self.logger.logger.warning("Login fields not found; awaiting manual login.")

        try:
            self.wait.until(
                EC.url_contains("https://www.linkedin.com/feed")
            )
        except TimeoutException:
            if self.ui.headless:
                raise RuntimeError("Login failed in headless mode.")
            prompt_response = self.ui.confirm(
                "LinkedIn login was not detected. Complete login manually and press OK.",
                title="LinkedIn Login Required",
                buttons=["OK", "Abort"],
            )
            if prompt_response == "Abort":
                raise RuntimeError("Login aborted by user.")
            # Wait again for successful login
            try:
                self.wait.until(
                    EC.url_contains("https://www.linkedin.com/feed")
                )
            except TimeoutException as exc:
                self.logger.log_exception("Login confirmation timeout", exc)
                raise RuntimeError("Manual login not detected.") from exc

        print_lg("LinkedIn login successful.")
