param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$FilePath
)

$ErrorActionPreference = 'Stop'
$fullPath = [System.IO.Path]::GetFullPath($FilePath)

if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) {
    throw "Arquivo para assinar nao encontrado: $fullPath"
}

foreach ($name in @('PDV_SIGNTOOL','PDV_DLIB','PDV_METADATA')) {
    $value = [Environment]::GetEnvironmentVariable($name)
    if ([string]::IsNullOrWhiteSpace($value) -or -not (Test-Path -LiteralPath $value -PathType Leaf)) {
        throw "Ferramenta de assinatura nao configurada: $name"
    }
}

# A identidade e' validada pelo servico Microsoft Artifact Signing.
# Nao usa certificado autoassinado nem desativa protecoes do Windows.
& $env:PDV_SIGNTOOL sign /fd SHA256 /tr 'http://timestamp.acs.microsoft.com/' /td SHA256 /dlib $env:PDV_DLIB /dmdf $env:PDV_METADATA $fullPath
if ($LASTEXITCODE -ne 0) {
    throw "Falha ao assinar: $fullPath"
}

& $env:PDV_SIGNTOOL verify /pa $fullPath
if ($LASTEXITCODE -ne 0) {
    throw "SignTool nao conseguiu validar a assinatura: $fullPath"
}

$signature = Get-AuthenticodeSignature -LiteralPath $fullPath
if ($signature.Status -ne 'Valid') {
    throw "Assinatura nao e' confiavel no runner: $fullPath ($($signature.Status))"
}
Write-Host "Assinatura verificada: $fullPath"
