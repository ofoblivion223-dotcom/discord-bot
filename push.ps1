Set-Location "c:\Users\owner\.gemini\antigravity\playground\axial-void\repo_new"
git config user.email "ai-assistant@example.com"
git config user.name "AI Assistant"
git add bot_main.py
git commit -m "Add post-confirmation reminders: day-before at 21:00, day-of at 20:00"
Write-Host "COMMIT_DONE"
git push origin main
Write-Host "PUSH_DONE"
git log --oneline -3
