#!/usr/bin/env pwsh
<#
.SYNOPSIS
SAVIA Deployment Script for Windows
Déploie l'application depuis GitHub sur le VPS
#>

$VPS_USER = "ubuntu"
$VPS_IP = "51.91.124.49"
$VPS_PATH = "/home/ubuntu/savia"
$GITHUB_REPO = "https://github.com/ghazisellami-ux/savia.git"
$BRANCH = "develop"

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "SAVIA Deployment Script" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "VPS: $VPS_USER@$VPS_IP" -ForegroundColor Yellow
Write-Host "Path: $VPS_PATH" -ForegroundColor Yellow
Write-Host "Branch: $BRANCH" -ForegroundColor Yellow
Write-Host ""

# ==========================================
# 1. SSH Connection Test
# ==========================================
Write-Host "1. Testing SSH connection..." -ForegroundColor Yellow
try {
    $result = ssh -o ConnectTimeout=5 $VPS_USER@$VPS_IP "echo 'SSH OK'" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK: SSH connection successful" -ForegroundColor Green
    } else {
        Write-Host "FAIL: SSH connection failed" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "FAIL: SSH connection error: $_" -ForegroundColor Red
    exit 1
}

# ==========================================
# 2. Clone or Update Repository
# ==========================================
Write-Host "`n2. Updating repository..." -ForegroundColor Yellow
$updateScript = @"
cd /home/ubuntu

if [ -d "savia" ]; then
    echo "Repository exists, pulling latest changes..."
    cd savia
    git fetch origin
    git checkout $BRANCH
    git pull origin $BRANCH
else
    echo "Cloning repository..."
    git clone -b $BRANCH $GITHUB_REPO savia
    cd savia
fi

echo "Repository updated"
"@

ssh $VPS_USER@$VPS_IP $updateScript
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Repository updated" -ForegroundColor Green
} else {
    Write-Host "FAIL: Repository update failed" -ForegroundColor Red
    exit 1
}

# ==========================================
# 3. Check .env file
# ==========================================
Write-Host "`n3. Checking .env file..." -ForegroundColor Yellow
$envScript = @"
if [ ! -f "$VPS_PATH/.env" ]; then
    echo "Creating .env from .env.example..."
    cp $VPS_PATH/.env.example $VPS_PATH/.env
    echo "WARNING: .env file created from template"
    echo "Please edit .env with your configuration:"
    echo "   nano $VPS_PATH/.env"
else
    echo ".env file exists"
fi
"@

ssh $VPS_USER@$VPS_IP $envScript
Write-Host "OK: .env file checked" -ForegroundColor Green

# ==========================================
# 4. Stop existing containers
# ==========================================
Write-Host "`n4. Stopping existing containers..." -ForegroundColor Yellow
$stopScript = @"
cd $VPS_PATH
docker-compose down 2>/dev/null || true
echo "Containers stopped"
"@

ssh $VPS_USER@$VPS_IP $stopScript
Write-Host "OK: Containers stopped" -ForegroundColor Green

# ==========================================
# 5. Build Docker images
# ==========================================
Write-Host "`n5. Building Docker images (this may take a few minutes)..." -ForegroundColor Yellow
$buildScript = @"
cd $VPS_PATH
docker-compose build --no-cache
echo "Docker images built"
"@

ssh $VPS_USER@$VPS_IP $buildScript
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Docker images built" -ForegroundColor Green
} else {
    Write-Host "FAIL: Docker build failed" -ForegroundColor Red
    exit 1
}

# ==========================================
# 6. Start services
# ==========================================
Write-Host "`n6. Starting services..." -ForegroundColor Yellow
$startScript = @"
cd $VPS_PATH
docker-compose up -d
echo "Services started"
"@

ssh $VPS_USER@$VPS_IP $startScript
if ($LASTEXITCODE -eq 0) {
    Write-Host "OK: Services started" -ForegroundColor Green
} else {
    Write-Host "FAIL: Services failed to start" -ForegroundColor Red
    exit 1
}

# ==========================================
# 7. Wait for services
# ==========================================
Write-Host "`n7. Waiting for services to be ready (10 seconds)..." -ForegroundColor Yellow
Start-Sleep -Seconds 10
Write-Host "OK: Services should be ready" -ForegroundColor Green

# ==========================================
# 8. Check service status
# ==========================================
Write-Host "`n8. Checking service status..." -ForegroundColor Yellow
$statusScript = @"
cd $VPS_PATH
echo ""
echo "Service Status:"
docker-compose ps
echo ""
echo "Recent logs (last 20 lines):"
docker-compose logs --tail=20
"@

ssh $VPS_USER@$VPS_IP $statusScript

# ==========================================
# 9. Verify deployment
# ==========================================
Write-Host "`n9. Verifying deployment..." -ForegroundColor Yellow
$verifyScript = @"
echo ""
echo "Checking backend health..."
if curl -s http://localhost:8001/docs > /dev/null 2>&1; then
    echo "Backend is running"
else
    echo "Backend might not be ready yet (normal if just started)"
fi

echo ""
echo "Checking frontend..."
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo "Frontend is running"
else
    echo "Frontend might not be ready yet (normal if just started)"
fi
"@

ssh $VPS_USER@$VPS_IP $verifyScript

# ==========================================
# Summary
# ==========================================
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Cyan

Write-Host "Application URLs:" -ForegroundColor Yellow
Write-Host "   Frontend:    http://51.91.124.49:3000" -ForegroundColor Cyan
Write-Host "   Backend API: http://51.91.124.49:8001" -ForegroundColor Cyan
Write-Host "   API Docs:    http://51.91.124.49:8001/docs" -ForegroundColor Cyan

Write-Host "`nUseful commands:" -ForegroundColor Yellow
Write-Host "   View logs:     ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose logs -f'" -ForegroundColor Gray
Write-Host "   Stop services: ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose down'" -ForegroundColor Gray
Write-Host "   Restart:       ssh ubuntu@51.91.124.49 'cd /home/ubuntu/savia && docker-compose restart'" -ForegroundColor Gray
Write-Host "   SSH shell:     ssh ubuntu@51.91.124.49" -ForegroundColor Gray

Write-Host "`n========================================`n" -ForegroundColor Cyan
