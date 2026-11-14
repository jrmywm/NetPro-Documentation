#!/bin/bash
set -euo pipefail
. /etc/os-release
test "$VERSION_ID" = 24.04
if ! dpkg-query -W zabbix-release >/dev/null 2>&1; then
    task_dir=$(mktemp -d /tmp/netpro-zabbix-release.XXXXXX)
    curl -fsSLo "$task_dir/release.deb" 'https://repo.zabbix.com/zabbix/6.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_6.0-10+ubuntu24.04_all.deb'
    dpkg-deb -f "$task_dir/release.deb" Package Version
    test "$(dpkg-deb -f "$task_dir/release.deb" Package)" = zabbix-release
    dpkg -i "$task_dir/release.deb"
fi
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends zabbix-server-pgsql zabbix-frontend-php zabbix-nginx-conf zabbix-sql-scripts zabbix-sender php8.3-pgsql
dpkg-query -W -f='${Package} ${Version}\n' zabbix-server-pgsql zabbix-frontend-php zabbix-sender
# Configuration and a new, isolated database are a separate guarded step.
