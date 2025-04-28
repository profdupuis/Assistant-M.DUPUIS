# Aller dans le bon dossier (où sont les fichiers à vérifier)
Set-Location -Path "C:\chemin\vers\export\audit_reports"  # <-- adapte ce chemin !

# Vérifier tous les .sha256 du dossier
Get-ChildItem *.sha256 | ForEach-Object {
    $shaFile = $_.FullName
    $txtFile = ($_.BaseName)

    if (Test-Path $txtFile) {
        Write-Output "🔍 Vérification de : $txtFile"

        $expectedHash = (Get-Content $shaFile).Split(" ")[0]
        $actualHash = (Get-FileHash $txtFile -Algorithm SHA256).Hash

        if ($expectedHash -eq $actualHash) {
            Write-Host "✅ OK : Intégrité vérifiée" -ForegroundColor Green
        } else {
            Write-Host "❌ ERREUR : Intégrité compromise" -ForegroundColor Red
        }
    } else {
        Write-Host "⚠️ Fichier $txtFile introuvable !" -ForegroundColor Yellow
    }
}
