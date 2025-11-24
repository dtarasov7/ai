#
#  xxx
#
```bash
#!/bin/bash

# Set variables
STATE_FILE="/var/lib/app_versions/state.json"
PROM_FILE="/var/lib/node_exporter/textfile_collector/app_versions.prom"
LOCK_FILE="/var/lock/app_versions.lock"
NODENAME=$(hostname)

# app_list should be set here or sourced from config
# Example: app_list="nginx openssl"

# Function to get app version - do not implement
get_app_version() {
    local app="$1"
    # TODO: Implement logic to get version and set VERSION
    # Return 1 if app exists and version obtained, 0 otherwise
    # VERSION="some.version"  # Set global VERSION
    return 0  # Placeholder
}

# Improved version encoding function
encode_version() {
    local version="$1"
    
    # Remove pre-release suffixes (everything after -, +, ~)
    version=$(echo "$version" | sed 's/[-+~].*//')
    
    # Support up to 4 components, each up to 9999
    local IFS='.'
    read -ra parts <<< "$version"
    
    # Pad with zeros if fewer than 4 components
    while [ ${#parts[@]} -lt 4 ]; do
        parts+=("0")
    done
    
    # Formula: v1*1000000000000 + v2*100000000 + v3*10000 + v4
    # But using string formatting for large numbers
    printf "%d%04d%04d%04d" "${parts[0]}" "${parts[1]}" "${parts[2]}" "${parts[3]}"
}

# Lock to prevent parallel runs
exec 9> "$LOCK_FILE"
if ! flock -n 9; then
    echo "Script is already running."
    exit 1
fi

# Start time for duration
START_TIME=$(date +%s)

# Read state.json or initialize empty
if [ -f "$STATE_FILE" ]; then
    JSON=$(cat "$STATE_FILE")
else
    JSON='{"apps":{}}'
fi

# Temporary prom file
TEMP_PROM="$PROM_FILE.tmp"
> "$TEMP_PROM"

# Success flag
SUCCESS=1

# Process each app
for app in $app_list; do
    # Get current state for app
    current=$(echo "$JSON" | jq -r ".apps.\"$app\".current // \"\"")
    previous=$(echo "$JSON" | jq -r ".apps.\"$app\".previous // \"\"")
    changes_total=$(echo "$JSON" | jq ".apps.\"$app\".changes_total // 0")
    change_time=$(echo "$JSON" | jq ".apps.\"$app\".change_time // 0")

    # Get version
    VERSION=""
    get_app_version "$app"
    if [ $? -eq 1 ]; then
        version_str="$VERSION"
        version_num=$(encode_version "$version_str")
        is_deleted=false
    else
        is_deleted=true
    fi

    update=false
    if $is_deleted; then
        if [ -n "$current" ] && [ "$current" != "deleted" ]; then
            previous="$current"
            current="deleted"
            change_time=$(date +%s)
            changes_total=$((changes_total + 1))
            update=true
            version_str="deleted"
            version_num=0
        fi
    else
        if [ "$current" != "$version_str" ]; then
            if [ -n "$current" ]; then
                previous="$current"
                changes_total=$((changes_total + 1))
            else
                previous=""
            fi
            current="$version_str"
            change_time=$(date +%s)
            update=true
        fi
    fi

    # Generate metrics only if app is in state or was found
    if [ -n "$current" ]; then
        echo "app_version_info{nodename=\"$NODENAME\", appname=\"$app\", version=\"$version_str\"} 1" >> "$TEMP_PROM"
        echo "app_version_numeric{nodename=\"$NODENAME\", appname=\"$app\"} $version_num" >> "$TEMP_PROM"
        echo "app_version_change_time_seconds{nodename=\"$NODENAME\", appname=\"$app\"} $change_time" >> "$TEMP_PROM"
        echo "app_version_scrape_timestamp_seconds{instance=\"$NODENAME\", appname=\"$app\"} $(date +%s)" >> "$TEMP_PROM"
    fi

    # Update JSON if needed
    if [ -n "$current" ]; then
        JSON=$(echo "$JSON" | jq ".apps.\"$app\" = {\"current\": \"$current\", \"previous\": \"$previous\", \"changes_total\": $changes_total, \"change_time\": $change_time}")
    fi
done

# Write updated state.json atomically
echo "$JSON" > "$STATE_FILE.tmp" && mv "$STATE_FILE.tmp" "$STATE_FILE"

# Collector metrics
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
echo "app_version_collector_success{instance=\"$NODENAME\"} $SUCCESS" >> "$TEMP_PROM"
echo "app_version_collector_duration_seconds{instance=\"$NODENAME\"} $DURATION" >> "$TEMP_PROM"

# Atomically move prom file
mv "$TEMP_PROM" "$PROM_FILE"

# Release lock
flock -u 9
```
