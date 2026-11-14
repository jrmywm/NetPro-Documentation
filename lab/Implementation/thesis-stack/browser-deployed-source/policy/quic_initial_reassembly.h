#ifndef NETPRO_QUIC_INITIAL_REASSEMBLY_H
#define NETPRO_QUIC_INITIAL_REASSEMBLY_H
#include "quicFunctions.h"
#include <stdlib.h>
#include <string.h>

#define QUIC_HELLO_LIMIT 4096
#define QUIC_HELLO_SLOTS 128

/* The existing TLS parser takes a record. Its five-byte header is synthesized
 * only after all ClientHello handshake bytes have been authenticated. */
char *tls_clienthello_sni(const uint8_t *record, size_t length, bool *valid);

struct quic_hello_flow {
    uint8_t key[54];
    uint8_t record[5 + QUIC_HELLO_LIMIT];
    uint8_t present[QUIC_HELLO_LIMIT];
    size_t contiguous;
    uint64_t touched_ms;
    uint64_t largest_pn;
    bool used;
};
static _Thread_local struct quic_hello_flow quic_hello_flows[QUIC_HELLO_SLOTS];

static bool quic_read_varint(const uint8_t **cursor, const uint8_t *end, uint64_t *value)
{
    if (*cursor == end) return false;
    size_t bytes = (size_t)1 << (**cursor >> 6);
    if (bytes > (size_t)(end - *cursor)) return false;
    *value = *(*cursor)++ & 63u;
    for (size_t i = 1; i < bytes; ++i)
        *value = (*value << 8) | *(*cursor)++;
    return true;
}

static bool quic_skip_ack(const uint8_t **cursor, const uint8_t *end, bool ecn)
{
    uint64_t ignored, ranges;
    if (!quic_read_varint(cursor,end,&ignored) || !quic_read_varint(cursor,end,&ignored) ||
        !quic_read_varint(cursor,end,&ranges) || !quic_read_varint(cursor,end,&ignored) ||
        ranges > (size_t)(end - *cursor)/2) return false;
    for (uint64_t i=0; i<ranges; ++i)
        if (!quic_read_varint(cursor,end,&ignored) || !quic_read_varint(cursor,end,&ignored))
            return false;
    return !ecn || (quic_read_varint(cursor,end,&ignored) &&
                    quic_read_varint(cursor,end,&ignored) &&
                    quic_read_varint(cursor,end,&ignored));
}

static char *quic_initial_sni(const uint8_t *packet, size_t length,
                              const uint8_t tuple[12], uint64_t now_ms,
                              QuicCryptoKeys *keys)
{
    if (length < 8 || length > 4096 || (packet[0]&0xf0)!=0xc0 ||
        memcmp(packet+1,"\x00\x00\x00\x01",4)) return NULL;
    const uint8_t *end=packet+length, *cursor=packet+5;
    size_t dl=*cursor++;
    if (!dl || dl>20 || dl+1>(size_t)(end-cursor)) return NULL;
    const uint8_t *dcid=cursor;
    cursor+=dl;
    size_t sl=*cursor++;
    if (sl>20 || sl>(size_t)(end-cursor)) return NULL;
    uint8_t key[54]={0};
    memcpy(key,tuple,12);
    key[12]=(uint8_t)dl;
    memcpy(key+13,dcid,dl);
    key[33]=(uint8_t)sl;
    memcpy(key+34,cursor,sl);
    cursor+=sl;
    uint64_t token, protected_length;
    if (!quic_read_varint(&cursor,end,&token) || token>(uint64_t)(end-cursor)) return NULL;
    cursor+=token;
    if (!quic_read_varint(&cursor,end,&protected_length) ||
        protected_length<20 || protected_length>(uint64_t)(end-cursor)) return NULL;
    size_t packet_length=(size_t)(cursor-packet)+protected_length;
    struct quic_hello_flow *flow=NULL,*slot=&quic_hello_flows[0];
    for (size_t i=0; i<QUIC_HELLO_SLOTS; ++i) {
        struct quic_hello_flow *candidate=&quic_hello_flows[i];
        if (candidate->used && now_ms-candidate->touched_ms>3000) candidate->used=false;
        if (candidate->used && !memcmp(candidate->key,key,sizeof key)) {
            flow=candidate;
            break;
        }
        if (!candidate->used || (slot->used && candidate->touched_ms<slot->touched_ms))
            slot=candidate;
    }
    derive_initial_keys(dcid,(int)dl,true,keys);
    uint8_t *header=NULL;
    size_t header_length=0;
    header_unmask(packet,packet_length,keys->quic_hp,&header,&header_length);
    if (!header || header_length+16>=packet_length || (header[0]&12)) {
        free(header);
        return NULL;
    }
    int pn_bytes=pn_length(header);
    uint64_t expected=flow ? flow->largest_pn+1 : 0;
    uint64_t window=UINT64_C(1)<<(8*pn_bytes);
    uint64_t number=(expected&~(window-1))|pn(header,pn_bytes,header_length);
    if (number+window/2<=expected) number+=window;
    else if (number>expected+window/2 && number>=window) number-=window;
    uint8_t nonce[12], plain[4096];
    generate_aead_nonce(keys->quic_iv,sizeof(keys->quic_iv),number,nonce);
    int size=aead_decrypt(keys->quic_key,sizeof(keys->quic_key),nonce,sizeof nonce,
                          header,header_length,packet+header_length,packet_length-header_length,plain);
    free(header);
    if (size<=0) return NULL;
    if (!flow) {
        flow=slot;
        memset(flow,0,sizeof *flow);
        memcpy(flow->key,key,sizeof key);
        flow->used=true;
    }
    flow->touched_ms=now_ms;
    if (number>flow->largest_pn) flow->largest_pn=number;

    cursor=plain;
    end=plain+size;
    bool have_crypto=false;
    while (cursor<end) {
        uint64_t type, offset, bytes;
        if (!quic_read_varint(&cursor,end,&type)) goto invalid;
        if (type<=1) continue;
        if (type==2 || type==3) {
            if (!quic_skip_ack(&cursor,end,type==3)) goto invalid;
            continue;
        }
        if (type==28) break;
        if (type!=6 || !quic_read_varint(&cursor,end,&offset) ||
            !quic_read_varint(&cursor,end,&bytes) || offset>QUIC_HELLO_LIMIT ||
            bytes>QUIC_HELLO_LIMIT-offset || bytes>(uint64_t)(end-cursor)) goto invalid;
        for (size_t i=0; i<bytes; ++i) {
            size_t pos=(size_t)offset+i;
            if (flow->present[pos] && flow->record[5+pos]!=cursor[i]) goto invalid;
            flow->present[pos]=1;
            flow->record[5+pos]=cursor[i];
        }
        cursor+=bytes;
        have_crypto|=bytes!=0;
    }
    while (flow->contiguous<QUIC_HELLO_LIMIT && flow->present[flow->contiguous])
        ++flow->contiguous;
    if (!have_crypto || flow->contiguous<4) return NULL;
    const uint8_t *hello=flow->record+5;
    size_t total=4+(((size_t)hello[1]<<16)|((size_t)hello[2]<<8)|hello[3]);
    if (hello[0]!=1 || total>QUIC_HELLO_LIMIT) goto invalid;
    if (flow->contiguous<total) return NULL;
    flow->record[0]=0x16;
    flow->record[1]=3;
    flow->record[2]=3;
    flow->record[3]=(uint8_t)(total>>8);
    flow->record[4]=(uint8_t)total;
    bool valid=false;
    return tls_clienthello_sni(flow->record,total+5,&valid);
invalid:
    flow->used=false;
    return NULL;
}
#endif
