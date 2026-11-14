"""Controlled backend restart: preserve authoritative rows, outbox and Kafka topic IDs."""
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.request

def run(args, env=None): return subprocess.run(args, env=env, capture_output=True, text=True, check=True, timeout=60).stdout
def sql(query): return run(['runuser', '-u', 'postgres', '--', 'psql', '-d', 'test', '-Atc', query])
def snapshot():
    return {table: hashlib.sha256(sql('SELECT row_to_json(t)::text FROM ' + table + ' t ORDER BY ' + key).encode()).hexdigest()
        for table, key in [('ps_blocked_list', 'id'), ('netpro_bulk_policy_events', 'event_id')]}
def main():
    if os.geteuid() != 0 or socket.gethostname() != 'backend-vm': raise RuntimeError('Expected root on Management')
    if sql('SELECT count(*) FROM netpro_bulk_policy_events WHERE published_at IS NULL').strip() != '0': raise RuntimeError('Pending events exist; inspect before restart test')
    distribution = Path(run(['systemctl', 'show', 'netpro-kafka', '-p', 'WorkingDirectory', '--value']).strip())
    cli = distribution / 'bin/kafka-topics.sh'
    if not cli.is_file(): raise RuntimeError('Kafka CLI missing from active service distribution')
    env = dict(os.environ, JAVA_HOME='/opt/netpro-runtime/java-17-openjdk-amd64')
    def topic_ids():
        found = {}
        for topic in ['logging-dashboard', 'dpdk-blocked-list']:
            text = run([str(cli), '--bootstrap-server', '127.0.0.1:9092', '--describe', '--topic', topic], env)
            match = re.search(r'TopicId:\s*(\S+)', text)
            if not match: raise RuntimeError('Topic ID unavailable for ' + topic)
            found[topic] = match.group(1)
        return found
    before = snapshot(); topics_before = topic_ids()
    run(['systemctl', 'restart', 'netpro-backend'])
    context = ssl.create_default_context(cafile='/home/ubuntu/cert/server.crt'); context.check_hostname = False
    for _ in range(60):
        try: urllib.request.urlopen('https://127.0.0.1:3000/ps/import-policy-batch/restart-probe', context=context, timeout=3)
        except urllib.error.HTTPError as e:
            if e.code == 401: break
        except Exception: pass
        time.sleep(1)
    else: raise RuntimeError('Import adapter did not return after restart')
    after = snapshot(); topics_after = topic_ids()
    if before != after or topics_before != topics_after: raise RuntimeError('Restart changed authoritative rows/outbox/topic identities')
    result = {'passed': True, 'authoritativeAndOutboxHashes': after, 'kafkaTopicIds': topics_after,
        'privateImportRouteReady': True, 'note': 'No pending event existed at restart; outage retry was covered separately by injected tests'}
    p = Path('/home/netpro/recovered-theses-20261030/luthfi/evidence/live-backend-restart.json')
    p.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
if __name__ == '__main__': main()
