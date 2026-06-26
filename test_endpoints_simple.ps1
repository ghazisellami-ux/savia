# ==========================================
# Test Multi-Tech Endpoints - Simple Version
# ==========================================

$API_BASE = "http://localhost:8001"
$ADMIN_USER = "admin"
$ADMIN_PASS = "admin"
$TECH_USER = "ghazi"
$TECH_PASS = "ghazi123"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Backend Endpoints Validation" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Step 1: Get Admin Token
Write-Host "Step 1: Getting Admin Token..." -ForegroundColor Yellow
$adminLoginResponse = Invoke-RestMethod -Uri "$API_BASE/api/auth/login" `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body (ConvertTo-Json @{ username = $ADMIN_USER; password = $ADMIN_PASS })

$ADMIN_TOKEN = $adminLoginResponse.token
Write-Host "✅ Admin Token obtained" -ForegroundColor Green
Write-Host ""

# Step 2: Get Technician Token
Write-Host "Step 2: Getting Technician Token..." -ForegroundColor Yellow
$techLoginResponse = Invoke-RestMethod -Uri "$API_BASE/api/auth/login" `
  -Method POST `
  -Headers @{ "Content-Type" = "application/json" } `
  -Body (ConvertTo-Json @{ username = $TECH_USER; password = $TECH_PASS })

$TECH_TOKEN = $techLoginResponse.token
$TECH_NAME = $techLoginResponse.user.nom
Write-Host "✅ Technician: $TECH_NAME" -ForegroundColor Green
Write-Host ""

# Step 3: Get all interventions
Write-Host "Step 3: Getting All Interventions..." -ForegroundColor Yellow
$interventionsResponse = Invoke-RestMethod -Uri "$API_BASE/api/interventions" `
  -Method GET `
  -Headers @{ "Authorization" = "Bearer $ADMIN_TOKEN" }

Write-Host "✅ Total interventions: $($interventionsResponse.Count)" -ForegroundColor Green

# Find intervention assigned to this tech OR any intervention for testing
$techIntervention = $interventionsResponse | Where-Object { 
    ($_.technicien -like "*$TECH_NAME*") -or ($_.technicien -like "*Ghazi*") 
} | Select-Object -First 1

$testIntervention = if ($techIntervention) { $techIntervention } else { $interventionsResponse | Select-Object -First 1 }

if ($testIntervention) {
    $INTERVENTION_ID = $testIntervention.id
    Write-Host "   Test Intervention #$INTERVENTION_ID" -ForegroundColor Green
    Write-Host "   Machine: $($testIntervention.machine)" -ForegroundColor Gray
    Write-Host "   Technicien: $($testIntervention.technicien)" -ForegroundColor Gray
    Write-Host "   Statut: $($testIntervention.statut)" -ForegroundColor Gray
    Write-Host "   is_temporary: $($testIntervention.is_temporary)" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host "❌ No interventions found" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Testing New Endpoints" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Test 1: GET /my-form
Write-Host "Test 1: GET /my-form" -ForegroundColor Yellow
Write-Host "  URL: /api/interventions/$INTERVENTION_ID/my-form" -ForegroundColor Gray
try {
    $formResponse = Invoke-RestMethod -Uri "$API_BASE/api/interventions/$INTERVENTION_ID/my-form" `
        -Method GET `
        -Headers @{ "Authorization" = "Bearer $TECH_TOKEN" }
    
    Write-Host "✅ SUCCESS" -ForegroundColor Green
    Write-Host "   Response:" -ForegroundColor Green
    Write-Host "   - Statut: $($formResponse.statut)" -ForegroundColor Green
    Write-Host "   - Durée: $($formResponse.duree_minutes) min" -ForegroundColor Green
    Write-Host "   - Déplacement: $($formResponse.deplacement)€" -ForegroundColor Green
    Write-Host "   - Machine: $($formResponse.parent_machine)" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ ERROR" -ForegroundColor Red
    Write-Host "   $($_.Exception.Response.StatusCode): $($_.ErrorDetails.Message)" -ForegroundColor Red
    Write-Host ""
}

# Test 2: POST /save-my-work
Write-Host "Test 2: POST /save-my-work" -ForegroundColor Yellow
Write-Host "  URL: /api/interventions/$INTERVENTION_ID/save-my-work" -ForegroundColor Gray
$saveData = @{
    duree_minutes = 120
    deplacement = 50
    probleme_tech = "Test problème"
    cause_tech = "Test cause"
    solution = "Test solution"
    pieces_changees = "Test pièces"
    observations = "Test observations"
}

try {
    $saveResponse = Invoke-RestMethod -Uri "$API_BASE/api/interventions/$INTERVENTION_ID/save-my-work" `
        -Method POST `
        -Headers @{ "Authorization" = "Bearer $TECH_TOKEN"; "Content-Type" = "application/json" } `
        -Body (ConvertTo-Json $saveData)
    
    Write-Host "✅ SUCCESS" -ForegroundColor Green
    Write-Host "   Message: $($saveResponse.message)" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ ERROR" -ForegroundColor Red
    Write-Host "   $($_.Exception.Response.StatusCode): $($_.ErrorDetails.Message)" -ForegroundColor Red
    Write-Host ""
}

# Test 3: Verify saved data
Write-Host "Test 3: Verify Saved Data" -ForegroundColor Yellow
try {
    $verifyResponse = Invoke-RestMethod -Uri "$API_BASE/api/interventions/$INTERVENTION_ID/my-form" `
        -Method GET `
        -Headers @{ "Authorization" = "Bearer $TECH_TOKEN" }
    
    Write-Host "✅ Data persisted correctly" -ForegroundColor Green
    Write-Host "   - Durée: $($verifyResponse.duree_minutes) min" -ForegroundColor Green
    Write-Host "   - Déplacement: $($verifyResponse.deplacement)€" -ForegroundColor Green
    Write-Host "   - Solution: $($verifyResponse.solution)" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "❌ ERROR" -ForegroundColor Red
    Write-Host "   $($_.Exception.Response.StatusCode)" -ForegroundColor Red
    Write-Host ""
}

# Test 4: POST /close-my-work
Write-Host "Test 4: POST /close-my-work" -ForegroundColor Yellow
Write-Host "  URL: /api/interventions/$INTERVENTION_ID/close-my-work" -ForegroundColor Gray
$closeData = @{
    duree_minutes = 120
    deplacement = 50
    probleme_tech = "Test problème"
    cause_tech = "Test cause"
    solution = "Test solution appliquée"
    pieces_changees = "Test pièces"
    observations = "Travail complété"
}

try {
    $closeResponse = Invoke-RestMethod -Uri "$API_BASE/api/interventions/$INTERVENTION_ID/close-my-work" `
        -Method POST `
        -Headers @{ "Authorization" = "Bearer $TECH_TOKEN"; "Content-Type" = "application/json" } `
        -Body (ConvertTo-Json $closeData)
    
    Write-Host "✅ SUCCESS" -ForegroundColor Green
    Write-Host "   Parent Status: $($closeResponse.parent_status)" -ForegroundColor Green
    Write-Host "   Message: $($closeResponse.message)" -ForegroundColor Green
    
    if ($closeResponse.pending_technicians) {
        Write-Host "   Pending: $($closeResponse.pending_technicians -join ', ')" -ForegroundColor Yellow
    }
    if ($closeResponse.aggregated_data) {
        Write-Host "   ✅ ALL COMPLETED!" -ForegroundColor Green
        Write-Host "   Total Duration: $($closeResponse.aggregated_data.total_duree_minutes) min" -ForegroundColor Green
    }
    Write-Host ""
} catch {
    Write-Host "❌ ERROR" -ForegroundColor Red
    $errorDetail = $_.ErrorDetails.Message | ConvertFrom-Json
    Write-Host "   $($_.Exception.Response.StatusCode): $($errorDetail.detail)" -ForegroundColor Red
    Write-Host ""
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "✅ Endpoint Testing Complete" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
