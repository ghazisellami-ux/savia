#!/usr/bin/env pwsh
# Deployment Health Check for SAVIA

Write-Host "`n========================================================" -ForegroundColor Cyan
Write-Host "SAVIA Deployment Health Check" -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

$checks = @()

# Check 1: Frontend Build
Write-Host "Checking Frontend Build..." -ForegroundColor Yellow
if (Test-Path "frontend/.next") {
    Write-Host "OK: Frontend build OK" -ForegroundColor Green
    $checks += $true
} else {
    Write-Host "FAIL: Frontend build missing" -ForegroundColor Red
    $checks += $false
}

# Check 2: Backend Files
Write-Host "Checking Backend Files..." -ForegroundColor Yellow
$backendFiles = @("backend/main.py", "backend/auth.py", "backend/db_engine.py", "backend/requirements.txt")
$missing = @()
foreach ($file in $backendFiles) {
    if (-not (Test-Path $file)) {
        $missing += $file
    }
}
if ($missing.Count -eq 0) {
    Write-Host "OK: Backend files OK" -ForegroundColor Green
    $checks += $true
} else {
    Write-Host "FAIL: Backend files missing" -ForegroundColor Red
    $checks += $false
}

# Check 3: Admin Page Modifications
Write-Host "Checking Admin Page Modifications..." -ForegroundColor Yellow
$adminPagePath = "frontend/src/app/(authenticated)/admin/page.tsx"
if (Test-Path $adminPagePath) {
    $content = Get-Content $adminPagePath -Raw
    $admin_ok = $true
    
    if ($content -notmatch "adminOnly: true") {
        Write-Host "  FAIL: Missing adminOnly flag" -ForegroundColor Red
        $admin_ok = $false
    }
    
    if ($content -notmatch "filter.*adminOnly.*admin") {
        Write-Host "  FAIL: Missing role-based filtering" -ForegroundColor Red
        $admin_ok = $false
    }
    
    if ($content -notmatch "defaultTab.*admin.*settings") {
        Write-Host "  FAIL: Missing defaultTab logic" -ForegroundColor Red
        $admin_ok = $false
    }
    
    if ($admin_ok) {
        Write-Host "OK: Admin page modifications OK" -ForegroundColor Green
        $checks += $true
    } else {
        $checks += $false
    }
} else {
    Write-Host "FAIL: Admin page not found" -ForegroundColor Red
    $checks += $false
}

# Check 4: Auth Context Permissions
Write-Host "Checking Auth Context Permissions..." -ForegroundColor Yellow
$authContextPath = "frontend/src/lib/auth-context.tsx"
if (Test-Path $authContextPath) {
    $content = Get-Content $authContextPath -Raw
    if ($content -match "settings: true") {
        Write-Host "OK: Auth context permissions OK" -ForegroundColor Green
        $checks += $true
    } else {
        Write-Host "FAIL: Missing settings permissions" -ForegroundColor Red
        $checks += $false
    }
} else {
    Write-Host "FAIL: Auth context not found" -ForegroundColor Red
    $checks += $false
}

# Check 5: Git Status
Write-Host "Checking Git Status..." -ForegroundColor Yellow
try {
    $branch = git rev-parse --abbrev-ref HEAD 2>$null
    if ($LASTEXITCODE -eq 0) {
        if ($branch -eq "develop") {
            Write-Host "OK: On develop branch" -ForegroundColor Green
            $checks += $true
        } else {
            Write-Host "FAIL: Not on develop branch (current: $branch)" -ForegroundColor Red
            $checks += $false
        }
    } else {
        Write-Host "FAIL: Git not available" -ForegroundColor Red
        $checks += $false
    }
} catch {
    Write-Host "FAIL: Git check failed" -ForegroundColor Red
    $checks += $false
}

# Summary
Write-Host "`n========================================================" -ForegroundColor Cyan
$passed = ($checks | Where-Object { $_ -eq $true }).Count
$total = $checks.Count
Write-Host "Results: $passed/$total checks passed" -ForegroundColor Cyan
Write-Host "========================================================`n" -ForegroundColor Cyan

if ($passed -eq $total) {
    Write-Host "SUCCESS: All checks passed! Ready to deploy." -ForegroundColor Green
    exit 0
} else {
    Write-Host "ERROR: Some checks failed. Please fix before deploying." -ForegroundColor Red
    exit 1
}
