#define _GNU_SOURCE
#include <sched.h>
/* Bintang e5448b3 shell/CLI trap mechanism, with this lab's endpoint adapter.
 * Domain notification is a labelled reconstruction; no author source recovered.
 * All notifications use the real Net-SNMP snmptrap CLI, not custom BER encoding.
 */
#include "thesis_monitoring.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <inttypes.h>
#include <ctype.h>
#include <time.h>
#include <arpa/inet.h>
#include <pthread.h>
/* Integration adaptation: the reconstructed per-domain hook must not pause
 * packet processing while the real snmptrap CLI runs. Original count and
 * 120-second summary functions below remain unchanged. */
static pthread_mutex_t domain_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t domain_ready=PTHREAD_COND_INITIALIZER;
static pthread_once_t domain_once=PTHREAD_ONCE_INIT;
static char domain_queue[1024][254];
static unsigned domain_head,domain_tail,domain_count;
static uint64_t domain_overflow;
static int domain_worker_ready;
static int deliver_domain_trap(const char *domain);
static void *domain_worker(void *unused) {
    (void)unused;
    /* Lab integration: avoid inheriting the packet lcore affinity for
     * CLI subprocesses. CPU 0 runs control/heartbeat in this four-core layout. */
    cpu_set_t cpus; CPU_ZERO(&cpus); CPU_SET(0,&cpus);
    if (pthread_setaffinity_np(pthread_self(),sizeof(cpus),&cpus)!=0)
        fprintf(stderr,"[THESIS SNMP] unable to select control CPU\n");
    for (;;) {
        char domain[254];
        pthread_mutex_lock(&domain_lock);
        while (!domain_count) pthread_cond_wait(&domain_ready,&domain_lock);
        memcpy(domain,domain_queue[domain_head],sizeof(domain));
        domain_head=(domain_head+1)%1024;--domain_count;
        pthread_mutex_unlock(&domain_lock);
        (void)deliver_domain_trap(domain);
    }
    return NULL;
}
static void start_domain_worker(void) {
    pthread_t thread;
    if (pthread_create(&thread,NULL,domain_worker,NULL)==0) {
        domain_worker_ready=1;pthread_detach(thread);
    }
}
extern char PS_ID[200];
static int enabled(void) {
    const char *target=getenv("NETPRO_THESIS_SNMP_TARGET"); struct in_addr addr;
    if (!target || inet_pton(AF_INET,target,&addr)!=1) return 0;
    for (size_t i=0; PS_ID[i]; ++i)
        if (!isalnum((unsigned char)PS_ID[i]) && PS_ID[i]!='-' && PS_ID[i]!='_' && PS_ID[i]!='.') return 0;
    return 1;
}
int send_trap(uint16_t portid, uint64_t dropped_packets) {
    if (!enabled()) return 0;
    char command[512];
    snprintf(command,sizeof(command),
        "/usr/bin/snmptrap -v 2c -c public %s '' 1.3.6.1.4.1.8072.9999.1 1.3.6.1.4.1.8072.9999.1 s \"%s port %u sent %" PRIu64 " packets\"",
        getenv("NETPRO_THESIS_SNMP_TARGET"), PS_ID,portid,dropped_packets);
    int result=system(command);
    printf("[THESIS SNMP] recovered reset-count trap port=%u count=%" PRIu64 " exit=%d\n",portid,dropped_packets,result);
    return result==0;
}
int send_trap_2minutes(uint16_t portid, uint64_t dropped_packets) {
    if (!enabled()) return 0;
    char command[512];
    snprintf(command,sizeof(command),
        "/usr/bin/snmptrap -v 2c -c public %s '' 1.3.6.1.4.1.8072.9999.1 1.3.6.1.4.1.8072.9999.1 s \"%s port %u dropped %" PRIu64 " packets after 2 minutes\"",
        getenv("NETPRO_THESIS_SNMP_TARGET"),PS_ID,portid,dropped_packets);
    int result=system(command);
    printf("[THESIS SNMP] recovered 120-second summary exit=%d\n",result);
    return result==0;
}
static int deliver_domain_trap(const char *domain) {
    if (!enabled() || !domain) return 0;
    size_t n=strnlen(domain,254); if (!n || n>253) return 0;
    for (size_t i=0;i<n;++i)
        if (!isalnum((unsigned char)domain[i]) && domain[i]!='-' && domain[i]!='.') return 0;
    char command[768];
    /* Reconstructed payload/OID mapping: use recovered enterprise OID plus text.
     * The original per-domain OID/schema was not available in the branch.
     */
    snprintf(command,sizeof(command),
        "/usr/bin/snmptrap -v 2c -c public %s '' 1.3.6.1.4.1.8072.9999.1 1.3.6.1.4.1.8072.9999.1 s \"%s blocked domain %s [reconstructed]\"",
        getenv("NETPRO_THESIS_SNMP_TARGET"),PS_ID,domain);
    int result=system(command);
    printf("[THESIS SNMP reconstructed] domain=%s exit=%d\n",domain,result);
    return result==0;
}
int send_trap_with_domain(const char *domain) {
    const char *flag=getenv("NETPRO_THESIS_SNMP_DOMAIN_ENABLE");
    if (flag && strcmp(flag,"0")==0) return 0;
    if (!enabled() || !domain) return 0;
    size_t n=strnlen(domain,254);if (!n || n>253) return 0;
    for (size_t i=0;i<n;++i)
        if (!isalnum((unsigned char)domain[i]) && domain[i]!='-' && domain[i]!='.') return 0;
    pthread_once(&domain_once,start_domain_worker);
    if (!domain_worker_ready) return 0;
    pthread_mutex_lock(&domain_lock);
    if (domain_count==1024) {
        ++domain_overflow;
        if (domain_overflow==1 || domain_overflow%1000==0)
            fprintf(stderr,"[THESIS SNMP reconstructed] queue overflow=%" PRIu64 "\n",domain_overflow);
        pthread_mutex_unlock(&domain_lock);return 0;
    }
    memcpy(domain_queue[domain_tail],domain,n+1);
    domain_tail=(domain_tail+1)%1024;++domain_count;
    pthread_cond_signal(&domain_ready);pthread_mutex_unlock(&domain_lock);
    return 1; /* Queue acceptance, not delivery confirmation. */
}
void thesis_monitor_cycle(uint16_t portid,uint64_t resets,int end_cycle) {
    static time_t last_reset_time;
    static uint64_t sent_this_cycle;
    if (!enabled()) return;
    time_t now=time(NULL); if (!last_reset_time) last_reset_time=now;
    if (!end_cycle) { if (resets) sent_this_cycle+=send_trap(portid,resets); return; }
    /* Preserve branch semantics: summary argument counts successful count traps
     * in this stats cycle, not unique domains or a 120-second packet total.
     */
    if (now-last_reset_time>=120) {
        send_trap_2minutes(portid,sent_this_cycle); last_reset_time=now;
    }
    sent_this_cycle=0;
}
