# 🔧 Post-Install Debug Checklist

Run through this after the wizard completes to verify everything works.

## 1. OpenClaw Running?
- [ ] `openclaw status` → should show "running"
- [ ] `openclaw gateway status` → gateway active

## 2. Config Valid?
- [ ] `cat ~/.openclaw/openclaw.json` → valid JSON, your model choices present
- [ ] `cat ~/.openclaw/agents/main/agent/auth-profiles.json` → API keys present (redacted)
- [ ] `cat ~/.openclaw/agents/main/agent/AGENTS.md` → Cortex personality configured

## 3. Cortex Responding?
- [ ] Send "hello" on your messaging platform → Cortex replies
- [ ] Verbose mode should be ON by default — you'll see agent activity indicators
- [ ] Ask "what's 2+2?" → Cortex handles directly (no delegation needed)

## 4. Delegation Working?
- [ ] Ask "research the latest Python 3.13 features" → Researcher activates (visible in verbose mode)
- [ ] `/idea build a hello world REST API` → idea added to backlog
- [ ] Ask about something technical in your configured tech stack → should reference your stack

## 5. Memory Working?
- [ ] Tell Cortex "my favorite language is Python"
- [ ] Wait a minute, then ask "what's my favorite language?" → should remember
- [ ] Check memory DB exists: `ls ~/MemoryEnhancedMultiAgent/data/`

## 6. Project Pipeline?
- [ ] `/ideas` → shows your idea backlog
- [ ] Promote an idea → spec generation kicks off (Researcher + Cortex)
- [ ] Watch verbose output for Researcher→Builder→Verifier→Guardian chain

## 7. Guardian Working?
- [ ] Check verbose output for Guardian activity during any build task
- [ ] Guardian should scan for credentials and check conventions

## 8. Crons Registered?
- [ ] `crontab -l` → should show:
  - Health check (every 30 min)
  - Memory backup (daily)
  - Log rotation (weekly)
  - Morning brief (daily at your configured time)
  - Idea surfacing (weekly Monday)

## 9. Morning Brief?
- [ ] Wait for scheduled time OR manually trigger: `python3 ~/MemoryEnhancedMultiAgent/scripts/morning_brief.py`
- [ ] Check your messaging platform for the digest

## 🚨 Common Issues

### Cortex doesn't respond
1. Check OpenClaw is running: `openclaw status`
2. Check logs: `openclaw gateway logs`
3. Verify API key works: check auth-profiles.json

### "Model not found" errors
1. Verify model IDs in openclaw.json match your provider
2. Check API key has access to the model tier you selected

### Memory not persisting
1. Check SQLite DB exists in data/
2. Check disk space: `df -h`
3. Check logs for memory engine errors

### Crons not running
1. Check crontab: `crontab -l`
2. Check cron service: `systemctl status cron`
3. Check script permissions: `ls -la ~/MemoryEnhancedMultiAgent/scripts/`
