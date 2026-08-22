from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PersonalInfo(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    address: str | None = None
    linkedin: str | None = None
    github: str | None = None
    website: str | None = None
    date_of_birth: str | None = None


class Education(BaseModel):
    institution: str | None = None
    degree: str | None = None
    field_of_study: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    gpa: str | None = None
    description: str | None = None


class WorkExperience(BaseModel):
    company: str | None = None
    position: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    description: str | None = None
    location: str | None = None


class Certification(BaseModel):
    name: str | None = None
    issuer: str | None = None
    date: str | None = None
    credential_id: str | None = None


class Language(BaseModel):
    name: str | None = None
    proficiency: str | None = None


class ParsedCV(BaseModel):
    personal_info: PersonalInfo | None = None
    summary: str | None = None
    education: list[Education] = []
    work_experience: list[WorkExperience] = []
    skills: list[str] = []
    certifications: list[Certification] = []
    languages: list[Language] = []


class CVResponse(BaseModel):
    id: UUID
    filename: str
    parsed_data: ParsedCV
    raw_text: str
    created_at: datetime

    model_config = {"from_attributes": True}
