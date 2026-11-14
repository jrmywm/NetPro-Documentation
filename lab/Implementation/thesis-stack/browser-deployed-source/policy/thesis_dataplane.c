/* IPv4 QUIC v1 Initial integration with bounded ClientHello reassembly. */
#include "thesis_dataplane.h"
#include "quicFunctions.h"
#include "quic_initial_reassembly.h"
#include <time.h>
#include "snmp_reporter.h"
#include <rte_ether.h>
#include <rte_ip.h>
#include <rte_udp.h>
#include <stdatomic.h>
#include <inttypes.h>
#include <unistd.h>
static atomic_uint_fast64_t udp_seen,quic_positive,quic_blocked,close_crafted,close_sent,close_errors;
char *getDomain(const uint8_t *, int, bool, QuicCryptoKeys *);
/* Preserve thesis parse->Close key reuse without a shared cross-lcore race. */
static _Thread_local QuicCryptoKeys packet_keys;
static _Thread_local int packet_keys_ready;
int thesis_quic_is_udp(const struct rte_mbuf *packet){
 uint8_t buf[34];const uint8_t *p=rte_pktmbuf_read(packet,0,sizeof(buf),buf);
 return p && p[12]==8 && p[13]==0 && (p[14]>>4)==4 && p[23]==17;
}
static const uint8_t *read_packet(const struct rte_mbuf *packet,uint8_t buf[4096],size_t *n){
 *n=rte_pktmbuf_pkt_len(packet);if(*n>4096||*n<42)return NULL;
 return rte_pktmbuf_read(packet,0,*n,buf);
}
int thesis_quic_domain(const struct rte_mbuf *packet,char hostname[254]){
 packet_keys_ready=0;
 atomic_fetch_add(&udp_seen,1);uint8_t b[4096];size_t n;const uint8_t *p=read_packet(packet,b,&n);
 if(!p||p[12]!=8||p[13]!=0||(p[14]>>4)!=4||p[23]!=17)return 0;
 size_t ihl=(p[14]&15u)*4u,u=14+ihl;
 if(ihl<20||u+8>n||(p[20]&0x3f)||p[21])return 0;
 size_t iplen=((size_t)p[16]<<8)|p[17],ulen=((size_t)p[u+4]<<8)|p[u+5];
 unsigned port=((unsigned)p[u+2]<<8)|p[u+3];
 if(port!=443||iplen>n-14||iplen<ihl+8||ulen<8||ulen>iplen-ihl)return 0;
 struct timespec now;
 if(clock_gettime(CLOCK_MONOTONIC,&now)!=0)return 0;
 uint8_t tuple[12];
 memcpy(tuple,p+26,8);
 memcpy(tuple+8,p+u,4);
 memset(&packet_keys,0,sizeof(packet_keys));
 char *name=quic_initial_sni(p+u+8,ulen-8,tuple,(uint64_t)now.tv_sec*1000+now.tv_nsec/1000000,&packet_keys);
 if(!name)return 0;size_t length=strlen(name);
 if(!length||length>253){free(name);return 0;}
 memcpy(hostname,name,length+1);free(name);packet_keys_ready=1;atomic_fetch_add(&quic_positive,1);return 1;
}
struct rte_mbuf *thesis_quic_reply(const struct rte_mbuf *packet){
 atomic_fetch_add(&quic_blocked,1);uint8_t b[4096],payload[2048];size_t n;uint32_t bytes=0;
 const uint8_t *p=read_packet(packet,b,&n);if(!p)goto failed;
 size_t ihl=(p[14]&15u)*4u,u=14+ihl,q=u+8;
 if(ihl<20||q+7>n)goto failed;
 size_t o=q+5;unsigned dl=p[o++];if(!dl||dl>20||o+dl+1>n)goto failed;
 const uint8_t *dcid=p+o;o+=dl;unsigned sl=p[o++];if(sl>20||o+sl>n)goto failed;
 if(!packet_keys_ready)goto failed;QuicCryptoKeys keys=packet_keys;packet_keys_ready=0;
 quic_payload_crafter(p+o,sl,dcid,dl,payload,&bytes,&keys,false);
 if(!bytes||bytes>sizeof(payload))goto failed;
 struct rte_mbuf *reply=rte_pktmbuf_alloc(packet->pool);if(!reply)goto failed;
 uint8_t *out=(uint8_t *)rte_pktmbuf_append(reply,14+20+8+bytes);if(!out){rte_pktmbuf_free(reply);goto failed;}
 memcpy(out,p+6,6);memcpy(out+6,p,6);out[12]=8;out[13]=0;
 struct rte_ipv4_hdr *ip=(struct rte_ipv4_hdr *)(out+14);memset(ip,0,sizeof(*ip));
 ip->version_ihl=0x45;ip->time_to_live=64;ip->next_proto_id=17;ip->total_length=rte_cpu_to_be_16(20+8+bytes);
 memcpy(&ip->src_addr,p+30,4);memcpy(&ip->dst_addr,p+26,4);ip->hdr_checksum=rte_ipv4_cksum(ip);
 struct rte_udp_hdr *udp=(struct rte_udp_hdr *)(out+34);memset(udp,0,sizeof(*udp));
 memcpy(&udp->src_port,p+u+2,2);memcpy(&udp->dst_port,p+u,2);udp->dgram_len=rte_cpu_to_be_16(8+bytes);
 memcpy(out+42,payload,bytes);udp->dgram_cksum=rte_ipv4_udptcp_cksum(ip,udp);
 if(!udp->dgram_cksum)udp->dgram_cksum=0xffff;
 atomic_fetch_add(&close_crafted,1);return reply;
failed:atomic_fetch_add(&close_errors,1);return NULL;
}
void thesis_quic_record_sent(unsigned sent){if(sent)atomic_fetch_add(&close_sent,1);else atomic_fetch_add(&close_errors,1);}
void thesis_metrics_report(void){
 const char *path=getenv("NETPRO_REPLICATION_STATS_PATH");if(!path||strncmp(path,"/home/netpro/incoming/",22)||strlen(path)>900)return;
 char tmp[1024];snprintf(tmp,sizeof(tmp),"%s.tmp",path);FILE *f=fopen(tmp,"w");if(!f)return;
 snmp_reporter_counters_t s;snmp_reporter_get_counters(&s);
 fprintf(f,"{\"udp_seen\":%"PRIuFAST64",\"quic_positive\":%"PRIuFAST64",\"quic_blocked\":%"PRIuFAST64",\"close_crafted\":%"PRIuFAST64",\"close_sent\":%"PRIuFAST64",\"close_errors\":%"PRIuFAST64",\"snmp_enqueued\":%"PRIu64",\"snmp_overflow\":%"PRIu64",\"snmp_send_attempted\":%"PRIu64",\"snmp_kernel_accepted\":%"PRIu64",\"snmp_send_error\":%"PRIu64"}\n",atomic_load(&udp_seen),atomic_load(&quic_positive),atomic_load(&quic_blocked),atomic_load(&close_crafted),atomic_load(&close_sent),atomic_load(&close_errors),s.enqueued,s.overflow,s.send_attempted,s.send_accepted,s.send_error);
 fclose(f);rename(tmp,path);
}
