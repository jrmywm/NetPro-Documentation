"""Independent QUIC v1 Initial authentication and client-local timing evidence."""
from pathlib import Path
import struct,json,hashlib,hmac,sys
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
BASE=Path(__file__).resolve().parent
def packets(path):
    data=path.read_bytes();endian='<' if data[:4]==bytes.fromhex('d4c3b2a1') else '>'
    o=24
    while o+16<=len(data):
        sec,us,n,_=struct.unpack_from(endian+'IIII',data,o);o+=16
        p=data[o:o+n];o+=n
        if len(p)<42 or p[12:14]!=b'\x08\x00' or p[23]!=17:continue
        u=14+(p[14]&15)*4;length=int.from_bytes(p[u+4:u+6],'big')
        yield sec+us/1e6,p[26:30],struct.unpack_from('!HH',p,u),p[u+8:u+length]
def varint(p,o):
    n=1<<(p[o]>>6);return int.from_bytes(p[o:o+n],'big')&((1<<(8*n-2))-1),o+n
def header(p):
    o=5;dl=p[o];o+=1;dcid=p[o:o+dl];o+=dl;sl=p[o];o+=1;scid=p[o:o+sl];o+=sl
    token,o=varint(p,o);o+=token;length,o=varint(p,o)
    return dcid,scid,o,length
def contains_handshake(p):
    while len(p)>6 and p[0]&0x80 and p[1:5]==b'\x00\x00\x00\x01':
        kind=(p[0]>>4)&3
        if kind==2:return True
        if kind==3:return False
        try:
            o=5;o+=1+p[o];o+=1+p[o]
            if kind==0:token,o=varint(p,o);o+=token
            length,o=varint(p,o);p=p[o+length:]
        except (IndexError,ValueError):return False
    return False
def expand(secret,label,n):
    label=b'tls13 '+label;info=struct.pack('!H',n)+bytes([len(label)])+label+b'\x00'
    out=b'';prev=b'';i=1
    while len(out)<n:
        prev=hmac.new(secret,prev+info+bytes([i]),hashlib.sha256).digest();out+=prev;i+=1
    return out[:n]
def decrypt(p,original_dcid):
    salt=bytes.fromhex('38762cf7f55934b34d179ae6a4c80cadccbb7f0a')
    initial=hmac.new(salt,original_dcid,hashlib.sha256).digest()
    secret=expand(initial,b'server in',32)
    key=expand(secret,b'quic key',16);iv=expand(secret,b'quic iv',12);hp=expand(secret,b'quic hp',16)
    dcid,scid,o,length=header(p)
    mask=Cipher(algorithms.AES(hp),modes.ECB()).encryptor().update(p[o+4:o+20])
    first=p[0]^(mask[0]&15);pnlen=(first&3)+1
    pnbytes=bytes(p[o+i]^mask[i+1] for i in range(pnlen));pn=int.from_bytes(pnbytes,'big')
    aad=bytes([first])+p[1:o]+pnbytes
    nonce=bytes(a^b for a,b in zip(iv,pn.to_bytes(12,'big')))
    plain=AESGCM(key).decrypt(nonce,p[o+pnlen:o+length],aad)
    error,o=varint(plain,1);frame,o=varint(plain,o);length,o=varint(plain,o)
    if plain[0]!=0x1c or len(plain)-o<length:raise ValueError('Incomplete CONNECTION_CLOSE frame')
    return dict(authenticated=True,packet_number=pn,dcid=dcid.hex(),scid=scid.hex(),plaintext_hex=plain.hex(),error_code=error,trigger_frame=frame,reason=plain[o:o+length].decode('ascii',errors='replace'))
def main():
    evidence=Path(sys.argv[1]) if len(sys.argv)>1 else sorted((BASE/'evidence').glob('live-original-stack-*'))[-1]
    rows=[];connections={};start=None
    for t,src,ports,p in packets(evidence/'192.168.31.39-close.pcap'):
        start=start or t;row={'relative_ms':round((t-start)*1000,3),'src':'.'.join(map(str,src)),'ports':ports,'bytes':len(p)}
        if src==bytes([192,168,80,29]) and len(p)>=1200 and p[0]&0xf0==0xc0:
            dcid,scid,_,_=header(p)
            if ports[0] not in connections or connections[ports[0]][1]!=scid:connections[ports[0]]=(dcid,scid)
            row['client_initial']=True
        if src==bytes([192,168,80,28]) and len(p) in (78,79):
            original=connections.get(ports[1])
            if original:
                try:
                    row.update(decrypt(p,original[0]));row['destination_cid_matches_client']=row['dcid']==original[1].hex()
                except Exception as exc:row['authentication_error']=str(exc)
        if src==bytes([192,168,80,28]):row['server_handshake']=contains_handshake(p)
        port=ports[0] if src==bytes([192,168,80,29]) else ports[1]
        if port in connections:row['connection_id']=connections[port][1].hex()
        rows.append(row)
    (evidence/'close-analysis.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    for r in rows:
        if r.get('client_initial') or r.get('authenticated') or r.get('authentication_error'):print(json.dumps(r))
if __name__=='__main__':main()
