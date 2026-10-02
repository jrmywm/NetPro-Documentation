SELECT id, domain, ip_add
FROM ps_blocked_list
WHERE domain = 'netpro-server-proof.test'
   OR ip_add = '192.168.31.35'
ORDER BY id;

SELECT COALESCE(MAX(packet_id), 0) AS npb_packet_baseline
FROM npb_packet;

SELECT COALESCE(MAX(packet_id), 0) AS policy_packet_baseline
FROM ps_packet;
