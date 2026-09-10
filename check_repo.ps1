$token = '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'
$url = 'https://api.github.com/repos/cjxbgu-wq/-xiagaoyige'
$result = Invoke-RestMethod -Uri $url -Headers @{Authorization = "token $token"}
Write-Host "Repo name: $($result.name)"
Write-Host "Repo exists: Yes"