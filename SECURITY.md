# Security Policy

## Reporting a Vulnerability

**Do not create a public issue for security vulnerabilities.**

Instead, report security issues privately:

1. **GitHub Security Advisories** (Preferred)
   - Go to: https://github.com/mintychochip/devpost-skill/security/advisories
   - Click "Report a vulnerability"
   - Provide details

2. **Email** (Alternative)
   - Send to: [your-email@example.com]
   - Subject: "Security: [brief description]"

## What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)
- Your contact info

## Response Time

- Acknowledgment: Within 48 hours
- Initial assessment: Within 1 week
- Fix timeline: Depends on severity (1-4 weeks)

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.7.x   | :white_check_mark: |
| < 0.7   | :x:                |

Always use the latest version for security patches.

## Security Best Practices

### For Users

- **Never commit credentials**: Use environment variables or `~/.devpost/.env`
- **Keep updated**: Update regularly for security patches
- **Review permissions**: Only grant necessary access

### For Contributors

- **No secrets in code**: Never commit API keys, passwords, tokens
- **Validate input**: Sanitize user input in commands
- **Secure dependencies**: Keep dependencies updated

## Known Limitations

- Credentials stored in `~/.devpost/.env` (file permissions: 600)
- Playwright browser automation may be detected by Devpost
- Rate limiting enabled to prevent abuse

## Security Audit

Last reviewed: May 2026

No known critical vulnerabilities.
