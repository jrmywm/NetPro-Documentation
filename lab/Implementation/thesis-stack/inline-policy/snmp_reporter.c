#define _POSIX_C_SOURCE 200809L
#include "snmp_reporter.h"

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

#define QUEUE_CAPACITY 4096
#define BER_CAPACITY 1024
#define DEFAULT_ENTERPRISE "1.3.6.1.4.1.53864.1"

typedef struct { uint64_t attempts, accepted, sequence, kind; char domain[254]; } event_t;
static event_t queue[QUEUE_CAPACITY];
static size_t head, tail, count;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t ready = PTHREAD_COND_INITIALIZER;
static pthread_t worker;
static int sockfd = -1, started, stopping;
static struct timespec agent_started;
static struct sockaddr_in destination;
static char community[128];
static char enterprise_oid[128];
static atomic_uint_fast64_t enqueued, overflow, send_attempted, send_accepted, send_error;
static atomic_uint_fast64_t domain_sequence;
static unsigned summary_seconds;
static struct timespec last_summary;

/* Small definite-length BER encoder. Every append checks the remaining space. */
static int put_len(uint8_t *b, size_t cap, size_t *n, size_t len) {
    if (len < 128) { if (*n >= cap) return -1; b[(*n)++] = (uint8_t)len; return 0; }
    uint8_t tmp[sizeof(size_t)]; size_t k = 0;
    while (len) { tmp[k++] = (uint8_t)len; len >>= 8; }
    if (*n + k + 1 > cap) return -1;
    b[(*n)++] = (uint8_t)(0x80 | k);
    while (k) b[(*n)++] = tmp[--k];
    return 0;
}
static int wrap(uint8_t *out, size_t cap, size_t *n, uint8_t tag,
                const uint8_t *data, size_t len) {
    if (*n >= cap) return -1;
    out[(*n)++] = tag;
    if (put_len(out, cap, n, len) || *n + len > cap) return -1;
    memcpy(out + *n, data, len); *n += len; return 0;
}
static int base128(uint8_t *b, size_t cap, size_t *n, uint64_t value) {
    uint8_t t[10]; size_t k = 0;
    do { t[k++] = (uint8_t)(value & 0x7f); value >>= 7; } while (value && k < sizeof(t));
    if (*n + k > cap) return -1;
    while (k) { uint8_t v = t[--k]; b[(*n)++] = (uint8_t)(v | (k ? 0x80 : 0)); }
    return 0;
}
static int oid_encode(const char *text, uint8_t *out, size_t cap, size_t *n) {
    uint32_t arcs[32]; size_t count = 0; const char *p = text;
    if (!p || !*p || *p == '.' || p[strlen(p)-1] == '.') return -1;
    while (*p) {
        if (*p < '0' || *p > '9') return -1;
        char *end; errno = 0; unsigned long v = strtoul(p, &end, 10);
        if (errno || end == p || v > UINT32_MAX || count == 32 || (*end && *end != '.')) return -1;
        arcs[count++] = (uint32_t)v; p = *end ? end + 1 : end;
    }
    if (count < 2 || arcs[0] > 2 || (arcs[0] < 2 && arcs[1] > 39)) return -1;
    if (base128(out, cap, n, (uint64_t)arcs[0] * 40 + arcs[1])) return -1;
    for (size_t i = 2; i < count; ++i) if (base128(out, cap, n, arcs[i])) return -1;
    return 0;
}
static int encode_unsigned(uint8_t *out, size_t cap, size_t *n, uint8_t tag, uint64_t value) {
    uint8_t bytes[9]; size_t k = 0;
    do { bytes[8-k++] = (uint8_t)value; value >>= 8; } while (value && k < 8);
    size_t start = 9-k;
    if (bytes[start] & 0x80) bytes[--start] = 0;
    return wrap(out, cap, n, tag, bytes + start, 9-start);
}
static int encode_counter(uint8_t *out, size_t cap, size_t *n, uint64_t value) {
    return encode_unsigned(out,cap,n,0x46,value);
}
static int varbind(uint8_t *out, size_t cap, size_t *n, const char *oid, uint64_t value) {
    uint8_t body[512], oidbuf[96]; size_t bn=0, on=0;
    if (oid_encode(oid, oidbuf, sizeof(oidbuf), &on) || wrap(body, sizeof(body), &bn, 0x06, oidbuf, on) ||
        encode_counter(body, sizeof(body), &bn, value)) return -1;
    return wrap(out, cap, n, 0x30, body, bn);
}
static int varbind_typed(uint8_t *out, size_t cap, size_t *n, const char *oid,
                         uint8_t value_tag, const uint8_t *value, size_t value_len) {
    uint8_t body[512], oidbuf[96]; size_t bn=0, on=0;
    if (oid_encode(oid, oidbuf, sizeof(oidbuf), &on) || wrap(body,sizeof(body),&bn,0x06,oidbuf,on) ||
        wrap(body,sizeof(body),&bn,value_tag,value,value_len)) return -1;
    return wrap(out,cap,n,0x30,body,bn);
}
static int varbind_unsigned(uint8_t *out, size_t cap, size_t *n, const char *oid,
                            uint8_t value_tag, uint64_t value) {
    uint8_t body[128], oidbuf[96]; size_t bn=0,on=0;
    if (oid_encode(oid,oidbuf,sizeof(oidbuf),&on) || wrap(body,sizeof(body),&bn,0x06,oidbuf,on) ||
        encode_unsigned(body,sizeof(body),&bn,value_tag,value)) return -1;
    return wrap(out,cap,n,0x30,body,bn);
}
static int build_trap(const event_t *e, uint8_t *packet, size_t cap, size_t *packet_len) {
    uint8_t pdu[BER_CAPACITY], vars[BER_CAPACITY], oidbuf[128];
    size_t pn=0, vn=0, on=0; char oid[160];
    const uint8_t zero=0;
    if (wrap(pdu,sizeof(pdu),&pn,0x02,&zero,1) || wrap(pdu,sizeof(pdu),&pn,0x02,&zero,1) ||
        wrap(pdu,sizeof(pdu),&pn,0x02,&zero,1)) return -1; /* request-id, error-status, error-index */
    snprintf(oid,sizeof(oid),"1.3.6.1.2.1.1.3.0");
    struct timespec now; if (clock_gettime(CLOCK_MONOTONIC,&now)) return -1;
    uint64_t elapsed_cs=(uint64_t)(now.tv_sec-agent_started.tv_sec)*100U;
    long ns=now.tv_nsec-agent_started.tv_nsec;
    if (ns<0) { elapsed_cs-=100; ns+=1000000000L; }
    elapsed_cs+=(uint64_t)(ns/10000000L);
    if (varbind_unsigned(vars,sizeof(vars),&vn,oid,0x43,(uint32_t)elapsed_cs)) return -1;
    snprintf(oid,sizeof(oid),"1.3.6.1.6.3.1.1.4.1.0");
    char trap_oid[160]; snprintf(trap_oid,sizeof(trap_oid),"%s.0.1",enterprise_oid);
    if (oid_encode(trap_oid,oidbuf,sizeof(oidbuf),&on) || varbind_typed(vars,sizeof(vars),&vn,oid,0x06,oidbuf,on)) return -1;
    snprintf(oid,sizeof(oid),"%s.0.2",enterprise_oid); if (varbind(vars,sizeof(vars),&vn,oid,e->attempts)) return -1;
    snprintf(oid,sizeof(oid),"%s.0.3",enterprise_oid); if (varbind(vars,sizeof(vars),&vn,oid,e->accepted)) return -1;
    snprintf(oid,sizeof(oid),"%s.0.11",enterprise_oid); if (varbind(vars,sizeof(vars),&vn,oid,e->sequence)) return -1;
    snprintf(oid,sizeof(oid),"%s.0.12",enterprise_oid); if (varbind(vars,sizeof(vars),&vn,oid,e->kind)) return -1;
    if (e->kind==1) {
        snprintf(oid,sizeof(oid),"%s.0.10",enterprise_oid);
        if (varbind_typed(vars,sizeof(vars),&vn,oid,0x04,(const uint8_t *)e->domain,strlen(e->domain))) return -1;
    }
    if (wrap(pdu,sizeof(pdu),&pn,0x30,vars,vn)) return -1;
    size_t n=0; if (wrap(packet,cap,&n,0xa7,pdu,pn)) return -1;
    uint8_t msg[BER_CAPACITY]; size_t mn=0;
    uint8_t ver=1; if (wrap(msg,sizeof(msg),&mn,0x02,&ver,1) || wrap(msg,sizeof(msg),&mn,0x04,(const uint8_t *)community,strlen(community)) ||
        n+mn+8>sizeof(msg)) return -1;
    memcpy(msg+mn,packet,n); mn+=n;
    n=0; if (wrap(packet,cap,&n,0x30,msg,mn)) return -1;
    *packet_len=n; return 0;
}
static void *worker_main(void *unused) {
    (void)unused;
    for (;;) {
        pthread_mutex_lock(&lock);
        while (!count && !stopping) pthread_cond_wait(&ready,&lock);
        if (!count && stopping) { pthread_mutex_unlock(&lock); break; }
        event_t e=queue[head]; head=(head+1)%QUEUE_CAPACITY; --count;
        pthread_mutex_unlock(&lock);
        uint8_t packet[BER_CAPACITY]; size_t len=0;
        atomic_fetch_add(&send_attempted,1);
        if (build_trap(&e,packet,sizeof(packet),&len) == 0) {
            ssize_t rc=sendto(sockfd,packet,len,0,(struct sockaddr *)&destination,sizeof(destination));
            if (rc == (ssize_t)len) atomic_fetch_add(&send_accepted,1);
            else atomic_fetch_add(&send_error,1);
        } else atomic_fetch_add(&send_error,1);
    }
    return NULL;
}
int snmp_reporter_start(void) {
    if (started) return -1;
    const char *enabled=getenv("NETPRO_SNMP_ENABLE");
    if (!enabled || strcmp(enabled,"1")) return 0;
    const char *ip=getenv("NETPRO_SNMP_MANAGER_IPV4"), *port=getenv("NETPRO_SNMP_MANAGER_PORT"),
        *comm=getenv("NETPRO_SNMP_COMMUNITY"), *oid=getenv("NETPRO_SNMP_ENTERPRISE_OID");
    if (!ip || !port || !comm || !*comm || strlen(comm)>=sizeof(community)) return -1;
    char *end; long p=strtol(port,&end,10); if (*end || p<1 || p>65535) return -1;
    memset(&destination,0,sizeof(destination)); destination.sin_family=AF_INET; destination.sin_port=htons((uint16_t)p);
    if (inet_pton(AF_INET,ip,&destination.sin_addr)!=1) return -1;
    snprintf(community,sizeof(community),"%s",comm);
    const char *chosen_oid=oid && *oid ? oid : DEFAULT_ENTERPRISE;
    if (strlen(chosen_oid)>=sizeof(enterprise_oid)) return -1;
    snprintf(enterprise_oid,sizeof(enterprise_oid),"%s",chosen_oid);
    uint8_t test[128]; size_t n=0;
    size_t arcs=1; for (const char *p=enterprise_oid; *p; ++p) if (*p=='.') ++arcs;
    if (arcs>29 || oid_encode(enterprise_oid,test,sizeof(test),&n) || n > 96) return -1;
    pthread_mutex_lock(&lock); head=tail=count=0; stopping=0; pthread_mutex_unlock(&lock);
    atomic_store(&enqueued,0); atomic_store(&overflow,0); atomic_store(&send_attempted,0);
    atomic_store(&send_accepted,0); atomic_store(&send_error,0);
    sockfd=socket(AF_INET,SOCK_DGRAM | SOCK_NONBLOCK | SOCK_CLOEXEC,0); if (sockfd<0) return -1;
    if (clock_gettime(CLOCK_MONOTONIC,&agent_started)) { close(sockfd); sockfd=-1; return -1; }
    summary_seconds=0;
    const char *period=getenv("NETPRO_SNMP_SUMMARY_SECONDS");
    if(period && *period) {
        char *end=NULL; errno=0; unsigned long value=strtoul(period,&end,10);
        if(errno||!end||*end||value>3600) {close(sockfd);sockfd=-1;return -1;}
        summary_seconds=(unsigned)value;
    }
    last_summary=agent_started;atomic_store(&domain_sequence,0);
    if (pthread_create(&worker,NULL,worker_main,NULL)) { close(sockfd); sockfd=-1; return -1; }
    started=1; return 1;
}
int snmp_reporter_submit(const snmp_reporter_snapshot_t *s) {
    if (!started || !s) return 0;
    struct timespec now;
    if(clock_gettime(CLOCK_MONOTONIC,&now))return -1;
    double elapsed=now.tv_sec-last_summary.tv_sec+(now.tv_nsec-last_summary.tv_nsec)/1e9;
    if(summary_seconds && elapsed<summary_seconds)return 0;
    if (pthread_mutex_trylock(&lock)) { atomic_fetch_add(&overflow,1); return -1; }
    if (stopping || count==QUEUE_CAPACITY) { pthread_mutex_unlock(&lock); atomic_fetch_add(&overflow,1); return -1; }
    queue[tail]=(event_t){.attempts=s->reset_attempts,.accepted=s->reset_tx_accepted,.kind=2}; tail=(tail+1)%QUEUE_CAPACITY; ++count;
    last_summary=now;
    atomic_fetch_add(&enqueued,1); pthread_cond_signal(&ready); pthread_mutex_unlock(&lock); return 0;
}
int snmp_reporter_submit_domain(const char *domain) {
    if(!started||!domain)return 0;
    size_t n=strnlen(domain,254);if(!n||n>253)return -1;
    if(pthread_mutex_trylock(&lock)){atomic_fetch_add(&overflow,1);return -1;}
    if(stopping||count==QUEUE_CAPACITY){pthread_mutex_unlock(&lock);atomic_fetch_add(&overflow,1);return -1;}
    event_t e={.kind=1,.sequence=atomic_fetch_add(&domain_sequence,1)+1};
    memcpy(e.domain,domain,n);e.domain[n]=0;queue[tail]=e;tail=(tail+1)%QUEUE_CAPACITY;++count;
    atomic_fetch_add(&enqueued,1);pthread_cond_signal(&ready);pthread_mutex_unlock(&lock);return 0;
}
void snmp_reporter_get_counters(snmp_reporter_counters_t *o) {
    if (!o) return;
    o->enqueued=atomic_load(&enqueued); o->overflow=atomic_load(&overflow);
    o->send_attempted=atomic_load(&send_attempted); o->send_accepted=atomic_load(&send_accepted);
    o->send_error=atomic_load(&send_error);
}
void snmp_reporter_stop(void) {
    if (!started) return;
    pthread_mutex_lock(&lock); stopping=1; pthread_cond_broadcast(&ready); pthread_mutex_unlock(&lock);
    pthread_join(worker,NULL); close(sockfd); sockfd=-1; started=0;
}
