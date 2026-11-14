#include "thesis_dataplane.h"
#include <rte_eal.h>
#include <rte_mbuf.h>
#include <rte_ip.h>
#include <rte_udp.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
int main(int argc,char **argv){
 if(argc!=3)return 2;const char *input=argv[1],*output=argv[2];
 char *eal[]={"gate","-l","0","--no-huge","--no-pci","--no-shconf","--file-prefix=thesis-gate",NULL};
 if(rte_eal_init(7,eal)<0)return 2;
 struct rte_mempool *pool=rte_pktmbuf_pool_create("thesis_gate_pool",127,0,0,4096,SOCKET_ID_ANY);if(!pool)return 2;
 uint8_t p[1500]={0};FILE *f=fopen(input,"rb");if(!f)return 2;size_t n=fread(p+42,1,sizeof(p)-42,f)+42;fclose(f);
 p[12]=8;p[14]=0x45;p[16]=(n-14)>>8;p[17]=n-14;p[23]=17;
 p[26]=192;p[27]=168;p[28]=80;p[29]=29;p[30]=192;p[31]=168;p[32]=80;p[33]=28;
 p[34]=0xc0;p[35]=1;p[36]=18443>>8;p[37]=(uint8_t)18443;p[38]=(n-34)>>8;p[39]=n-34;
 struct rte_mbuf *pkt=rte_pktmbuf_alloc(pool);memcpy(rte_pktmbuf_append(pkt,n),p,n);char host[254];
 assert(thesis_quic_is_udp(pkt));assert(thesis_quic_domain(pkt,host));assert(!strcmp(host,"netpro-quic.test"));
 struct rte_mbuf *reply=thesis_quic_reply(pkt);assert(reply);const uint8_t *out=rte_pktmbuf_mtod(reply,const uint8_t *);
 assert(!memcmp(out+26,p+30,4)&&!memcmp(out+30,p+26,4));assert(!memcmp(out+34,p+36,2)&&!memcmp(out+36,p+34,2));
 assert(rte_ipv4_cksum((const struct rte_ipv4_hdr *)(out+14))==0);
 assert(rte_ipv4_udptcp_cksum_verify((const struct rte_ipv4_hdr *)(out+14),out+34)==0);
 f=fopen(output,"wb");assert(f);assert(fwrite(out+42,1,reply->pkt_len-42,f)==reply->pkt_len-42);fclose(f);
 rte_pktmbuf_free(reply);rte_pktmbuf_free(pkt);
 for(size_t k=0;k<n;k++){
  pkt=rte_pktmbuf_alloc(pool);if(k)memcpy(rte_pktmbuf_append(pkt,k),p,k);
  assert(!thesis_quic_domain(pkt,host));rte_pktmbuf_free(pkt);
 }
 printf("PASS DPDK mbuf: SNI, Close construction, IP/UDP checksums, reversed tuple; %zu truncated prefixes\n",n);
 rte_mempool_free(pool);rte_eal_cleanup();return 0;
}
