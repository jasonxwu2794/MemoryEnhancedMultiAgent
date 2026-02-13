#!/usr/bin/env bash
# ============================================================================
# Step 6: Model Selection
# Per-agent model selection with cost estimates.
# ============================================================================

wizard_header "6" "Model Selection" "Choose which AI model powers each agent."

# --- Model definitions ---
MODELS=(
    "Claude Opus 4.6|claude-opus-4-6|anthropic|~\$40-80/mo|██████████|💰💰💰 Best brain money can buy"
    "Claude Sonnet 4.5|claude-sonnet-4-5|anthropic|~\$15-30/mo|████████░░|Save ~40% vs Opus"
    "DeepSeek V3.2 Reasoner|deepseek-reasoner|deepseek|~\$2-8/mo|██████░░░░|🏆 Best coding value (74% Aider)"
    "DeepSeek V3.2 Chat|deepseek-chat|deepseek|~\$1-5/mo|████░░░░░░|Fast + cheap, no thinking"
    "Gemini 3 Pro|gemini-3-pro-preview|google|~\$15-40/mo|█████████░|🔥 #3 Arena coding, premium"
    "Gemini 2.5 Pro|gemini-2.5-pro|google|~\$10-30/mo|████████░░|83% Aider, 1M context"
    "Qwen3 Max|qwen-max|alibaba|~\$5-15/mo|██████░░░░|Complex tasks, 262K context"
    "Qwen3 Plus|qwen-plus|alibaba|~\$2-6/mo|████░░░░░░|1M context, never recharge 😂"
    "Kimi K2.5|kimi-k2.5|moonshot|~\$3-10/mo|██████░░░░|#4 Arena coding, multimodal"
)

# --- Agents to configure ---
declare -A AGENT_LABELS=(
    [brain]="🧠 Cortex (Orchestrator, user-facing)"
    [builder]="🔨 Builder (Code generation)"
    [researcher]="🔬 Researcher (Research, synthesis)"
    [verifier]="✅ Verifier (Fact verification)"
    [guardian]="🛡️ Guardian (Security review)"
)

# --- Recommended defaults ---
declare -A DEFAULTS=(
    [brain]="Claude Opus 4.6"
    [builder]="DeepSeek V3.2 Reasoner"
    [researcher]="Qwen3 Plus"
    [verifier]="Claude Opus 4.6"
    [guardian]="DeepSeek V3.2 Chat"
)

AGENT_ORDER=(brain builder researcher verifier guardian)

# Build display names for gum choose
MODEL_NAMES=()
for m in "${MODELS[@]}"; do
    IFS='|' read -r name slug provider cost bar <<< "$m"
    MODEL_NAMES+=("$name  $cost  $bar")
done

for agent in "${AGENT_ORDER[@]}"; do
    wizard_divider
    gum style --bold --foreground 212 "${AGENT_LABELS[$agent]}"
    echo ""

    # Get previous/default selection
    PREV="$(state_get "models.$agent" '')"
    if [ -z "$PREV" ] && is_recommended; then
        PREV="${DEFAULTS[$agent]}"
    fi

    # Build --selected flag if we have a previous/default
    SELECTED_FLAG=()
    if [ -n "$PREV" ]; then
        for entry in "${MODEL_NAMES[@]}"; do
            if [[ "$entry" == "$PREV"* ]]; then
                SELECTED_FLAG=(--selected "$entry")
                break
            fi
        done
    fi

    # Show cost table and let user choose
    CHOICE="$(gum choose --header "Select model:" "${SELECTED_FLAG[@]}" "${MODEL_NAMES[@]}")"

    # Extract model slug from choice
    CHOSEN_NAME="$(echo "$CHOICE" | sed 's/  .*//')"
    CHOSEN_SLUG=""
    CHOSEN_PROVIDER=""
    for m in "${MODELS[@]}"; do
        IFS='|' read -r name slug provider cost bar <<< "$m"
        if [ "$name" = "$CHOSEN_NAME" ]; then
            CHOSEN_SLUG="$slug"
            CHOSEN_PROVIDER="$provider"
            break
        fi
    done

    state_set "models.$agent" "$CHOSEN_SLUG"
    state_set "providers.$agent" "$CHOSEN_PROVIDER"
    log_ok "$agent → $CHOSEN_NAME ($CHOSEN_SLUG)"
done

wizard_divider
wizard_success "Model selection complete!"
