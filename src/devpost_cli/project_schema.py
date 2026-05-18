"""Pydantic schemas for project submission configuration."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ProjectLinks(BaseModel):
    """Project link configuration."""
    github: Optional[str] = Field(None, description="GitHub repository URL")
    demo: Optional[str] = Field(None, description="Live demo URL")
    video: Optional[str] = Field(None, description="Demo video URL (YouTube, Vimeo)")
    website: Optional[str] = Field(None, description="Project website URL")


class ProjectConfig(BaseModel):
    """Project submission configuration.
    
    This schema defines the structure for devpost.yaml manifest files.
    After first submission, project_url is written back to enable updates.
    """
    hackathon: str = Field(..., description="Hackathon slug (e.g., 'my-hackathon')")
    title: str = Field(..., description="Project title")
    tagline: str = Field(..., description="Short description (max 140 chars)")
    description: Optional[str] = Field(None, description="Inline markdown description")
    description_file: Optional[str] = Field(None, description="Path to markdown file (takes priority over inline description)")
    built_with: Optional[list[str]] = Field(None, description="Technologies used")
    links: Optional[ProjectLinks] = Field(None, description="Project links")
    images: Optional[list[str]] = Field(None, description="Screenshot/image paths (first = main image)")
    project_url: Optional[str] = Field(None, description="Devpost project URL (set after first submit)")
    
    @field_validator("tagline")
    @classmethod
    def validate_tagline_length(cls, v):
        if v and len(v) > 140:
            raise ValueError(f"Tagline must be 140 characters or less (got {len(v)})")
        return v
    
    @field_validator("images")
    @classmethod
    def validate_images(cls, v):
        if v and len(v) > 10:
            raise ValueError("Maximum 10 images allowed")
        return v
