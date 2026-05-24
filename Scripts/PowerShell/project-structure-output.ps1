# Full project structure + file details saved to a clean file
Get-ChildItem -Path "C:\SLAM-Services-Project" -Recurse -File | 
Select-Object FullName, Length, LastWriteTime, Extension | 
Sort-Object FullName | 
Format-Table -AutoSize | 
Out-File -FilePath "C:\SLAM-Services-Project\Project-Structure-Report.txt" -Encoding UTF8 -Width 500

Write-Host "✅ Project structure saved to: Project-Structure-Report.txt" -ForegroundColor Green