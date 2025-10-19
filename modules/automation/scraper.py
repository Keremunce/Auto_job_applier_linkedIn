from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from typing import Literal, Optional

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from modules.helpers import buffer, print_lg
from modules.clickers_and_finders import (
    boolean_button_click,
    find_by_class,
    multi_sel_noWait,
    try_find_by_classes,
    try_xp,
    wait_span_click,
    text_input,
)


logger = logging.getLogger(__name__)


@dataclass
class ScraperContext:
    """
    Context helper shared across LinkedIn automation flows.

    Provides a consistent interface for driver interactions, click pacing,
    and explicit waits.
    """

    driver: WebDriver
    click_gap: float = 1.0
    actions: Optional[ActionChains] = None
    wait_timeout: int = 10
    wait: Optional[WebDriverWait] = None

    def __post_init__(self) -> None:
        if self.driver is None:
            raise ValueError("ScraperContext requires an initialized WebDriver.")

        if self.wait is None:
            self.wait = WebDriverWait(self.driver, self.wait_timeout)
        self.wait_timeout = getattr(self.wait, "_timeout", self.wait_timeout)

        if self.actions is None:
            self.actions = ActionChains(self.driver)

    def wait_for_element(
        self,
        locator: tuple[str, str],
        timeout: int = 10,
    ) -> Optional[WebElement]:
        """
        Wait for an element to be present and return it when available.
        """
        reference_wait = self.wait or WebDriverWait(self.driver, timeout)
        if timeout != getattr(reference_wait, "_timeout", timeout):
            reference_wait = WebDriverWait(self.driver, timeout)

        try:
            return reference_wait.until(EC.presence_of_element_located(locator))
        except TimeoutException:
            logger.warning("Timed out waiting for locator %s in %s", locator, self)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.warning("Failed while waiting for locator %s: %s", locator, exc)
        return None

    def __repr__(self) -> str:
        session_id = getattr(self.driver, "session_id", "unknown")
        timeout = self.wait_timeout if self.wait else "unknown"
        return f"ScraperContext(driver_session={session_id}, click_gap={self.click_gap}, timeout={timeout})"


def apply_filters(
    ctx: ScraperContext,
    search_config,
) -> None:
    """
    Apply LinkedIn job filters based on configuration.
    """
    driver = ctx.driver
    wait = ctx.wait

    def _set_search_location() -> None:
        location = search_config.search_location.strip()
        if not location:
            return
        print_lg(f'Setting search location as: "{location}"')
        try:
            location_input = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, "input[aria-label='City, state, or zip code']")
                )
            )
            location_input.clear()
            location_input.send_keys(location)
            time.sleep(1.5)
            return
        except TimeoutException:
            logger.warning("Location input not found; skipping location filter.")
            return
        except ElementNotInteractableException:
            logger.warning("Standard location input interaction failed; attempting keyboard fallback.")
        except Exception as exc:
            logger.warning("Unexpected error while populating location input: %s", exc)

        try:
            try_xp(
                driver,
                ".//label[@class='jobs-search-box__input-icon jobs-search-box__keywords-label']",
            )
            ctx.actions.send_keys(Keys.TAB, Keys.TAB).perform()
            ctx.actions.key_down(Keys.CONTROL).send_keys("a").key_up(Keys.CONTROL).perform()
            ctx.actions.send_keys(location).perform()
            buffer(2)
            ctx.actions.send_keys(Keys.ENTER).perform()
            try_xp(driver, ".//button[@aria-label='Cancel']")
        except Exception as exc:
            try_xp(driver, ".//button[@aria-label='Cancel']")
            logger.warning("Failed to update search location via fallback; continuing without location filter. %s", exc)

    from selenium.webdriver.common.keys import Keys

    _set_search_location()

    try:
        recommended_wait = 1 if ctx.click_gap < 1 else 0
        wait.until(
            EC.presence_of_element_located((By.XPATH, '//button[normalize-space()="All filters"]'))
        ).click()
        buffer(recommended_wait)

        wait_span_click(driver, search_config.sort_by)
        wait_span_click(driver, search_config.date_posted)
        buffer(recommended_wait)

        multi_sel_noWait(driver, search_config.experience_level)
        multi_sel_noWait(driver, getattr(search_config, "companies", []), ctx.actions)
        if search_config.experience_level or getattr(search_config, "companies", []):
            buffer(recommended_wait)

        multi_sel_noWait(driver, search_config.job_type)
        multi_sel_noWait(driver, search_config.on_site)
        if search_config.job_type or search_config.on_site:
            buffer(recommended_wait)

        if search_config.easy_apply_only:
            boolean_button_click(driver, ctx.actions, "Easy Apply")

        location_filters = getattr(search_config, "location", []) or []
        if not location_filters:
            fallback_location = getattr(search_config, "search_location", "").strip()
            if fallback_location:
                location_filters = [fallback_location]
        if location_filters:
            multi_sel_noWait(driver, location_filters)

        industry_filters = getattr(search_config, "industry", []) or []
        if industry_filters:
            multi_sel_noWait(driver, industry_filters)

        if location_filters or industry_filters:
            buffer(recommended_wait)

        job_functions = getattr(search_config, "job_function", []) or []
        if job_functions:
            multi_sel_noWait(driver, job_functions)

        job_titles = getattr(search_config, "job_titles", []) or []
        if job_titles:
            multi_sel_noWait(driver, job_titles)

        if job_functions or job_titles:
            buffer(recommended_wait)

        if search_config.under_10_applicants:
            boolean_button_click(driver, ctx.actions, "Under 10 applicants")
        if search_config.in_your_network:
            boolean_button_click(driver, ctx.actions, "In your network")
        if search_config.fair_chance_employer:
            boolean_button_click(driver, ctx.actions, "Fair Chance Employer")

        wait_span_click(driver, search_config.salary)
        buffer(recommended_wait)

        benefits = getattr(search_config, "benefits", []) or []
        if benefits:
            multi_sel_noWait(driver, benefits)

        commitments = getattr(search_config, "commitments", []) or []
        if commitments:
            multi_sel_noWait(driver, commitments)

        if benefits or commitments:
            buffer(recommended_wait)

        show_results_button: WebElement = driver.find_element(
            By.XPATH, '//button[contains(@aria-label, "Apply current filters to show")]'
        )
        show_results_button.click()
    except Exception as exc:
        print_lg("Setting the preferences failed!", exc)


def get_page_info(ctx: ScraperContext) -> tuple[Optional[WebElement], Optional[int]]:
    try:
        pagination_element = try_find_by_classes(
            ctx.driver,
            [
                "jobs-search-pagination__pages",
                "artdeco-pagination",
                "artdeco-pagination__pages",
            ],
        )
        ctx.actions.move_to_element(pagination_element).perform()
        current_page = int(
            pagination_element.find_element(By.XPATH, "//button[contains(@class, 'active')]").text
        )
    except Exception as exc:
        print_lg("Failed to find pagination element.", exc)
        return None, None
    return pagination_element, current_page


def get_job_main_details(
    ctx: ScraperContext,
    job: WebElement,
    blacklisted_companies: set[str],
    rejected_jobs: set[str],
) -> tuple[str, str, str, str, str, bool]:
    job_details_button = job.find_element(By.TAG_NAME, "a")
    ctx.actions.move_to_element(job_details_button).perform()
    job_id = job.get_dom_attribute("data-occludable-job-id")
    title = job_details_button.text.partition("\n")[0]
    other_details = job.find_element(By.CLASS_NAME, "artdeco-entity-lockup__subtitle").text
    company, _, work_location = other_details.partition(" · ")
    if "(" in work_location and ")" in work_location:
        work_style = work_location[work_location.rfind("(") + 1 : work_location.rfind(")")]
        work_location = work_location[: work_location.rfind("(")].strip()
    else:
        work_style = "Unknown"

    skip = False
    if company in blacklisted_companies:
        print_lg(f'Skipping "{title} | {company}" (blacklisted company).')
        skip = True
    elif job_id in rejected_jobs:
        print_lg(f'Skipping previously rejected "{title} | {company}".')
        skip = True

    try:
        if job.find_element(By.CLASS_NAME, "job-card-container__footer-job-state").text == "Applied":
            print_lg(f'Already applied to "{title} | {company}".')
            skip = True
    except NoSuchElementException:
        pass

    if not skip:
        try:
            job_details_button.click()
        except ElementClickInterceptedException:
            logger.warning("Normal click failed, retrying with JS click.")
            ctx.driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", job_details_button
            )
            ctx.driver.execute_script("arguments[0].click();", job_details_button)
            time.sleep(1)
        except Exception as exc:
            logger.warning("Job card click failed: %s", exc)
            raise
        buffer(ctx.click_gap)

    return job_id, title, company, work_location, work_style, skip


def check_blacklist(
    ctx: ScraperContext,
    company: str,
    about_company_bad_words: list[str],
    about_company_good_words: list[str],
) -> tuple[bool, Optional[str], Optional[str], Optional[WebElement]]:
    jobs_top_card = try_find_by_classes(
        ctx.driver,
        [
            "job-details-jobs-unified-top-card__primary-description-container",
            "job-details-jobs-unified-top-card__primary-description",
            "jobs-unified-top-card__primary-description",
            "jobs-details__main-content",
        ],
    )
    about_company_org = find_by_class(ctx.driver, "jobs-company__box")
    ctx.actions.move_to_element(about_company_org).perform()
    about_company_text = about_company_org.text.lower()
    skip_checking = False
    for good_word in about_company_good_words:
        if good_word.lower() in about_company_text:
            print_lg(f'Found good word "{good_word}". Skipping blacklist checks.')
            skip_checking = True
            break

    if not skip_checking:
        for bad_word in about_company_bad_words:
            if bad_word.lower() in about_company_text:
                return True, "Found blacklisted company keyword", bad_word, jobs_top_card
    buffer(ctx.click_gap)
    ctx.actions.move_to_element(jobs_top_card).perform()
    return False, None, None, jobs_top_card


re_experience = re.compile(
    r"[(]?\s*(\d+)\s*[)]?\s*[-to]*\s*\d*[+]*\s*year[s]?",
    re.IGNORECASE,
)


def extract_years_of_experience(text: str) -> int:
    matches = re.findall(re_experience, text)
    if not matches:
        return 0
    return max(int(match) for match in matches if int(match) <= 40)


def get_job_description(
    ctx: ScraperContext,
    bad_words: list[str],
    security_clearance_required: bool,
    did_masters: bool,
    current_experience: int,
) -> tuple[
    str | Literal["Unknown"],
    int | Literal["Unknown"],
    bool,
    Optional[str],
    Optional[str],
]:
    job_description = "Unknown"
    experience_required: int | Literal["Unknown"] = "Unknown"
    skip = False
    skip_reason: Optional[str] = None
    skip_message: Optional[str] = None

    try:
        job_description = find_by_class(ctx.driver, "jobs-box__html-content").text
        job_description_low = job_description.lower()

        for word in bad_words:
            if word.lower() in job_description_low:
                skip_message = (
                    f'Job description contains blacklisted word "{word}". Skipping job.'
                )
                skip_reason = "Found bad word in job description"
                skip = True
                break

        if not skip and not security_clearance_required:
            if any(term in job_description_low for term in ["polygraph", "clearance", "secret"]):
                skip_message = "Security clearance requirement detected. Skipping job."
                skip_reason = "Security clearance required"
                skip = True

        found_masters = 0
        if not skip and did_masters and "master" in job_description_low:
            found_masters = 2

        experience_required = extract_years_of_experience(job_description)
        if (
            not skip
            and current_experience > -1
            and isinstance(experience_required, int)
            and experience_required > current_experience + found_masters
        ):
            skip_message = (
                f"Experience required ({experience_required}) exceeds configured limit."
            )
            skip_reason = "Required experience too high"
            skip = True
    except Exception as exc:
        print_lg("Unable to extract job description or experience requirements.", exc)

    return job_description, experience_required, skip, skip_reason, skip_message
