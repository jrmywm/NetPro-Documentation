#include "quic_classifier.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
int main(int argc,char **argv){
 if(argc!=2)return 2;uint8_t p[1500]={0};FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t k=fread(p+42,1,sizeof(p)-42,f);fclose(f);if(k!=1200)return 2;
 size_t n=42+k;p[12]=8;p[14]=0x45;p[16]=(uint8_t)((n-14)>>8);p[17]=(uint8_t)(n-14);p[23]=17;
 p[36]=(uint8_t)(18443>>8);p[37]=(uint8_t)18443;p[38]=(uint8_t)((k+8)>>8);p[39]=(uint8_t)(k+8);
 assert(netpro_quic_initial_hint(p,n));
 for(size_t i=0;i<n;i++)assert(!netpro_quic_initial_hint(p,i));
 const size_t offsets[]={12,14,20,21,23,36,38,42,46,47};
 const uint8_t bad[]={0,0x44,0x20,1,6,0,0,0x40,2,21};
 for(size_t i=0;i<sizeof(offsets)/sizeof(offsets[0]);i++){
  uint8_t saved=p[offsets[i]];p[offsets[i]]=bad[i];assert(!netpro_quic_initial_hint(p,n));p[offsets[i]]=saved;
 }
 p[36]=1;p[37]=187;assert(netpro_quic_initial_hint(p,n));
 printf("PASS actual Initial on UDP443/18443, all %zu truncated prefixes, 10 malformed/unsupported cases\n",n);
 return 0;
}
