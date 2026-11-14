#ifndef THESIS_DATAPLANE_H
#define THESIS_DATAPLANE_H
#include <rte_mbuf.h>
int thesis_quic_is_udp(const struct rte_mbuf *packet);
int thesis_quic_domain(const struct rte_mbuf *packet,char hostname[254]);
struct rte_mbuf *thesis_quic_reply(const struct rte_mbuf *packet);
void thesis_quic_record_sent(unsigned sent);
void thesis_metrics_report(void);
#endif
