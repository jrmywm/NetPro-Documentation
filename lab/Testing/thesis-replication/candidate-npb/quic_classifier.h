#ifndef NETPRO_QUIC_CLASSIFIER_H
#define NETPRO_QUIC_CLASSIFIER_H
#include <stddef.h>
#include <stdint.h>
/* Cheap forwarding hint only. Authentication/SNI belongs to Policy Server.
 * IPv4/Ethernet, unfragmented UDP, v1 Initial, >=1200-byte UDP payload.
 * Test port 18443 and production port 443 only; no VLAN/IPv6 handling here. */
static int netpro_quic_initial_hint(const uint8_t *p,size_t n){
 if(n<14+20+8+1200||p[12]!=8||p[13]!=0||(p[14]>>4)!=4)return 0;
 size_t ihl=(p[14]&15u)*4u;if(ihl<20||14+ihl+8>n||p[23]!=17)return 0;
 unsigned iplen=((unsigned)p[16]<<8)|p[17];
 if(iplen<ihl+8+1200||14+iplen>n||(p[20]&63)||p[21])return 0;
 size_t u=14+ihl;unsigned dst=((unsigned)p[u+2]<<8)|p[u+3];
 unsigned len=((unsigned)p[u+4]<<8)|p[u+5];
 if((dst!=443&&dst!=18443)||len<1208||len!=iplen-ihl)return 0;
 size_t q=u+8,end=u+len;
 if((p[q]&0xf0)!=0xc0||p[q+1]||p[q+2]||p[q+3]||p[q+4]!=1)return 0;
 size_t o=q+5;unsigned dl=p[o++];if(dl>20||!dl||o+dl+1>end)return 0;o+=dl;
 unsigned sl=p[o++];if(sl>20||!sl||o+sl>end)return 0;
 return 1;
}
#endif
