#!/usr/bin/env bash
# Log rotation with metrics harvesting — runs weekly via cron
set -euo pipefail

WORKSPACE="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="$WORKSPACE/data"
METRICS_FILE="$DATA_DIR/metrics.json"
TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
PERIOD_END="$(date -u '+%Y-%m-%d')"

log() { echo "$TIMESTAMP [rotate] $1"; }

# Initialize metrics file if missing
if [ ! -f "$METRICS_FILE" ]; then
    echo '[]' > "$METRICS_FILE"
fi

# --- Harvest from consolidation.log ---
CONSOL_LOG="$DATA_DIR/consolidation.log"
CONSOLIDATIONS=0
MEMORIES_CONSOLIDATED=0
MEMORIES_PRUNED=0

if [ -f "$CONSOL_LOG" ]; then
    CONSOLIDATIONS=$(grep -c "Consolidation complete" "$CONSOL_LOG" 2>/dev/null || echo 0)
    MEMORIES_CONSOLIDATED=$(grep -oP 'consolidated=\K[0-9]+' "$CONSOL_LOG" 2>/dev/null | awk '{s+=$1}END{print s+0}')
    MEMORIES_PRUNED=$(grep -oP 'pruned=\K[0-9]+' "$CONSOL_LOG" 2>/dev/null | awk '{s+=$1}END{print s+0}')
fi

# --- Harvest from health.log ---
HEALTH_LOG="$DATA_DIR/health.log"
TOTAL_CHECKS=0
HEALTHY_CHECKS=0
RESTARTS=0
UPTIME_PCT=100.0

if [ -f "$HEALTH_LOG" ]; then
    TOTAL_CHECKS=$(grep -c '\[health\]' "$HEALTH_LOG" 2>/dev/null || echo 0)
    HEALTHY_CHECKS=$(grep -c '\[health\] OK' "$HEALTH_LOG" 2>/dev/null || echo 0)
    RESTARTS=$(grep -c 'restart' "$HEALTH_LOG" 2>/dev/null || echo 0)
    if [ "$TOTAL_CHECKS" -gt 0 ]; then
        UPTIME_PCT=$(python3 -c "print(round($HEALTHY_CHECKS / $TOTAL_CHECKS * 100, 1))" 2>/dev/null || echo "100.0")
    fi
fi

# --- Harvest usage from usage.db ---
USAGE_TOKENS=0
USAGE_COST="0.0"
USAGE_CALLS=0
USAGE_TOP_MODEL=""
USAGE_PER_AGENT="{}"

if [ -f "$DATA_DIR/usage.db" ]; then
    eval "$(python3 -c "
import sqlite3, json
conn = sqlite3.connect('$DATA_DIR/usage.db')
conn.row_factory = sqlite3.Row
row = conn.execute('SELECT COUNT(*) as calls, COALESCE(SUM(total_tokens),0) as tokens, COALESCE(SUM(cost_estimate),0) as cost FROM api_calls WHERE date(timestamp) >= date(\"now\",\"-7 days\")').fetchone()
print(f'USAGE_CALLS={row[\"calls\"]}')
print(f'USAGE_TOKENS={row[\"tokens\"]}')
print(f'USAGE_COST={row[\"cost\"]}')
top = conn.execute('SELECT model, SUM(cost_estimate) as c FROM api_calls WHERE date(timestamp) >= date(\"now\",\"-7 days\") GROUP BY model ORDER BY c DESC LIMIT 1').fetchone()
if top: print(f'USAGE_TOP_MODEL=\"{top[\"model\"]}\"')
agents = conn.execute('SELECT agent, COUNT(*) as calls FROM api_calls WHERE date(timestamp) >= date(\"now\",\"-7 days\") GROUP BY agent').fetchall()
pa = {r['agent']: r['calls'] for r in agents}
print(f'USAGE_PER_AGENT={json.dumps(pa)}')
conn.close()
" 2>/dev/null)" || true
fi

# --- Append metrics entry ---
python3 -c "
import json, sys
metrics_file = '$METRICS_FILE'
entry = {
    'period_end': '$PERIOD_END',
    'consolidations': $CONSOLIDATIONS,
    'memories_consolidated': $MEMORIES_CONSOLIDATED,
    'memories_pruned': $MEMORIES_PRUNED,
    'uptime_pct': $UPTIME_PCT,
    'restarts': $RESTARTS,
    'usage_calls': $USAGE_CALLS,
    'usage_tokens': $USAGE_TOKENS,
    'usage_cost': $USAGE_COST,
    'usage_top_model': '$USAGE_TOP_MODEL',
    'usage_per_agent': $USAGE_PER_AGENT,
}
try:
    with open(metrics_file) as f:
        data = json.load(f)
except (json.JSONDecodeError, FileNotFoundError):
    data = []
data.append(entry)
with open(metrics_file, 'w') as f:
    json.dump(data, f, indent=2)
print(f'Metrics appended: {json.dumps(entry)}')
"

log "Metrics harvested for period ending $PERIOD_END"

# --- Trim logs to last 1000 lines ---
for logfile in "$CONSOL_LOG" "$HEALTH_LOG" "$DATA_DIR/backup.log" "$DATA_DIR/rotation.log"; do
    if [ -f "$logfile" ]; then
        LINES=$(wc -l < "$logfile")
        if [ "$LINES" -gt 1000 ]; then
            tail -1000 "$logfile" > "${logfile}.tmp" && mv "${logfile}.tmp" "$logfile"
            log "Trimmed $(basename "$logfile") from $LINES to 1000 lines"
        fi
    fi
done

log "Log rotation complete"
