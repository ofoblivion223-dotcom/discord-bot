Set-Location "c:\Users\owner\.gemini\antigravity\playground\axial-void\repo_new"
git config user.email "ai-assistant@example.com"
git config user.name "AI Assistant"
git add state.json
git commit -m "Manual fix: set status to confirmed for 02/24(火) to enable reminders"
git pull --rebase origin main
git push origin main 2>&1 | Out-File push_state_log.txt -Encoding utf8
git log --oneline -3
