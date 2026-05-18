"""YAML/JSON config file handling for project submissions."""

import json
from pathlib import Path
from typing import Any, Optional

import yaml

from .project_schema import ProjectConfig, ProjectLinks
from .logging_config import get_logger

logger = get_logger("project_yaml")


def markdown_to_html(md_text: str) -> str:
    """Convert markdown to HTML for Devpost rich text field.
    
    Uses the markdown library for conversion. Devpost's description
    field accepts HTML, so we convert markdown for better formatting.
    """
    try:
        import markdown
        # Use extensions commonly used in project descriptions
        html = markdown.markdown(
            md_text,
            extensions=[
                'tables',
                'fenced_code',
                'toc',
            ]
        )
        return html
    except ImportError:
        logger.warning("markdown library not installed, using raw text")
        # Fallback: escape basic HTML and return as-is
        return md_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def load_config(config_path: str) -> ProjectConfig:
    """Load and validate a project config file.
    
    Args:
        config_path: Path to YAML or JSON config file
        
    Returns:
        Validated ProjectConfig object
        
    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If config is invalid
    """
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        if path.suffix in ('.yaml', '.yml'):
            data = yaml.safe_load(f)
        elif path.suffix == '.json':
            data = json.load(f)
        else:
            # Default to YAML
            data = yaml.safe_load(f)
    
    # Resolve relative paths (images, description_file) relative to config file location
    config_dir = path.parent
    
    if data.get('images'):
        data['images'] = [
            str((config_dir / img_path).resolve()) if not Path(img_path).is_absolute() else img_path
            for img_path in data['images']
        ]
    
    if data.get('description_file'):
        desc_file = data['description_file']
        if not Path(desc_file).is_absolute():
            data['description_file'] = str((config_dir / desc_file).resolve())
    
    return ProjectConfig(**data)


def config_to_yaml(config: ProjectConfig) -> str:
    """Convert a ProjectConfig to YAML string."""
    data = config.model_dump(exclude_none=True, by_alias=True)
    return yaml.dump(data, default_flow_style=False, sort_keys=False)


def config_to_json(config: ProjectConfig) -> str:
    """Convert a ProjectConfig to JSON string."""
    data = config.model_dump(exclude_none=True, by_alias=True)
    return json.dumps(data, indent=2)


def generate_template() -> str:
    """Generate a minimal devpost.yaml template."""
    return """# Devpost Project Submission Configuration
# Generate with: devpost submit init
# 
# This file defines your project metadata. Version it alongside your code.
# After first submission, project_url will be added automatically.

hackathon: my-hackathon-slug

title: "My Project"
tagline: "Short description of what we built (max 140 chars)"

# Reference a markdown file for the description (recommended)
description_file: SUBMISSION.md

# Or use inline description (uncomment if preferred)
# description: |
#   ## What We Built
#   Describe your project here...

built_with:
  - Python
  - React
  - OpenAI

links:
  github: https://github.com/user/repo
  demo: https://demo.example.com
  # video: https://youtube.com/watch?v=...
  # website: https://example.com

# Screenshots/images (first image = main)
# Paths are relative to this config file
images:
  - screenshots/main.png
  - screenshots/demo.gif

# project_url will be set automatically after first submission
# project_url: https://devpost.com/software/my-project
""".strip()


def generate_submission_md_template() -> str:
    """Generate a SUBMISSION.md template."""
    return """# What We Built

<!-- Describe your project here. This markdown will be converted to HTML for Devpost. -->

Brief overview of your project and what it does.

## Features

- Feature 1
- Feature 2
- Feature 3

## How We Built It

<!-- Describe your tech stack, architecture, and approach -->

We used [technology] to build...

## Challenges We Faced

<!-- What obstacles did you overcome? -->

## Future Plans

<!-- What's next for this project? -->
""".strip()


def save_config(config: ProjectConfig, config_path: str) -> None:
    """Save a ProjectConfig to a YAML file.
    
    Args:
        config: ProjectConfig object
        config_path: Path to save YAML file
    """
    path = Path(config_path)
    
    # Convert absolute paths back to relative if possible
    data = config.model_dump(exclude_none=True, by_alias=True)
    config_dir = path.parent
    
    if data.get('images') and config_dir.exists():
        relative_images = []
        for img_path in data['images']:
            try:
                img = Path(img_path)
                if img.is_absolute():
                    relative_images.append(str(img.relative_to(config_dir)))
                else:
                    relative_images.append(img_path)
            except ValueError:
                # Can't make relative, keep absolute
                relative_images.append(img_path)
        data['images'] = relative_images
    
    if data.get('description_file') and config_dir.exists():
        desc_file = Path(data['description_file'])
        if desc_file.is_absolute():
            try:
                data['description_file'] = str(desc_file.relative_to(config_dir))
            except ValueError:
                pass  # Keep absolute
    
    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def update_project_url(config_path: str, project_url: str) -> None:
    """Update the project_url field in a config file.
    
    Called after successful submission to enable future updates.
    
    Args:
        config_path: Path to config file
        project_url: Devpost project URL to save
    """
    config = load_config(config_path)
    config.project_url = project_url
    save_config(config, config_path)
