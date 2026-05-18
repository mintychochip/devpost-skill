# Install Devpost CLI (PowerShell)

Write-Host "Installing Devpost CLI..." -ForegroundColor Green

# Clone repo
$REPO = "https://github.com/mintychochip/devpost-skill.git"
$TEMP_DIR = Join-Path $env:TEMP "devpost-cli-install"
if (Test-Path $TEMP_DIR) { Remove-Item $TEMP_DIR -Recurse -Force }
New-Item -ItemType Directory -Path $TEMP_DIR | Out-Null
Set-Location $TEMP_DIR

git clone $REPO devpost-cli
Set-Location devpost-cli

# Install package
pip install -e .

# Install playwright browser
playwright install chromium

Write-Host "Devpost CLI installed successfully!" -ForegroundColor Green
Write-Host "Run: devpost --help" -ForegroundColor Gray

# Cleanup
Set-Location $env:TEMP
Remove-Item $TEMP_DIR -Recurse -Force
