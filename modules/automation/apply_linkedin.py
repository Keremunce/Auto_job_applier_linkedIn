from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime
from random import choice, shuffle
from typing import Optional, Literal
from urllib.parse import quote_plus

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC

import config.questions as questions_config
import config.search as search_config
import config.settings as settings_config
import config.personals as personals_config

from modules.automation.browser_utils import BrowserController
from modules.automation.scraper import (
    ScraperContext,
    apply_filters as scraper_apply_filters,
    check_blacklist,
    get_job_description,
    get_job_main_details,
    get_page_info,
)
from modules.helpers import (
    buffer,
    calculate_date_posted,
    convert_to_lakhs,
    make_directories,
    print_lg,
    truncate_for_csv,
)
from modules.clickers_and_finders import (
    find_by_class,
    try_find_by_classes,
    try_xp,
    wait_span_click,
)
from modules.logger import AutomationLogger
from modules.ui import UIController
from modules.ai.resume_rewriter import ResumeRewriter


@dataclass
class LinkedInCredentials:
    email: str
    password: str


@dataclass
class SessionStats:
    easy_apply_count: int = 0
    external_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    randomly_answered: set[str] = field(default_factory=set)


class LinkedInApplier:
    """
    Orchestrates the LinkedIn job application flow.
    """

    def __init__(
        self,
        browser: BrowserController,
        credentials: LinkedInCredentials,
        logger: AutomationLogger,
        ui: UIController,
        resume_rewriter: Optional[ResumeRewriter] = None,
    ) -> None:
        self.browser = browser
        self.credentials = credentials
        self.logger = logger
        self.ui = ui
        self.resume_rewriter = resume_rewriter

        self.settings = settings_config
        self.questions = questions_config
        self.search = search_config
        self.personals = personals_config

        self.pause_before_submit = self.questions.pause_before_submit
        self.pause_at_failed_question = self.questions.pause_at_failed_question
        self.run_non_stop = self.settings.run_non_stop
        if self.settings.run_in_background:
            self.pause_before_submit = False
            self.pause_at_failed_question = False
            self.run_non_stop = False

        self.click_gap = self.settings.click_gap
        self.stats = SessionStats()
        self.applied_jobs = self._load_previous_applications()
        self.blacklisted_companies: set[str] = set()
        self.rejected_jobs: set[str] = set()

        self.default_resume_path = self.questions.default_resume_path
        self.use_new_resume = True

        self.desired_salary = str(self.questions.desired_salary)
        self.desired_salary_lakhs = str(round(self.questions.desired_salary / 100000, 2))
        self.desired_salary_monthly = str(round(self.questions.desired_salary / 12, 2))
        self.current_ctc = str(self.questions.current_ctc)
        self.current_ctc_lakhs = str(round(self.questions.current_ctc / 100000, 2))
        self.current_ctc_monthly = str(round(self.questions.current_ctc / 12, 2))
        self.notice_period = str(self.questions.notice_period)
        self.notice_period_months = str(self.questions.notice_period // 30)
        self.notice_period_weeks = str(self.questions.notice_period // 7)

        self.full_name = " ".join(
            filter(None, [self.personals.first_name, self.personals.middle_name, self.personals.last_name])
        )

        make_directories(
            [
                os.path.join("outputs", "logs"),
                os.path.join("outputs", "resumes"),
                self.default_resume_path,
            ]
        )

    def _load_previous_applications(self) -> set[str]:
        success_log = os.path.join("outputs", "logs", "success.csv")
        job_ids: set[str] = set()
        if not os.path.exists(success_log):
            return job_ids
        try:
            with open(success_log, "r", encoding="utf-8") as csv_file:
                reader = csv.DictReader(csv_file)
                for row in reader:
                    url = row.get("job_url")
                    if url and url.rstrip("/").split("/")[-1].isdigit():
                        job_ids.add(url.rstrip("/").split("/")[-1])
        except Exception as exc:
            self.logger.log_exception("Failed to load previous applications", exc)
        return job_ids

    def _get_scraper_context(self) -> ScraperContext:
        if not self.browser.driver or not self.browser.wait or not self.browser.actions:
            raise RuntimeError("Browser driver not initialized.")
        return ScraperContext(
            driver=self.browser.driver,
            wait=self.browser.wait,
            actions=self.browser.actions,
            click_gap=self.click_gap,
        )

    def _rewrite_resume(self, job_title: str, company: str, description: str) -> Optional[str]:
        if not description or description == "Unknown":
            return None
        if not self.resume_rewriter:
            return None
        return self.resume_rewriter.rewrite(job_title, company, description)

    def launch_and_login(self) -> None:
        profile_dir = os.getenv("CHROME_PROFILE_DIR") or None
        self.browser.safe_launch_and_login(
            self.credentials.email,
            self.credentials.password,
            headless=self.browser.settings.headless,
            use_profile_dir=profile_dir,
        )

    def run(self) -> None:
        search_terms = list(self.search.search_terms)
        if self.search.randomize_search_order:
            shuffle(search_terms)

        total_runs = 1
        try:
            self.launch_and_login()
            self._process_search_terms(search_terms)
            while self.run_non_stop:
                if self.settings.cycle_date_posted:
                    options = ["Any time", "Past month", "Past week", "Past 24 hours"]
                    current_index = options.index(self.search.date_posted)
                    next_index = (current_index + 1) % len(options)
                    self.search.date_posted = options[next_index]
                if self.settings.alternate_sortby:
                    self.search.sort_by = (
                        "Most recent"
                        if self.search.sort_by == "Most relevant"
                        else "Most relevant"
                    )
                self._process_search_terms(search_terms)
                total_runs += 1
        except KeyboardInterrupt:
            self.logger.logger.info("Interrupted by user. Exiting gracefully.")
        except (NoSuchElementException, TimeoutException, WebDriverException) as exc:
            self.logger.log_exception("Fatal browser error", exc)
        finally:
            self._summarize(total_runs)
            self.browser.close()

    def _process_search_terms(self, search_terms: list[str]) -> None:
        ctx = self._get_scraper_context()
        for term in search_terms:
            url = (
                "https://www.linkedin.com/jobs/search/?keywords="
                + quote_plus(term)
            )
            self.browser.driver.get(url)
            print_lg(f'Starting search for "{term}"')
            scraper_apply_filters(ctx, self.search)
            self._iterate_job_pages(ctx)

    def _iterate_job_pages(self, ctx: ScraperContext) -> None:
        current_count = 0
        while current_count < self.search.switch_number:
            ctx.wait.until(
                EC.presence_of_all_elements_located((By.XPATH, "//li[@data-occludable-job-id]"))
            )
            pagination_element, current_page = get_page_info(ctx)
            buffer(3)
            job_listings = ctx.driver.find_elements(By.XPATH, "//li[@data-occludable-job-id]")

            for job in job_listings:
                if self.settings.keep_screen_awake:
                    self.ui.keep_awake()
                if current_count >= self.search.switch_number:
                    break
                result = self._process_single_job(ctx, job)
                if result:
                    current_count += 1

            if not pagination_element:
                print_lg("No pagination element found; reached end of results.")
                break
            if current_page is None:
                break
            try:
                next_button = pagination_element.find_element(
                    By.XPATH, f"//button[@aria-label='Page {current_page + 1}']"
                )
                next_button.click()
                print_lg(f"Switching to page {current_page + 1}")
            except NoSuchElementException:
                print_lg("No more pages in pagination.")
                break

    def _process_single_job(
        self,
        ctx: ScraperContext,
        job,
    ) -> bool:
        job_id, title, company, work_location, work_style, skip = get_job_main_details(
            ctx, job, self.blacklisted_companies, self.rejected_jobs
        )
        if skip or job_id in self.applied_jobs:
            return False

        job_link = f"https://www.linkedin.com/jobs/view/{job_id}"

        blacklist_skip, _, bad_word, jobs_top_card = check_blacklist(
            ctx,
            company,
            self.search.about_company_bad_words,
            self.search.about_company_good_words,
        )
        if blacklist_skip:
            message = f"Skipping {company} due to blacklisted term {bad_word}"
            self.logger.log_failure(title, company, job_link, message)
            self.rejected_jobs.add(job_id)
            self.stats.skipped_count += 1
            return False

        if not jobs_top_card:
            try:
                jobs_top_card = try_find_by_classes(
                    ctx.driver,
                    [
                        "job-details-jobs-unified-top-card__primary-description-container",
                        "job-details-jobs-unified-top-card__primary-description",
                        "jobs-unified-top-card__primary-description",
                        "jobs-details__main-content",
                    ],
                )
            except Exception:
                jobs_top_card = None

        if jobs_top_card:
            try:
                time_posted_text = jobs_top_card.find_element(
                    By.XPATH, './/span[contains(normalize-space(), " ago")]'
                ).text
                if "Reposted" in time_posted_text:
                    time_posted_text = time_posted_text.replace("Reposted", "")
                date_listed = calculate_date_posted(time_posted_text.strip())
            except Exception:
                date_listed = None
        else:
            date_listed = None

        description, experience_required, skip_job, skip_reason, skip_message = get_job_description(
            ctx,
            self.search.bad_words,
            self.search.security_clearance,
            self.search.did_masters,
            self.search.current_experience,
        )
        if skip_job:
            self.logger.log_failure(
                title,
                company,
                job_link,
                skip_message or skip_reason or "Skipped job",
            )
            self.rejected_jobs.add(job_id)
            self.stats.skipped_count += 1
            return False

        resume_path = self._rewrite_resume(title, company, description)
        try:
            applied = self._attempt_apply(
                ctx,
                job_id,
                job_link,
                title,
                company,
                work_location,
                work_style,
                description,
                experience_required,
                date_listed,
                resume_path,
            )
            if applied:
                self.applied_jobs.add(job_id)
                return True
        except Exception as exc:
            self.logger.log_exception("Unhandled error during application", exc)
            self.stats.failed_count += 1
            self.logger.log_failure(
                title, company, job_link, "Unhandled exception during apply", resume_path
            )
        return False

    def _attempt_apply(
        self,
        ctx: ScraperContext,
        job_id: str,
        job_link: str,
        title: str,
        company: str,
        work_location: str,
        work_style: str,
        description: str,
        experience_required: int | Literal["Unknown"],
        date_listed: Optional[datetime],
        resume_path: Optional[str],
    ) -> bool:
        driver = ctx.driver
        try:
            easy_apply_button = try_xp(
                driver,
                ".//button[contains(@class,'jobs-apply-button') and contains(@class, 'artdeco-button--3') and contains(@aria-label, 'Easy')]",
                click=False,
            )
            if easy_apply_button:
                gained_resume_path = self._handle_easy_apply(
                    ctx,
                    job_id,
                    job_link,
                    title,
                    company,
                    work_location,
                    work_style,
                    description,
                    experience_required,
                    date_listed,
                    resume_path,
                )
                if gained_resume_path:
                    resume_path = gained_resume_path
                self.logger.log_success(title, company, job_link, resume_path)
                self.stats.easy_apply_count += 1
                return True
            else:
                application_link = self._handle_external_apply(ctx)
                self.logger.log_success(
                    title,
                    company,
                    application_link or job_link,
                    resume_path,
                )
                self.stats.external_count += 1
                return True
        except Exception as exc:
            self.stats.failed_count += 1
            self.logger.log_failure(
                title, company, job_link, str(exc), resume_path
            )
            raise
        return False

    def _handle_external_apply(
        self,
        ctx: ScraperContext,
    ) -> str:
        driver = ctx.driver
        try:
            ctx.wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, ".//button[contains(@class,'jobs-apply-button') and contains(@class, 'artdeco-button--3')]")
                )
            ).click()
            wait_span_click(driver, "Continue", 1, True, False)
            windows = driver.window_handles
            driver.switch_to.window(windows[-1])
            application_link = driver.current_url
            if self.settings.close_tabs and driver.current_window_handle != windows[0]:
                driver.close()
            driver.switch_to.window(windows[0])
            return application_link
        except Exception as exc:
            raise RuntimeError(f"Failed to capture external application link: {exc}") from exc

    def _handle_easy_apply(
        self,
        ctx: ScraperContext,
        job_id: str,
        job_link: str,
        title: str,
        company: str,
        work_location: str,
        work_style: str,
        description: str,
        experience_required: int | Literal["Unknown"],
        date_listed: Optional[datetime],
        resume_path: Optional[str],
    ) -> Optional[str]:
        driver = ctx.driver
        wait = ctx.wait
        try:
            wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, ".//button[contains(@class,'jobs-apply-button') and contains(@class, 'artdeco-button--3') and contains(@aria-label, 'Easy')]")
                )
            ).click()
            modal = find_by_class(driver, "jobs-easy-apply-modal")
            wait_span_click(modal, "Next", 1)
            resume_used = resume_path or "Previous resume"
            questions_list = set()
            next_steps = True
            next_counter = 0
            while next_steps:
                next_counter += 1
                if next_counter >= 15 and self.pause_at_failed_question and not self.ui.headless:
                    self.ui.alert(
                        "Could not answer some questions automatically. "
                        "Provide answers manually and return to this dialog."
                    )
                    next_counter = 1
                questions_list = self._answer_questions(modal, questions_list, work_location, description)
                if self.use_new_resume and resume_used == "Previous resume":
                    uploaded, resume_used = self._upload_resume(modal, resume_used)
                    if uploaded:
                        self.use_new_resume = False
                try:
                    modal.find_element(By.XPATH, './/span[normalize-space(.)="Review"]')
                    next_steps = False
                except NoSuchElementException:
                    next_button = modal.find_element(By.XPATH, './/button[contains(span, "Next")]')
                    next_button.click()
                    buffer(self.click_gap)

            wait_span_click(driver, "Review", 1, scrollTop=True)
            if self.pause_before_submit and not self.ui.headless:
                decision = self.ui.confirm(
                    "Review the application before submitting.",
                    buttons=["Submit Application", "Disable Pause", "Discard"],
                )
                if decision == "Discard":
                    raise RuntimeError("Application discarded by user.")
                if decision == "Disable Pause":
                    self.pause_before_submit = False
            submitted = wait_span_click(driver, "Submit application", 2, scrollTop=True)
            if submitted:
                return resume_used
            raise RuntimeError("Submit button was not clickable.")
        except Exception as exc:
            raise RuntimeError(f"Easy apply failed: {exc}") from exc

    def _upload_resume(self, modal, resume_path: str) -> tuple[bool, str]:
        try:
            modal.find_element(By.NAME, "file").send_keys(os.path.abspath(self.default_resume_path))
            return True, os.path.basename(self.default_resume_path)
        except Exception:
            return False, resume_path

    def _answer_questions(
        self,
        modal,
        questions_list: set,
        work_location: str,
        job_description: Optional[str] = None,
    ) -> set:
        # Simplified version relying on stored answers.
        all_questions = modal.find_elements(By.XPATH, ".//div[@data-test-form-element]")
        for question in all_questions:
            select = try_xp(question, ".//select", False)
            if select:
                label = try_xp(question, ".//label", False)
                label_text = label.text if label else "Unknown"
                questions_list.add((label_text, "select"))
                continue
            text = try_xp(question, ".//input[@type='text']", False)
            if text:
                label = try_xp(question, ".//label", False)
                label_text = label.text if label else "Unknown"
                text.clear()
                answer = self._default_answer(label_text.lower(), work_location)
                text.send_keys(answer)
                questions_list.add((label_text, answer))
                continue
            text_area = try_xp(question, ".//textarea", False)
            if text_area:
                label = try_xp(question, ".//label", False)
                label_text = label.text if label else "Unknown"
                text_area.clear()
                answer = self.questions.linkedin_summary.strip()
                text_area.send_keys(answer)
                questions_list.add((label_text, "textarea"))
                continue
        return questions_list

    def _default_answer(self, label: str, work_location: str) -> str:
        if "visa" in label:
            return self.questions.require_visa
        if "first name" in label:
            return self.personals.first_name
        if "last name" in label:
            return self.personals.last_name
        if "phone" in label:
            return self.personals.phone_number
        if "linkedin" in label:
            return self.questions.linkedIn
        if "website" in label or "portfolio" in label:
            return self.questions.website
        if "headline" in label:
            return self.questions.linkedin_headline
        if "city" in label:
            return self.personals.current_city or work_location
        if "state" in label:
            return self.personals.state
        if "country" in label:
            return self.personals.country
        if "zipcode" in label or "postal" in label:
            return self.personals.zipcode
        if "notice" in label and "month" in label:
            return self.notice_period_months
        if "notice" in label and "week" in label:
            return self.notice_period_weeks
        if "notice" in label:
            return self.notice_period
        if "salary" in label or "compensation" in label:
            if "current" in label:
                if "month" in label:
                    return self.current_ctc_monthly
                if "lakh" in label:
                    return self.current_ctc_lakhs
                return self.current_ctc
            if "month" in label:
                return self.desired_salary_monthly
            if "lakh" in label:
                return self.desired_salary_lakhs
            return self.desired_salary
        if "experience" in label and "year" in label:
            return self.questions.years_of_experience
        return "Yes"

    def _summarize(self, total_runs: int) -> None:
        quotes = [
            "You're one step closer than before.",
            "All the best with your future interviews.",
            "Keep up with the progress. You got this.",
            "If you're tired, learn to take rest but never give up.",
            "Success is not final, failure is not fatal: It is the courage to continue that counts. - Winston Churchill",
            "Believe in yourself and all that you are. Know that there is something inside you that is greater than any obstacle. - Christian D. Larson",
        ]
        print_lg(f"Total runs: {total_runs}")
        print_lg(f"Jobs Easy Applied: {self.stats.easy_apply_count}")
        print_lg(f"External job links collected: {self.stats.external_count}")
        print_lg(f"Failed jobs: {self.stats.failed_count}")
        print_lg(f"Irrelevant jobs skipped: {self.stats.skipped_count}")
        print_lg(choice(quotes))
