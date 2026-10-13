#!/bin/bash

# Read JSON input from stdin
input=$(cat)

# Colors
RESET="\033[0m"
WHITE="\033[97m"
GRAY="\033[90m"
BG_CHECK="\033[48;5;238m"
BG_GREEN="\033[42m"
BG_YELLOW="\033[43m"
BG_RED="\033[41m"
FG_GREEN="\033[32m"
FG_YELLOW="\033[33m"
FG_RED="\033[31m"

# --- Helpers ---

# make_gradient_bar <percentage> <yellow_threshold> <red_threshold> [inner_width=10]
# Renders: [  XX%  ] — filled cells use zone color based on current percentage
make_gradient_bar() {
    local pct=$1
    local yellow=$2
    local red=$3
    local width=${4:-10}
    (( pct < 0 )) && pct=0
    (( pct > 100 )) && pct=100
    local filled=$(( pct * width / 100 ))
    # Zone color: determined by where pct falls, not cell position
    local zone_fg
    if [ "$pct" -ge "$red" ]; then
        zone_fg="$FG_RED"
    elif [ "$pct" -ge "$yellow" ]; then
        zone_fg="$FG_YELLOW"
    else
        zone_fg="$FG_GREEN"
    fi
    local text
    text=$(printf "%d%%" "$pct")
    local tlen=${#text}
    local pad_left=$(( (width - tlen) / 2 ))
    local pad_right=$(( width - tlen - pad_left ))
    local full_inner
    full_inner=$(printf "%${pad_left}s%s%${pad_right}s" "" "$text" "")
    local bar="" i
    for ((i=0; i<width; i++)); do
        local ch="${full_inner:$i:1}"
        if [ "$i" -lt "$filled" ]; then
            if [ "$ch" = " " ]; then
                bar+=$(printf "%b%b▒%b" "$BG_CHECK" "$zone_fg" "$RESET")
            else
                bar+=$(printf "%b%b%s%b" "$BG_CHECK" "$WHITE" "$ch" "$RESET")
            fi
        else
            if [ "$ch" = " " ]; then
                bar+=$(printf "%b%b▒%b" "$BG_CHECK" "\033[38;5;248m" "$RESET")
            else
                bar+=$(printf "%b%b%s%b" "$BG_CHECK" "$WHITE" "$ch" "$RESET")
            fi
        fi
    done
    printf "[%s]" "$bar"
}

# osc8_link <url> <text> → clickable terminal hyperlink
osc8_link() {
    local url="$1"
    local text="$2"
    printf "\033]8;;%s\033\\%s\033]8;;\033\\" "$url" "$text"
}

# file_birth <path> → creation time in epoch seconds: BSD `stat -f %B`, else
# GNU `stat -c %W`. Empty when the filesystem does not record it.
file_birth() {
    local value
    value=$(stat -f %B "$1" 2>/dev/null)
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        value=$(stat -c %W "$1" 2>/dev/null)
    fi
    if [[ "$value" =~ ^[0-9]+$ ]] && [ "$value" -gt 0 ]; then
        printf "%s" "$value"
    fi
}

# epoch_format <seconds> <format> → BSD `date -r`, else GNU `date -d @seconds`
epoch_format() {
    date -r "$1" "+$2" 2>/dev/null || date -d "@$1" "+$2" 2>/dev/null
}

# --- Data extraction ---

# Model name: strip common provider prefixes from display labels
model_raw=$(echo "$input" | jq -r '.model.display_name // empty')
model_name=$(echo "$model_raw" | sed -E 's/^([Cc]laude|OpenAI) //')

# Effort level: the live session value (tracks /effort and --effort); absent
# when the model has no effort parameter. settings.json holds only the saved
# default, so it is never consulted.
effort_str=""
effort=$(echo "$input" | jq -r '.effort.level // empty')
if [ -n "$effort" ]; then
    case "$effort" in
        max)        effort_str=$(printf "%b%s%b" "$FG_RED"    "$effort" "$RESET") ;;
        high|xhigh) effort_str=$(printf "%b%s%b" "$FG_YELLOW" "$effort" "$RESET") ;;
        *)          effort_str=$(printf "%b%s%b" "$GRAY"      "$effort" "$RESET") ;;
    esac
fi

# Message count + session duration
msg_str=""
duration_str=""
transcript=$(echo "$input" | jq -r '.transcript_path // empty')
if [ -n "$transcript" ] && [ -f "$transcript" ]; then
    msg_count=$(wc -l < "$transcript" 2>/dev/null | tr -d ' ')
    if [ -n "$msg_count" ] && [ "$msg_count" -gt 0 ]; then
        if [ "$msg_count" -ge 100 ]; then
            msg_color="$FG_RED"
        elif [ "$msg_count" -ge 50 ]; then
            msg_color="$FG_YELLOW"
        else
            msg_color="$FG_GREEN"
        fi
        msg_str=$(printf "%b%d msgs%b" "$msg_color" "$msg_count" "$RESET")
    fi

    # Session duration from the transcript file's birth time
    birth=$(file_birth "$transcript")
    if [ -n "$birth" ]; then
        now=$(date +%s)
        elapsed=$(( now - birth ))
        minutes=$(( elapsed / 60 ))
        if [ "$minutes" -ge 60 ]; then
            hours=$(( minutes / 60 ))
            mins=$(( minutes % 60 ))
            duration_str=$(printf "session: %dh%02dm" "$hours" "$mins")
        else
            duration_str=$(printf "session: %dm" "$minutes")
        fi
    fi
fi

# Session cost
cost_str=""
cost_usd=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')
if [ -n "$cost_usd" ]; then
    cost_cents=$(printf "%.0f" "$(echo "$cost_usd * 100" | bc 2>/dev/null || echo 0)")
    if [ "$cost_cents" -ge 800 ]; then
        cost_color="$FG_RED"
    elif [ "$cost_cents" -ge 300 ]; then
        cost_color="$FG_YELLOW"
    else
        cost_color="$FG_GREEN"
    fi
    cost_str=$(printf "cost %b\$%.2f%b" "$cost_color" "$cost_usd" "$RESET")
fi

# Current directory (condensed, fish-style)
cwd=$(echo "$input" | jq -r '.workspace.current_dir')
cwd_display=$(echo "$cwd" | sed "s|^$HOME|~|")
component_count=$(echo "$cwd_display" | tr '/' '\n' | grep -c .)
if [ "$component_count" -gt 4 ]; then
    cwd_display="~/…/$(basename "$cwd")"
fi

# Git info
branch=""
repo_name=""
github_base=""
total_changes=0

if git -C "$cwd" rev-parse --git-dir > /dev/null 2>&1; then
    branch=$(git -C "$cwd" symbolic-ref --short HEAD 2>/dev/null || git -C "$cwd" rev-parse --short HEAD 2>/dev/null)

    # Repo name: walk up to the real repo root via git-common-dir (handles worktrees correctly)
    git_common=$(git -C "$cwd" rev-parse --git-common-dir 2>/dev/null)
    if [ -n "$git_common" ]; then
        repo_root=$(cd "$git_common/.." 2>/dev/null && pwd)
        repo_name=$(basename "$repo_root")
    else
        repo_name=$(basename "$cwd")
    fi

    # GitHub remote URL for OSC 8 links
    remote_url=$(git -C "$cwd" remote get-url origin 2>/dev/null)
    if [ -n "$remote_url" ]; then
        remote_clean="${remote_url%.git}"
        if [[ "$remote_clean" =~ ^git@([^:]+):(.+)$ ]]; then
            github_base="https://${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
        elif [[ "$remote_clean" =~ ^https?:// ]]; then
            github_base="$remote_clean"
        fi
    fi

    # Git dirty indicator: staged + unstaged + untracked
    staged=$(git -C "$cwd" diff --cached --name-only 2>/dev/null | wc -l | tr -d ' ')
    unstaged=$(git -C "$cwd" diff --name-only 2>/dev/null | wc -l | tr -d ' ')
    untracked=$(git -C "$cwd" ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')
    total_changes=$(( staged + unstaged + untracked ))
fi

# Context used percentage and absolute token count
ctx_pct=""
ctx_tokens_display=""
remaining=$(echo "$input" | jq -r '.context_window.remaining_percentage // empty')
ctx_size=$(echo "$input" | jq -r '.context_window.context_window_size // empty')
if [ -n "$remaining" ]; then
    remaining_int=$(printf "%.0f" "$remaining")
    ctx_pct=$((100 - remaining_int))
    if [ -n "$ctx_size" ] && [ "$ctx_size" -gt 0 ]; then
        ctx_tokens=$(awk "BEGIN{printf \"%.0f\", $ctx_pct * $ctx_size / 100}")
        if [ "$ctx_tokens" -ge 1000 ]; then
            ctx_tokens_display=$(awk "BEGIN{printf \"%.0fk\", $ctx_tokens/1000}")
        else
            ctx_tokens_display="${ctx_tokens}"
        fi
    fi
fi

# Rate limits + reset times
five_hr_pct=""
five_hr_reset_str=""
five_hr=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
five_hr_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
if [ -n "$five_hr" ]; then
    five_hr_pct=$(printf "%.0f" "$five_hr")
fi
if [ -n "$five_hr_reset" ]; then
    five_hr_reset_str=$(epoch_format "$five_hr_reset" "%-I%p" | tr '[:upper:]' '[:lower:]')
fi

seven_day_pct=""
seven_day_reset_str=""
seven_day=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
seven_day_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')
if [ -n "$seven_day" ]; then
    seven_day_pct=$(printf "%.0f" "$seven_day")
fi
if [ -n "$seven_day_reset" ]; then
    now_ts=$(date +%s)
    delta=$(( seven_day_reset - now_ts ))
    if [ "$delta" -lt 0 ]; then delta=0; fi
    if [ "$delta" -ge 86400 ]; then
        d=$(( delta / 86400 ))
        h=$(( (delta % 86400) / 3600 ))
        seven_day_reset_str=$(printf "in %dd %dh" "$d" "$h")
    elif [ "$delta" -ge 3600 ]; then
        h=$(( delta / 3600 ))
        m=$(( (delta % 3600) / 60 ))
        seven_day_reset_str=$(printf "in %dh %dm" "$h" "$m")
    else
        m=$(( delta / 60 ))
        seven_day_reset_str=$(printf "in %dm" "$m")
    fi
fi

# --- Line 1: model effort | session dur | msgs | cost | time | diff ---
line1_parts=()

# Model + effort
if [ -n "$model_name" ] && [ -n "$effort_str" ]; then
    line1_parts+=("$(printf "%s %s" "$model_name" "$effort_str")")
elif [ -n "$model_name" ]; then
    line1_parts+=("$model_name")
fi

# Session duration
[ -n "$duration_str" ] && line1_parts+=("$duration_str")

# Message count
[ -n "$msg_str" ] && line1_parts+=("$msg_str")

# Cost
[ -n "$cost_str" ] && line1_parts+=("$cost_str")

# Git diff count
if [ "$total_changes" -gt 0 ]; then
    line1_parts+=("$(printf "%bdiff +%d%b" "$FG_YELLOW" "$total_changes" "$RESET")")
fi

line1=""
for part in "${line1_parts[@]}"; do
    if [ -z "$line1" ]; then
        line1="$part"
    else
        line1="${line1} | ${part}"
    fi
done

# --- Line 2: resource bars — context, 5h, weekly ---
BAR_WIDTH=10
line2_parts=()

if [ -n "$ctx_pct" ]; then
    bar=$(make_gradient_bar "$ctx_pct" 15 25 "$BAR_WIDTH")
    if [ -n "$ctx_tokens_display" ]; then
        line2_parts+=("context $bar $ctx_tokens_display")
    else
        line2_parts+=("context $bar")
    fi
fi

if [ -n "$five_hr_pct" ]; then
    bar=$(make_gradient_bar "$five_hr_pct" 70 90 "$BAR_WIDTH")
    if [ -n "$five_hr_reset_str" ]; then
        line2_parts+=("5h $bar · resets $five_hr_reset_str")
    else
        line2_parts+=("5h $bar")
    fi
fi

if [ -n "$seven_day_pct" ]; then
    bar=$(make_gradient_bar "$seven_day_pct" 70 90 "$BAR_WIDTH")
    if [ -n "$seven_day_reset_str" ]; then
        line2_parts+=("weekly $bar · resets $seven_day_reset_str")
    else
        line2_parts+=("weekly $bar")
    fi
fi

line2=""
for part in "${line2_parts[@]}"; do
    if [ -z "$line2" ]; then
        line2="$part"
    else
        line2="${line2} | ${part}"
    fi
done

# --- Line 3: directory | branch | repo ---
line3_parts=()

# Directory
[ -n "$cwd_display" ] && line3_parts+=("directory $cwd_display")

# Branch with optional OSC 8 link
if [ -n "$branch" ]; then
    if [ -n "$github_base" ]; then
        branch_link=$(osc8_link "${github_base}/tree/${branch}" "$branch")
        line3_parts+=("branch $branch_link")
    else
        line3_parts+=("branch $branch")
    fi
fi

# Repo name with optional OSC 8 link
if [ -n "$repo_name" ]; then
    if [ -n "$github_base" ]; then
        repo_link=$(osc8_link "$github_base" "$repo_name")
        line3_parts+=("repo $repo_link")
    else
        line3_parts+=("repo $repo_name")
    fi
fi

line3=""
for part in "${line3_parts[@]}"; do
    if [ -z "$line3" ]; then
        line3="$part"
    else
        line3="${line3} | ${part}"
    fi
done

# --- Output ---
output="$line1"
[ -n "$line2" ] && output="${output}"$'\n'"${line2}"
[ -n "$line3" ] && output="${output}"$'\n'"${line3}"
printf "%s" "$output"
