$ErrorActionPreference = 'Stop'
$backend = Join-Path $PSScriptRoot 'backend'
$envFile = Join-Path $backend '.env'
$example = Join-Path $backend '.env.example'

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python was not found. Install Python 3.11+ and reopen PowerShell.'
}

if (-not (Test-Path $envFile)) {
    Copy-Item $example $envFile
}

$content = Get-Content $envFile -Raw

if ($content -match '(?m)^JWT_SECRET=(REPLACE_WITH_RANDOM_SECRET_AT_LEAST_32_CHARACTERS|CHANGE_ME)?[ \t\r]*$') {
    $jwt = python -c "import secrets; print(secrets.token_urlsafe(48))"
    $content = [regex]::Replace($content, '(?m)^JWT_SECRET=.*$', "JWT_SECRET=$jwt")
}

if ($content -match '(?m)^FERNET_KEY=(REPLACE_WITH_GENERATED_FERNET_KEY|GENERATE_FERNET_KEY)?[ \t\r]*$') {
    # Fernet keys are URL-safe base64 encodings of 32 random bytes.
    $fernet = python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
    $content = [regex]::Replace($content, '(?m)^FERNET_KEY=.*$', "FERNET_KEY=$fernet")
}

if ($content -match '(?m)^ADMIN_PASSWORD=(REPLACE_WITH_YOUR_OWN_STRONG_PASSWORD|CHANGE_ME)[ \t\r]*$') {
    $secure = Read-Host 'Create your admin password (12+ characters)' -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ($plain.Length -lt 12 -or [Text.Encoding]::UTF8.GetByteCount($plain) -gt 72) {
        throw 'Password must be at least 12 characters and no more than 72 UTF-8 bytes.'
    }
    $quoted = ConvertTo-Json -InputObject $plain -Compress
    $content = [regex]::Replace($content, '(?m)^ADMIN_PASSWORD=.*$', "ADMIN_PASSWORD=$quoted")
}

[System.IO.File]::WriteAllText($envFile, $content, (New-Object System.Text.UTF8Encoding($false)))
Write-Host 'Backend .env configured. Keep it private; never upload or share it.' -ForegroundColor Green
Write-Host 'Next commands:' -ForegroundColor Cyan
Write-Host '  cd backend'
Write-Host '  py -3.11 -m venv .venv'
Write-Host '  .\.venv\Scripts\Activate.ps1'
Write-Host '  python -m pip install --upgrade pip'
Write-Host '  pip install -r requirements.txt'
