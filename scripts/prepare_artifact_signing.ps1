$ErrorActionPreference = 'Stop'

foreach ($name in @('PDV_AS_ENDPOINT', 'PDV_AS_ACCOUNT', 'PDV_AS_PROFILE', 'GITHUB_ENV', 'RUNNER_TEMP')) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Configuracao ausente: $name. Nenhum instalador sera publicado."
    }
}

$msi = Join-Path $env:RUNNER_TEMP 'ArtifactSigningClientTools.msi'
$uri = 'https://download.microsoft.com/download/70ad2c3b-761f-4aa9-a9de-e7405aa2b4c1/ArtifactSigningClientTools.msi'
Invoke-WebRequest -Uri $uri -OutFile $msi
if (-not (Test-Path -LiteralPath $msi)) { throw 'Falha ao obter ferramenta oficial da Microsoft.' }

$installArgs = '/i "' + $msi + '" /qn /norestart'
$install = Start-Process -FilePath 'msiexec.exe' -ArgumentList $installArgs -Wait -PassThru
if ($install.ExitCode -ne 0 -and $install.ExitCode -ne 3010) {
    throw "Falha ao instalar Artifact Signing Client Tools: $($install.ExitCode)"
}

$sdk = Join-Path ([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')) 'Windows Kits\10\bin'
$signtool = Get-ChildItem -Path $sdk -Filter signtool.exe -File -Recurse -ErrorAction Stop |
    Where-Object { $_.FullName -match '\\x64\\' } |
    Sort-Object FullName -Descending |
    Select-Object -First 1
if (-not $signtool) { throw 'Windows SDK SignTool x64 nao encontrado.' }

$clientRoots = @(
    (Join-Path ([Environment]::GetEnvironmentVariable('ProgramFiles(x86)')) 'Microsoft\ArtifactSigningClientTools'),
    (Join-Path $env:ProgramFiles 'Microsoft\ArtifactSigningClientTools')
)
$dlib = $null
foreach ($root in $clientRoots) {
    if (Test-Path $root) {
        $dlib = Get-ChildItem $root -Recurse -File -Filter 'Azure.CodeSigning.Dlib.dll' |
            Where-Object { $_.FullName -match '\\x64\\' } |
            Select-Object -First 1
        if ($dlib) { break }
    }
}
if (-not $dlib) { throw 'Artifact Signing Dlib x64 nao encontrado.' }

$metadataFile = Join-Path $env:RUNNER_TEMP 'pdv_artifact_signing_metadata.json'
@{
    Endpoint = $env:PDV_AS_ENDPOINT
    CodeSigningAccountName = $env:PDV_AS_ACCOUNT
    CertificateProfileName = $env:PDV_AS_PROFILE
} | ConvertTo-Json -Depth 5 | Set-Content -Path $metadataFile -Encoding UTF8

@(
    "PDV_SIGNTOOL=$($signtool.FullName)"
    "PDV_DLIB=$($dlib.FullName)"
    "PDV_METADATA=$metadataFile"
) | Add-Content -Path $env:GITHUB_ENV -Encoding utf8

Write-Host 'Ferramentas de assinatura da Microsoft localizadas. Nenhuma chave privada foi copiada para o repositorio.'
