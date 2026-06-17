$API = "http://localhost:8001"

function req {
    param([string]$Path, [string]$Method, [string]$Token, [object]$Body)
    $h = @{"Authorization"="Bearer $Token";"Content-Type"="application/json"}
    if ($Method -eq "GET") {
        return Invoke-RestMethod -Uri "$API$Path" -Method GET -Headers $h
    }
    return Invoke-RestMethod -Uri "$API$Path" -Method $Method -Headers $h -Body (ConvertTo-Json $Body)
}

Write-Host "=== MULTI-TECH INTERVENTION TEST ===" -ForegroundColor White
Write-Host ""

Write-Host "1. Login as Admin..." -ForegroundColor Yellow
$admin = Invoke-RestMethod -Uri "$API/api/auth/login" -Method POST -Headers @{"Content-Type"="application/json"} -Body '{"username":"admin","password":"admin"}'
$adminTok = $admin.token
Write-Host "   OK" -ForegroundColor Green

Write-Host "2. Find Intervention..." -ForegroundColor Yellow
$ints = req "/api/interventions" "GET" $adminTok @{}
$int = $ints[-1]
$intId = $int.id
Write-Host "   Intervention #$intId" -ForegroundColor Green

Write-Host "3. Get Tech Tokens..." -ForegroundColor Yellow
$techs = @()
foreach ($t in @("ghazi","hamdi","mahdi")) {
    $pass = "$t`123"
    $res = Invoke-RestMethod -Uri "$API/api/auth/login" -Method POST -Headers @{"Content-Type"="application/json"} -Body (ConvertTo-Json @{username=$t; password=$pass})
    $techs += @{name=$t; token=$res.token}
    Write-Host "   Token for $t" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== ACCEPT PHASE ===" -ForegroundColor White
foreach ($t in $techs) {
    Write-Host "$($t.name): Accepting..." -ForegroundColor Yellow
    $res = req "/api/interventions/$intId/accept" "PUT" $t.token @{}
    Write-Host "   Status: $($res.statut)" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== LOAD & SAVE PHASE ===" -ForegroundColor White
$workData = @(
    @{duree_minutes=120; deplacement=50; probleme_tech="Problem1"; cause_tech="Cause1"; solution="Solution1"; pieces_changees="Parts1"; observations="Work by Ghazi"},
    @{duree_minutes=90; deplacement=30; probleme_tech="Problem2"; cause_tech="Cause2"; solution="Solution2"; pieces_changees="Parts2"; observations="Work by Hamdi"},
    @{duree_minutes=150; deplacement=60; probleme_tech="Problem3"; cause_tech="Cause3"; solution="Solution3"; pieces_changees="Parts3"; observations="Work by Mahdi"}
)

$i = 0
foreach ($t in $techs) {
    Write-Host "$($t.name): Loading form..." -ForegroundColor Yellow
    $form = req "/api/interventions/$intId/my-form" "GET" $t.token
    Write-Host "   Form status: $($form.statut)" -ForegroundColor Green
    
    Write-Host "$($t.name): Saving work..." -ForegroundColor Yellow
    $save = req "/api/interventions/$intId/save-my-work" "POST" $t.token $workData[$i]
    Write-Host "   Message: $($save.message)" -ForegroundColor Green
    $i++
}

Write-Host ""
Write-Host "=== CLOSE PHASE ===" -ForegroundColor White
$i = 0
foreach ($t in $techs) {
    Write-Host "$($t.name): Closing work..." -ForegroundColor Yellow
    $close = req "/api/interventions/$intId/close-my-work" "POST" $t.token $workData[$i]
    Write-Host "   Parent Status: $($close.parent_status)" -ForegroundColor Green
    
    if ($close.aggregated_data) {
        Write-Host "   ALL DONE! Total: $($close.aggregated_data.total_duree_minutes)min" -ForegroundColor Cyan
    } else {
        Write-Host "   Pending: $($close.pending_technicians -join ', ')" -ForegroundColor Yellow
    }
    $i++
}

Write-Host ""
Write-Host "=== TEST COMPLETE ===" -ForegroundColor White
