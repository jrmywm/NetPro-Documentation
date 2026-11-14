#!/bin/bash
exec > /tmp/netpro-rafie-preflight.txt 2>&1
hostname
systemctl is-active ssh
sudo -n true
systemctl list-units --type=service --no-legend | grep -E 'netpro|policy'
cd /home/netpro/NetPro-Policy-Server || exit 1
git status --short
sha256sum policyServer.c
readlink build/policyServer
ls meson.build Makefile build.sh 2>/dev/null
tar -czf /tmp/netpro-rafie-baseline.tar.gz policyServer.c meson.build
systemctl cat netpro-policy-server netpro-policy 2>/dev/null
ss -ltn | grep ':22'
