/* Isolated safety gate for the archived thesis branch, not live enforcement. */
#include "quicFunctions.h"
#include <openssl/evp.h>

static int verify_close(const unsigned char *p, size_t n, QuicCryptoKeys *k) {
    size_t o=5;
    if(n<8)return 0;
    unsigned dl=p[o++]; if(dl>20||o+dl+1>n)return 0; o+=dl;
    unsigned sl=p[o++]; if(sl>20||o+sl+2>n)return 0; o+=sl;
    /* Crafter always emits an empty token and a one/two-byte length. */
    if(p[o++]!=0)return 0;
    unsigned w=1u<<(p[o]>>6);if(w>2||o+w>n)return 0;
    size_t payload=p[o]&63;for(unsigned i=1;i<w;i++)payload=(payload<<8)|p[o+i];o+=w;
    if(payload!=n-o||o+4+16>n)return 0;
    unsigned char mask[32]={0};int a=0,b=0;
    EVP_CIPHER_CTX *ctx=EVP_CIPHER_CTX_new();if(!ctx)return 0;
    int ok=EVP_EncryptInit_ex(ctx,EVP_aes_128_ecb(),NULL,k->quic_hp_server,NULL)==1;
    ok=ok&&EVP_CIPHER_CTX_set_padding(ctx,0)==1;
    ok=ok&&EVP_EncryptUpdate(ctx,mask,&a,p+o+4,16)==1;
    ok=ok&&EVP_EncryptFinal_ex(ctx,mask+a,&b)==1;EVP_CIPHER_CTX_free(ctx);if(!ok)return 0;
    unsigned char hdr[128];if(o+4>sizeof(hdr))return 0;memcpy(hdr,p,o+4);
    hdr[0]^=mask[0]&15;unsigned pnw=(hdr[0]&3)+1;uint64_t pn=0;
    for(unsigned i=0;i<pnw;i++){hdr[o+i]^=mask[i+1];pn=(pn<<8)|hdr[o+i];}
    size_t h=o+pnw;if(n<h+16)return 0;
    unsigned char nonce[12],plain[2048];memcpy(nonce,k->quic_iv_server,12);
    for(int i=0;i<8;i++)nonce[11-i]^=(unsigned char)(pn>>(8*i));
    ctx=EVP_CIPHER_CTX_new();if(!ctx)return 0;
    ok=EVP_DecryptInit_ex(ctx,EVP_aes_128_gcm(),NULL,NULL,NULL)==1;
    ok=ok&&EVP_CIPHER_CTX_ctrl(ctx,EVP_CTRL_GCM_SET_IVLEN,12,NULL)==1;
    ok=ok&&EVP_DecryptInit_ex(ctx,NULL,NULL,k->quic_key_server,nonce)==1;
    ok=ok&&EVP_DecryptUpdate(ctx,NULL,&a,hdr,(int)h)==1;
    ok=ok&&EVP_DecryptUpdate(ctx,plain,&a,p+h,(int)(n-h-16))==1;
    ok=ok&&EVP_CIPHER_CTX_ctrl(ctx,EVP_CTRL_GCM_SET_TAG,16,(void *)(p+n-16))==1;
    ok=ok&&EVP_DecryptFinal_ex(ctx,plain+a,&b)==1;EVP_CIPHER_CTX_free(ctx);
    return ok&&a+b>=4&&plain[0]==0x1c;
}
int main(void) {
    const unsigned char dcid[]={0x83,0x94,0xc8,0xf0,0x3e,0x51,0x57,0x08};
    const unsigned char scid[]={1,2,3,4,5,6,7,8};
    QuicCryptoKeys keys={0};unsigned char output[2048]={0};uint32_t n=0;
    derive_initial_keys(dcid,sizeof(dcid),true,&keys);
    derive_initial_keys(dcid,sizeof(dcid),false,&keys);
    quic_payload_crafter(scid,sizeof(scid),dcid,sizeof(dcid),output,&n,&keys,false);
    int verified=n<=sizeof(output)&&verify_close(output,n,&keys);
    printf("generated_bytes=%u independent_authenticated_close=%s\n",n,verified?"PASS":"FAIL");
    return verified?0:1;
}
