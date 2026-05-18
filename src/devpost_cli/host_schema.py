"""Pydantic schemas for hackathon hosting configuration."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator


class EssentialsConfig(BaseModel):
    """Essentials tab configuration."""
    url_slug: Optional[str] = Field(None, description="Hackathon URL slug (locked after publish)")
    tagline: Optional[str] = Field(None, description="Short CTA phrase")
    manager_email: Optional[str] = Field(None, description="Manager contact email")
    host: Optional[str] = Field(None, description="Host organization name")
    themes: Optional[list[str]] = Field(None, description="Up to 3 theme tags")
    hackathon_type: Optional[str] = Field(None, description="Hackathon type categorization")
    timezone: Optional[str] = Field("America/New_York", description="Timezone for dates")

    @field_validator("themes")
    @classmethod
    def validate_themes(cls, v):
        if v and len(v) > 3:
            raise ValueError("Maximum 3 themes allowed")
        return v


class EligibilityConfig(BaseModel):
    """Eligibility tab configuration."""
    community: str = Field("public", description="public or invite-only")
    invite_community_name: Optional[str] = Field(None, description="Community name if invite-only")
    min_age: Optional[int] = Field(None, description="Minimum age requirement")
    occupation: Optional[str] = Field(None, description="professional, college, high-school, middle-school")
    team_mode: Optional[str] = Field(None, description="individuals, teams, or teams_and_individuals")
    min_team_size: Optional[int] = Field(1, description="Minimum team size")
    max_team_size: Optional[int] = Field(4, description="Maximum team size")
    geo_restrictions: Optional[list[str]] = Field(None, description="Restricted countries/regions")

    @field_validator("community")
    @classmethod
    def validate_community(cls, v):
        if v not in ("public", "invite-only"):
            raise ValueError("community must be 'public' or 'invite-only'")
        return v

    @field_validator("occupation")
    @classmethod
    def validate_occupation(cls, v):
        valid = ("professional", "college", "high-school", "middle-school")
        if v and v not in valid:
            raise ValueError(f"occupation must be one of: {valid}")
        return v

    @field_validator("team_mode")
    @classmethod
    def validate_team_mode(cls, v):
        valid = ("individuals", "teams", "teams_and_individuals")
        if v and v not in valid:
            raise ValueError(f"team_mode must be one of: {valid}")
        return v


class DatesConfig(BaseModel):
    """Dates configuration across multiple tabs."""
    submission_open: Optional[str] = Field(None, description="Submission period start (ISO format)")
    submission_close: Optional[str] = Field(None, description="Submission period end (ISO format)")
    judging_start: Optional[str] = Field(None, description="Judging period start")
    judging_end: Optional[str] = Field(None, description="Judging period end")
    voting_start: Optional[str] = Field(None, description="Public voting start")
    voting_end: Optional[str] = Field(None, description="Public voting end")
    winners_announced: Optional[str] = Field(None, description="Winner announcement date")


class DesignConfig(BaseModel):
    """Design tab configuration."""
    thumbnail: Optional[str] = Field(None, description="Path to 300x300px thumbnail image")
    header_title_text: Optional[str] = Field(None, description="Header title text (if not using image)")
    header_title_color: Optional[str] = Field(None, description="Header title text color")
    header_bg_color: Optional[str] = Field(None, description="Header background color")
    header_bg_image: Optional[str] = Field(None, description="Path to header background image (2000x246px)")
    header_title_image: Optional[str] = Field(None, description="Path to header title image (1170x156px)")


class DescriptionConfig(BaseModel):
    """Overview page text configuration."""
    overview: Optional[str] = Field(None, description="Main description (who, what, why)")
    eligibility_blurb: Optional[str] = Field(None, description="Brief eligibility summary")
    submission_requirements: Optional[str] = Field(None, description="'What to build' statement")


class ResourceConfig(BaseModel):
    """Resource link configuration."""
    title: str
    url: str


class RulesConfig(BaseModel):
    """Rules and resources tab configuration."""
    text: Optional[str] = Field(None, description="Official rules document")
    resources: Optional[list[ResourceConfig]] = Field(None, description="Resource links")


class SponsorConfig(BaseModel):
    """Sponsor configuration."""
    name: str
    logo: Optional[str] = Field(None, description="Path to sponsor logo")
    section: Optional[str] = Field("Sponsor", description="Sponsor section/level")
    url: Optional[str] = Field(None, description="Sponsor website URL")


class JudgingCriteriaConfig(BaseModel):
    """Judging criteria configuration."""
    name: str
    weight: Optional[int] = Field(1, description="Criteria weight")


class JudgingConfig(BaseModel):
    """Judging tab configuration."""
    mode: str = Field("online", description="online or offline")
    criteria: Optional[list[JudgingCriteriaConfig]] = Field(None, description="Judging criteria")
    judge_comments: Optional[str] = Field("optional", description="required, optional, or disabled")
    judges: Optional[list[str]] = Field(None, description="Judge emails or Devpost usernames")

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        if v not in ("online", "offline"):
            raise ValueError("mode must be 'online' or 'offline'")
        return v

    @field_validator("judge_comments")
    @classmethod
    def validate_judge_comments(cls, v):
        if v not in ("required", "optional", "disabled"):
            raise ValueError("judge_comments must be 'required', 'optional', or 'disabled'")
        return v


class PrizeConfig(BaseModel):
    """Prize configuration."""
    name: str
    type: str = Field("cash", description="cash, cash_and_other, crypto, crypto_and_other, other")
    amount: Optional[float] = Field(None, description="Prize amount")
    currency: Optional[str] = Field("USD", description="Currency symbol")
    breakdown: Optional[str] = Field(None, description="Prize breakdown details")
    other_prize: Optional[str] = Field(None, description="Non-cash prize description")
    opt_in: Optional[bool] = Field(False, description="Show on submission form and gallery filters")

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        valid = ("cash", "cash_and_other", "crypto", "crypto_and_other", "other")
        if v not in valid:
            raise ValueError(f"type must be one of: {valid}")
        return v


class TodoConfig(BaseModel):
    """Custom to-do configuration."""
    action: str = Field(..., description="Action verb: Download, Signup, Register, Read, Review, Attend, Request, Go")
    label: str
    url: str

    @field_validator("action")
    @classmethod
    def validate_action(cls, v):
        valid = ("Download", "Signup", "Register", "Read", "Review", "Attend", "Request", "Go")
        if v not in valid:
            raise ValueError(f"action must be one of: {valid}")
        return v


class TodosConfig(BaseModel):
    """To-dos tab configuration."""
    chat_link: Optional[str] = Field(None, description="Slack/Discord/Facebook invite link")
    custom: Optional[list[TodoConfig]] = Field(None, description="Up to 3 custom to-dos")


class StarterKitConfig(BaseModel):
    """Starter Kit email configuration."""
    subject: Optional[str] = Field(None, description="Email subject line")
    body: Optional[str] = Field(None, description="Rich text email body")


class QuestionOptionConfig(BaseModel):
    """Dropdown question option."""
    value: str


class RegistrationQuestionConfig(BaseModel):
    """Custom registration question."""
    question: str
    type: str = Field("text", description="text, dropdown, url")
    options: Optional[list[str]] = Field(None, description="Options for dropdown type")
    required: Optional[bool] = Field(False)


class SubmissionQuestionConfig(BaseModel):
    """Custom submission form question."""
    question: str
    type: str = Field("text", description="text, dropdown, url")
    options: Optional[list[str]] = Field(None, description="Options for dropdown type")
    show_to_judges: Optional[bool] = Field(False)
    required: Optional[bool] = Field(False)


class SubmissionsConfig(BaseModel):
    """Submissions tab configuration."""
    require_video: Optional[bool] = Field(False)
    file_upload: Optional[bool] = Field(False)
    file_upload_required: Optional[bool] = Field(False)
    final_reminders: Optional[str] = Field(None, description="Text shown on last step of submission form")
    custom_registration_questions: Optional[list[RegistrationQuestionConfig]] = Field(None)
    custom_submission_questions: Optional[list[SubmissionQuestionConfig]] = Field(None)


class HackathonConfig(BaseModel):
    """Complete hackathon configuration."""
    name: str = Field(..., description="Hackathon name")
    type: str = Field("in-person", description="in-person, online-student, or online-paid")
    start_date: str = Field(..., description="Hackathon start date for collecting projects")

    essentials: Optional[EssentialsConfig] = None
    eligibility: Optional[EligibilityConfig] = None
    dates: Optional[DatesConfig] = None
    design: Optional[DesignConfig] = None
    description: Optional[DescriptionConfig] = None
    rules: Optional[RulesConfig] = None
    sponsors: Optional[list[SponsorConfig]] = None
    judging: Optional[JudgingConfig] = None
    prizes: Optional[list[PrizeConfig]] = None
    todos: Optional[TodosConfig] = None
    starter_kit: Optional[StarterKitConfig] = None
    submissions: Optional[SubmissionsConfig] = None

    @field_validator("type")
    @classmethod
    def validate_type(cls, v):
        valid = ("in-person", "online-student", "online-paid")
        if v not in valid:
            raise ValueError(f"type must be one of: {valid}")
        return v
