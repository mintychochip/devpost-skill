# Contributing to Devpost CLI

## Quick Start

```bash
git clone https://github.com/mintychochip/devpost-skill.git
cd devpost-skill
pip install -e ".[dev]"
playwright install chromium
```

## Development

```bash
# Run tests
pytest

# Run integration tests
RUN_INTEGRATION_TESTS=1 pytest tests/test_integration_team_invites.py -v -s

# Lint (if configured)
ruff check .
```

## Pull Requests

1. Fork the repo
2. Create a branch: `git checkout -b feature/your-feature`
3. Make changes
4. Run tests: `pytest`
5. Commit: `git commit -m "Add your feature"`
6. Push: `git push origin feature/your-feature`
7. Open PR

## Testing

- Unit tests: `pytest tests/`
- Integration tests require `RUN_INTEGRATION_TESTS=1`
- Manual testing: see `docs/MANUAL_TESTING.md`

## Code Style

- Follow existing code style
- Use type hints
- Add docstrings for public functions
- Keep functions small and focused

## Reporting Issues

- Use GitHub Issues
- Include: what you tried, what happened, what you expected
- Add logs/error messages if applicable

## Security

- Report security issues privately via email or GitHub Security Advisories
- Do not post credentials/secrets in issues or PRs
- See `SECURITY.md` for details
