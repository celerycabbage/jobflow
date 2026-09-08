param(
    [string]$Email = $env:JOBFLOW_SMOKE_EMAIL,
    [string]$Password = $env:JOBFLOW_SMOKE_PASSWORD
)

if ([string]::IsNullOrWhiteSpace($Email) -or [string]::IsNullOrWhiteSpace($Password)) {
    throw "Pass -Email and -Password, or set JOBFLOW_SMOKE_EMAIL and JOBFLOW_SMOKE_PASSWORD."
}

$health = Invoke-RestMethod -Uri "http://localhost:8000/health"
if ($health.status -ne "ok") { throw "API health check failed" }
$body = @{ email = $Email; password = $Password } | ConvertTo-Json
$token = (Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/v1/auth/login" -ContentType "application/json" -Body $body).access_token
$headers = @{ Authorization = "Bearer $token" }
$applications = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/applications" -Headers $headers
$insights = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/dashboard/insights" -Headers $headers
Write-Host "Smoke test passed: $($applications.Count) applications, offer rate $($insights.offer_rate)%"
