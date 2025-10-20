from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

import markdown2
from tenacity import retry, stop_after_attempt, wait_exponential

from modules.helpers import sanitize_filename, read_text_file, write_text_file
from modules.logger import AutomationLogger

# PATCHED BY CODEX
pdfkit = None

try:
    from weasyprint import HTML  # type: ignore
except Exception:  # pragma: no cover
    HTML = None

from openai import OpenAI


PROMPT_TEMPLATE = """
You are an expert resume writer.
Rewrite the following resume to match this job description.
Keep it concise, results-focused, and formatted in Markdown.
Return ONLY the rewritten Markdown text.

JOB DESCRIPTION:
{job_text}

BASE RESUME:
{base_resume}
"""


@dataclass
class ResumeRewriterConfig:
    base_resume_path: str
    output_dir: str = os.path.join("outputs", "resumes")
    model: str = "gpt-4o-mini"
    max_tokens: int = 2000


class ResumeRewriter:
    def __init__(
        self,
        config: ResumeRewriterConfig,
        logger: AutomationLogger,
        api_key: Optional[str],
        api_base: Optional[str] = None,
    ) -> None:
        self.config = config
        self.logger = logger
        self.api_key = api_key
        self.api_base = api_base or "https://api.openai.com/v1"
        self._client: Optional[OpenAI] = None
        os.makedirs(self.config.output_dir, exist_ok=True)

    @property
    def client(self) -> OpenAI:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not configured; resume rewriting disabled.")
        if not self._client:
            self._client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        return self._client

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, max=10))
    def _invoke_model(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=self.config.max_tokens,
        )
        return response.choices[0].message.content or ""

    def _convert_markdown_to_pdf(self, markdown_text: str, output_path: str) -> None:
        # PATCHED BY CODEX
        html_content = markdown2.markdown(markdown_text)
        html_path = output_path.replace(".pdf", ".html")
        write_text_file(html_path, html_content)

        if not HTML:
            self.logger.logger.error(
                "WeasyPrint is required but not installed; cannot generate PDF output."
            )
            raise RuntimeError("WeasyPrint dependency missing for resume generation.")

        HTML(string=html_content).write_pdf(output_path)

    def rewrite(
        self,
        job_title: str,
        company: str,
        job_description: str,
    ) -> Optional[str]:
        if not self.api_key:
            self.logger.logger.info(
                "OPENAI_API_KEY not set. Skipping resume rewriting step."
            )
            return None

        base_resume = read_text_file(self.config.base_resume_path)
        if not base_resume:
            self.logger.logger.warning(
                "Base resume content is empty at %s.", self.config.base_resume_path
            )
            return None

        prompt = PROMPT_TEMPLATE.format(
            job_text=job_description,
            base_resume=base_resume,
        )

        try:
            markdown_resume = self._invoke_model(prompt)
        except Exception as exc:
            self.logger.log_exception("Resume rewriting failed", exc)
            return None
        # PATCHED BY CODEX
        if "backend" in job_description.lower():
            backend_line = (
                "I have foundational knowledge of backend development "
                "(basic API integrations in PHP) and am eager to grow further in full-stack contexts."
            )
            if backend_line not in markdown_resume:
                markdown_resume = f"{markdown_resume.rstrip()}\n\n{backend_line}"

        safe_company = sanitize_filename(company)
        safe_title = sanitize_filename(job_title)
        filename = f"{safe_company}_{safe_title}.pdf"
        output_path = os.path.join(self.config.output_dir, filename)

        try:
            self._convert_markdown_to_pdf(markdown_resume, output_path)
        except Exception as exc:
            self.logger.log_exception("Resume PDF generation failed", exc)
            return None

        self.logger.logger.info("Generated resume: %s", output_path)
        return output_path
