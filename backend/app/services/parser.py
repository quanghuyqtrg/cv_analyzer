"""Hybrid CV parser: regex extraction + Claude API for complex sections."""

import json
import logging
import os
import re

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

# Section header patterns (EN + VN, with/without diacritics)
_SECTION_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("education", re.compile(
        r"^(?:education|học vấn|hoc van|trình độ học vấn|trinh do hoc van|bằng cấp|bang cap)\s*$",
        re.IGNORECASE,
    )),
    ("work_experience", re.compile(
        r"^(?:work\s*experience|experience|professional\s*experience|"
        r"kinh nghiệm(?:\s*làm việc)?|kinh nghiem(?:\s*lam viec)?|"
        r"quá trình công tác|qua trinh cong tac)\s*$",
        re.IGNORECASE,
    )),
    ("skills", re.compile(
        r"^(?:skills|technical\s*skills|kỹ năng|ky nang|năng lực|nang luc)\s*$",
        re.IGNORECASE,
    )),
    ("certifications", re.compile(
        r"^(?:certifications?|certificates?|licenses?|"
        r"chứng chỉ|chung chi|bằng cấp chứng chỉ)\s*$",
        re.IGNORECASE,
    )),
    ("languages", re.compile(
        r"^(?:languages?|ngoại ngữ|ngoai ngu|ngôn ngữ|ngon ngu)\s*$",
        re.IGNORECASE,
    )),
    ("summary", re.compile(
        r"^(?:summary|objective|profile|about\s*me|"
        r"mục tiêu(?:\s*nghề nghiệp)?|muc tieu(?:\s*nghe nghiep)?|"
        r"giới thiệu|gioi thieu|tóm tắt|tom tat)\s*$",
        re.IGNORECASE,
    )),
    ("personal_info", re.compile(
        r"^(?:personal\s*(?:info(?:rmation)?|details)|"
        r"thông tin(?:\s*cá nhân)?|thong tin(?:\s*ca nhan)?)\s*$",
        re.IGNORECASE,
    )),
    ("projects", re.compile(
        r"^(?:projects?|dự án|du an)\s*$",
        re.IGNORECASE,
    )),
    ("references", re.compile(
        r"^(?:references?|người tham chiếu|nguoi tham chieu)\s*$",
        re.IGNORECASE,
    )),
]


def _detect_sections(text: str) -> dict[str, str]:
    """Split text into named sections based on header detection.

    Text before the first recognized header goes into "header".
    """
    lines = text.splitlines()
    sections: dict[str, str] = {}
    current_section = "header"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        # Remove common decorations around section headers
        cleaned = re.sub(r"^[#\-=_*:]+\s*", "", stripped)
        cleaned = re.sub(r"\s*[#\-=_*:]+$", "", cleaned)

        matched = False
        for section_name, pattern in _SECTION_PATTERNS:
            if pattern.match(cleaned):
                # Save previous section
                if current_lines:
                    sections[current_section] = "\n".join(current_lines).strip()
                current_section = section_name
                current_lines = []
                matched = True
                break

        if not matched:
            current_lines.append(line)

    # Save last section
    if current_lines:
        sections[current_section] = "\n".join(current_lines).strip()

    return sections


# ---------------------------------------------------------------------------
# Regex extraction (contacts, skills, languages)
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[-.\s]?)?\(?\d{2,4}\)?[-.\s]?\d{3,4}[-.\s]?\d{3,4}"
)
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w-]+/?")
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w-]+/?")
_WEBSITE_RE = re.compile(r"https?://[^\s,]+")


def _extract_contact_info(header_text: str, personal_section: str) -> dict:
    """Extract personal/contact info using regex."""
    combined = f"{header_text}\n{personal_section}".strip()
    lines = combined.splitlines()

    email = None
    phone = None
    linkedin = None
    github = None
    website = None
    full_name = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if not email:
            m = _EMAIL_RE.search(stripped)
            if m:
                email = m.group()

        if not phone:
            m = _PHONE_RE.search(stripped)
            if m:
                candidate = m.group()
                # Basic sanity: at least 7 digits
                digits = re.sub(r"\D", "", candidate)
                if len(digits) >= 7:
                    phone = candidate

        if not linkedin:
            m = _LINKEDIN_RE.search(stripped)
            if m:
                linkedin = m.group()

        if not github:
            m = _GITHUB_RE.search(stripped)
            if m:
                github = m.group()

        if not website:
            m = _WEBSITE_RE.search(stripped)
            if m:
                url = m.group()
                # Skip linkedin/github already captured
                if "linkedin.com" not in url and "github.com" not in url:
                    website = url

    # Full name: first non-empty line that isn't an email/phone/URL
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _EMAIL_RE.search(stripped):
            continue
        if _WEBSITE_RE.search(stripped):
            continue
        # Skip lines that are mostly digits (phone lines)
        digits = re.sub(r"\D", "", stripped)
        if len(digits) > 5 and len(digits) / len(stripped) > 0.5:
            continue
        full_name = stripped
        break

    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "address": None,
        "linkedin": linkedin,
        "github": github,
        "website": website,
        "date_of_birth": None,
    }


def _extract_skills(section_text: str) -> list[str]:
    """Split skills section into individual skill strings."""
    if not section_text or not section_text.strip():
        return []

    # Split by common delimiters: comma, semicolon, bullet, newline
    items = re.split(r"[,;\n]|[-*](?:\s)", section_text)
    skills = []
    for item in items:
        cleaned = item.strip().strip("-*").strip()
        if cleaned and len(cleaned) < 100:
            skills.append(cleaned)
    return skills


def _extract_languages(section_text: str) -> list[dict]:
    """Extract language name and proficiency level."""
    if not section_text or not section_text.strip():
        return []

    lines = re.split(r"[,;\n]|[-*](?:\s)", section_text)
    languages = []
    for line in lines:
        line = line.strip().strip("-*").strip()
        if not line:
            continue

        # Try splitting by colon or dash: "English: Fluent" or "English - Fluent"
        parts = re.split(r"\s*[:\-]\s*", line, maxsplit=1)
        name = parts[0].strip()
        proficiency = parts[1].strip() if len(parts) > 1 else None

        if name:
            languages.append({"name": name, "proficiency": proficiency})

    return languages


# ---------------------------------------------------------------------------
# Claude API layer (for complex sections)
# ---------------------------------------------------------------------------

_ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

_SECTION_PROMPTS = {
    "education": {
        "schema": [
            {"institution": "str", "degree": "str", "field_of_study": "str",
             "start_date": "str", "end_date": "str", "gpa": "str", "description": "str"}
        ],
        "instruction": (
            "Extract education entries from this CV section. "
            "Return a JSON array of objects. Each object should have: "
            "institution, degree, field_of_study, start_date, end_date, gpa, description. "
            "Use null for missing fields. Handle both Vietnamese and English text."
        ),
    },
    "work_experience": {
        "schema": [
            {"company": "str", "position": "str", "start_date": "str",
             "end_date": "str", "description": "str", "location": "str"}
        ],
        "instruction": (
            "Extract work experience entries from this CV section. "
            "Return a JSON array of objects. Each object should have: "
            "company, position, start_date, end_date, description, location. "
            "Use null for missing fields. Handle both Vietnamese and English text."
        ),
    },
    "certifications": {
        "schema": [
            {"name": "str", "issuer": "str", "date": "str", "credential_id": "str"}
        ],
        "instruction": (
            "Extract certification entries from this CV section. "
            "Return a JSON array of objects. Each object should have: "
            "name, issuer, date, credential_id. "
            "Use null for missing fields. Handle both Vietnamese and English text."
        ),
    },
}


def _parse_with_llm(section_name: str, section_text: str) -> list[dict] | str | None:
    """Use Claude API to parse a complex CV section into structured data.

    Returns parsed list of dicts on success, raw text on API failure, None if empty.
    """
    if not section_text or not section_text.strip():
        return []

    prompt_config = _SECTION_PROMPTS.get(section_name)
    if not prompt_config:
        return section_text.strip()

    if not _ANTHROPIC_API_KEY or _ANTHROPIC_API_KEY.startswith("sk-ant-your-key"):
        logger.warning("ANTHROPIC_API_KEY not configured, returning raw text for %s", section_name)
        return _fallback_raw(section_name, section_text)

    try:
        client = anthropic.Anthropic(api_key=_ANTHROPIC_API_KEY)
        response = client.messages.create(
            model="claude-haiku-4-20250514",
            max_tokens=2048,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"{prompt_config['instruction']}\n\n"
                        f"Expected JSON schema: {json.dumps(prompt_config['schema'])}\n\n"
                        f"CV section text:\n{section_text}\n\n"
                        "Respond with ONLY valid JSON, no explanation."
                    ),
                }
            ],
        )
        raw_response = response.content[0].text.strip()

        # Extract JSON from response (may be wrapped in markdown code blocks)
        json_match = re.search(r"\[.*\]", raw_response, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())

        return json.loads(raw_response)

    except (anthropic.APIError, json.JSONDecodeError) as exc:
        logger.warning("Claude API parsing failed for %s: %s", section_name, exc)
        return _fallback_raw(section_name, section_text)
    except Exception as exc:
        logger.warning("Unexpected error parsing %s with LLM: %s", section_name, exc)
        return _fallback_raw(section_name, section_text)


def _fallback_raw(section_name: str, section_text: str) -> list[dict]:
    """Return raw text wrapped in the appropriate schema when LLM parsing fails."""
    if section_name == "education":
        return [{"institution": None, "degree": None, "field_of_study": None,
                 "start_date": None, "end_date": None, "gpa": None,
                 "description": section_text.strip()}]
    elif section_name == "work_experience":
        return [{"company": None, "position": None, "start_date": None,
                 "end_date": None, "description": section_text.strip(),
                 "location": None}]
    elif section_name == "certifications":
        return [{"name": None, "issuer": None, "date": None,
                 "credential_id": None}]
    return []


# ---------------------------------------------------------------------------
# Main parse function
# ---------------------------------------------------------------------------

def parse_cv_text(raw_text: str) -> dict:
    """Parse raw CV text into structured data using regex + Claude API.

    Returns a dict conforming to the ParsedCV schema.
    """
    sections = _detect_sections(raw_text)

    personal_info = _extract_contact_info(
        sections.get("header", ""),
        sections.get("personal_info", ""),
    )
    skills = _extract_skills(sections.get("skills", ""))
    languages = _extract_languages(sections.get("languages", ""))

    # Claude API for complex sections
    education = _parse_with_llm("education", sections.get("education", ""))
    work_experience = _parse_with_llm("work_experience", sections.get("work_experience", ""))
    certifications = _parse_with_llm("certifications", sections.get("certifications", ""))

    summary = sections.get("summary", "").strip() or None

    return {
        "personal_info": personal_info,
        "summary": summary,
        "education": education if isinstance(education, list) else [],
        "work_experience": work_experience if isinstance(work_experience, list) else [],
        "skills": skills,
        "certifications": certifications if isinstance(certifications, list) else [],
        "languages": languages,
    }
