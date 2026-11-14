#ifndef NETPRO_THESIS_MONITORING_H
#define NETPRO_THESIS_MONITORING_H
#include <stdint.h>
int send_trap(uint16_t portid, uint64_t dropped_packets);
int send_trap_2minutes(uint16_t portid, uint64_t dropped_packets);
/* Reconstructed from thesis behavior: not present in recovered branch. */
int send_trap_with_domain(const char *domain);
void thesis_monitor_cycle(uint16_t portid, uint64_t resets, int end_cycle);
#endif
