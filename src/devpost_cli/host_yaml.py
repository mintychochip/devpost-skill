"""YAML/JSON config file handling for hackathon hosting."""

import json
from pathlib import Path
from typing import Any, Optional

import yaml

from .host_schema import HackathonConfig


CONFIG_TEMPLATE = """# Devpost Hackathon Configuration
# Generate with: devpost host init

name: "My Hackathon"
type: in-person  # in-person | online-student | online-paid
start_date: "2026-07-01"

# essentials:
#   url_slug: my-hackathon
#   tagline: "Build the future"
#   manager_email: organizer@example.com
#   host: "Acme Inc"
#   themes: [Machine Learning/AI, Cloud]
#   timezone: America/New_York

# eligibility:
#   community: public  # public | invite-only
#   occupation: professional  # professional | college | high-school
#   team_mode: teams_and_individuals
#   min_team_size: 1
#   max_team_size: 4

# dates:
#   submission_open: "2026-07-01T09:00"
#   submission_close: "2026-07-31T23:59"
#   judging_start: "2026-08-01T09:00"
#   judging_end: "2026-08-07T23:59"
#   winners_announced: "2026-08-10"

# design:
#   thumbnail: thumbnail.png
#   header_title_text: "My Hackathon"
#   header_title_color: "#ffffff"
#   header_bg_color: "#1a1a2e"

# description:
#   overview: |
#     Welcome to My Hackathon!
#   eligibility_blurb: |
#     Open to developers worldwide, 18+...
#   submission_requirements: |
#     Build an AI-powered application...

# rules:
#   text: |
#     1. ELIGIBILITY: ...
#     2. REQUIREMENTS: ...
#   resources:
#     - title: "API Documentation"
#       url: "https://docs.example.com"

# sponsors:
#   - name: "Acme Corp"
#     logo: sponsors/acme.png
#     section: Gold
#     url: "https://acme.com"

# judging:
#   mode: online  # online | offline
#   criteria:
#     - name: Creativity
#     - name: Impact
#     - name: Completeness
#   judge_comments: optional  # required | optional | disabled

# prizes:
#   - name: Grand Prize
#     type: cash  # cash | cash_and_other | crypto | crypto_and_other | other
#     amount: 10000
#     currency: USD
#     opt_in: false

# todos:
#   chat_link: "https://discord.gg/myhack"
#   custom:
#     - action: Signup
#       label: "Create an account"
#       url: "https://platform.example.com/signup"

# starter_kit:
#   subject: "Welcome to My Hackathon!"
#   body: |
#     Hi! Thanks for registering...

# submissions:
#   require_video: true
#   file_upload: true
#   final_reminders: "Don't forget to submit by July 31!"
#   custom_registration_questions:
#     - question: "How did you hear about us?"
#       type: dropdown
#       options: [Twitter, LinkedIn, Friend, Other]
#   custom_submission_questions:
#     - question: "Project category"
#       type: dropdown
#       options: [Web, Mobile, AI/ML, IoT, Other]
#       show_to_judges: true
"""


def load_config(config_path: str) -> HackathonConfig:
    """Load and validate a hackathon configuration file.
    
    Supports both YAML and JSON formats.
    
    Args:
        config_path: Path to the config file (.yaml, .yml, or .json)
        
    Returns:
        Validated HackathonConfig object
        
    Raises:
        FileNotFoundError: Config file doesn't exist
        ValueError: Invalid config format or validation errors
    """
    path = Path(config_path)
    
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    content = path.read_text(encoding="utf-8")
    
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(content)
    elif path.suffix.lower() == ".json":
        data = json.loads(content)
    else:
        # Try YAML first, then JSON
        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            try:
                data = json.loads(content)
            except json.JSONDecodeError as e:
                raise ValueError(f"Unable to parse config file (tried YAML and JSON): {e}")
    
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML/JSON object")
    
    return HackathonConfig.model_validate(data)


def load_config_from_string(content: str, format: str = "yaml") -> HackathonConfig:
    """Load and validate a hackathon configuration from a string.
    
    Args:
        content: YAML or JSON string content
        format: "yaml" or "json"
        
    Returns:
        Validated HackathonConfig object
    """
    if format == "yaml":
        data = yaml.safe_load(content)
    elif format == "json":
        data = json.loads(content)
    else:
        raise ValueError(f"Unknown format: {format}. Use 'yaml' or 'json'.")
    
    return HackathonConfig.model_validate(data)


def generate_template() -> str:
    """Generate a blank configuration template.
    
    Returns:
        YAML template string with all fields commented out
    """
    return CONFIG_TEMPLATE.strip()


def generate_minimal_template(name: str = "My Hackathon", start_date: str = "2026-07-01", hackathon_type: str = "in-person") -> str:
    """Generate a minimal configuration template with required fields.
    
    Args:
        name: Hackathon name
        start_date: Start date for the hackathon
        hackathon_type: Type of hackathon (in-person, online-student, online-paid)
        
    Returns:
        Minimal YAML template string
    """
    return f"""# Minimal Devpost Hackathon Configuration
name: "{name}"
type: {hackathon_type}
start_date: "{start_date}"

# Run 'devpost host init --full' for complete template with all options
"""


def config_to_dict(config: HackathonConfig) -> dict[str, Any]:
    """Convert a HackathonConfig to a plain dictionary.
    
    Args:
        config: HackathonConfig object
        
    Returns:
        Dictionary representation
    """
    return config.model_dump(mode="json", exclude_none=True)


def config_to_yaml(config: HackathonConfig) -> str:
    """Convert a HackathonConfig to YAML string.
    
    Args:
        config: HackathonConfig object
        
    Returns:
        YAML string representation
    """
    return yaml.dump(config_to_dict(config), default_flow_style=False, sort_keys=False)


def config_to_json(config: HackathonConfig, indent: int = 2) -> str:
    """Convert a HackathonConfig to JSON string.
    
    Args:
        config: HackathonConfig object
        indent: JSON indentation level
        
    Returns:
        JSON string representation
    """
    return json.dumps(config_to_dict(config), indent=indent)
