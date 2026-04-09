# Quick Test Setup Script
# Run this to quickly set up your testing environment

Write-Host "=== eBook Management System - Test Setup ===" -ForegroundColor Cyan
Write-Host ""

# Configuration
$sourcePath = "\\TS-469L\Multimedia\Books -sample DB - Copy\Sample [To Delete]"
$fixedPath = "\\TS-469L\Multimedia\Books -sample DB - Copy\Fixed [To Delete]"
$venvPath = ".\.venv\Scripts\Activate.ps1"

# Step 1: Check paths
Write-Host "[1/5] Checking paths..." -ForegroundColor Yellow
if (Test-Path $sourcePath) {
    Write-Host "  ✓ Source folder found: $sourcePath" -ForegroundColor Green
    $fileCount = (Get-ChildItem $sourcePath -Recurse -File).Count
    Write-Host "  ℹ Files in source: $fileCount" -ForegroundColor Cyan
} else {
    Write-Host "  ✗ Source folder not found: $sourcePath" -ForegroundColor Red
    exit 1
}

if (Test-Path $fixedPath) {
    Write-Host "  ✓ Fixed folder found: $fixedPath" -ForegroundColor Green
} else {
    Write-Host "  ℹ Fixed folder not found, creating..." -ForegroundColor Yellow
    New-Item -Path $fixedPath -ItemType Directory -Force | Out-Null
    Write-Host "  ✓ Fixed folder created" -ForegroundColor Green
}

# Step 2: Activate virtual environment
Write-Host ""
Write-Host "[2/5] Activating virtual environment..." -ForegroundColor Yellow
& $venvPath
Write-Host "  ✓ Virtual environment activated" -ForegroundColor Green

# Step 3: Check Django
Write-Host ""
Write-Host "[3/5] Checking Django..." -ForegroundColor Yellow
$checkResult = python manage.py check 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  ✓ Django configuration valid" -ForegroundColor Green
} else {
    Write-Host "  ✗ Django check failed" -ForegroundColor Red
    Write-Host $checkResult
    exit 1
}

# Step 4: Database status
Write-Host ""
Write-Host "[4/5] Checking database..." -ForegroundColor Yellow
python -c "from books.models import Book, ScanFolder; print(f'  ℹ Total books: {Book.objects.count()}'); print(f'  ℹ Scan folders: {ScanFolder.objects.count()}')"

# Step 5: File analysis
Write-Host ""
Write-Host "[5/5] Analyzing test files..." -ForegroundColor Yellow

$files = Get-ChildItem $sourcePath -Recurse -File
$stats = $files | Group-Object Extension | Sort-Object Count -Descending

Write-Host "  File Type Distribution:" -ForegroundColor Cyan
foreach ($stat in $stats) {
    $ext = if ($stat.Name) { $stat.Name } else { "(no ext)" }
    Write-Host "    $ext : $($stat.Count) files" -ForegroundColor White
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Next Steps:" -ForegroundColor Cyan
Write-Host "1. Ensure test files are in: $sourcePath" -ForegroundColor White
Write-Host "2. Start dev server: python manage.py runserver" -ForegroundColor White
Write-Host "3. Open browser: http://127.0.0.1:8000" -ForegroundColor White
Write-Host "4. Add scan folder in UI" -ForegroundColor White
Write-Host "5. Follow TESTING_WORKFLOW.md" -ForegroundColor White
Write-Host ""
Write-Host "Quick Commands:" -ForegroundColor Cyan
Write-Host "  Start server:    python manage.py runserver" -ForegroundColor White
Write-Host "  Django shell:    python manage.py shell" -ForegroundColor White
Write-Host "  Run tests:       python manage.py test books.tests.test_cover_upload -v 2" -ForegroundColor White
Write-Host "  Create admin:    python manage.py createsuperuser" -ForegroundColor White
Write-Host ""
