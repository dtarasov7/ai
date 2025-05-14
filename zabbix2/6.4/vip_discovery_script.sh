#!/bin/bash
#
# Script to discover VIP address for RadosGW service in Zabbix 6.4
#

# VIP address defined in Zabbix macros or passed as parameter
VIP=${1:-"$(zabbix_get -s 127.0.0.1 -k 'host.macro[{$RADOSGW.VIP}]' 2>/dev/null)"}
# If failed to get from zabbix_get, try with default macro format
if [ -z "$VIP" ] || [ "$VIP" = "ZBX_NOTSUPPORTED" ]; then
    VIP=${1:-"{$RADOSGW.VIP}"}
fi

# Generate JSON for Zabbix discovery with proper path
cat << EOF
{
    "data": [
        {
            "vip": "$VIP"
        }
    ]
}
EOF
