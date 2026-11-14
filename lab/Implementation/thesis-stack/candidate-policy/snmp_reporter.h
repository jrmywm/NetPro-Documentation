#ifndef SNMP_REPORTER_H
#define SNMP_REPORTER_H

#include <stdint.h>

/* Optional, best-effort SNMPv2c trap reporter. Environment configuration:
 * NETPRO_SNMP_ENABLE=1, NETPRO_SNMP_MANAGER_IPV4, NETPRO_SNMP_MANAGER_PORT,
 * NETPRO_SNMP_COMMUNITY, NETPRO_SNMP_ENTERPRISE_OID.
 * OID defaults to the documented lab-private 1.3.6.1.4.1.53864.1 (not a
 * claim that this enterprise number is registered). */
typedef struct {
    uint64_t reset_attempts;
    uint64_t reset_tx_accepted;
} snmp_reporter_snapshot_t;

typedef struct {
    uint64_t enqueued;
    uint64_t overflow;
    uint64_t send_attempted;
    uint64_t send_accepted; /* UDP datagram accepted by local kernel only. */
    uint64_t send_error;
} snmp_reporter_counters_t;

/* Returns 0 if disabled, 1 if started, -1 on invalid enabled configuration or
 * thread/socket setup error. submit is bounded and never waits for the worker. */
int snmp_reporter_start(void);
int snmp_reporter_submit(const snmp_reporter_snapshot_t *snapshot);
int snmp_reporter_submit_domain(const char *domain);
void snmp_reporter_get_counters(snmp_reporter_counters_t *out);
void snmp_reporter_stop(void); /* drains queued events before returning */

#endif
