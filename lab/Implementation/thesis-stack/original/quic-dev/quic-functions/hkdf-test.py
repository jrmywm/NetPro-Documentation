from Crypto.Cipher import AES
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
import binascii
import hashlib
import hmac
from collections import namedtuple
import math



client_in = binascii.unhexlify("00200f746c73313320636c69656e7420696e00")
server_in = binascii.unhexlify("00200f746c7331332073657276657220696e00")
quic_key = binascii.unhexlify("00100e746c7331332071756963206b657900")
quic_iv= binascii.unhexlify("000c0d746c733133207175696320697600")
quic_hp = binascii.unhexlify("00100d746c733133207175696320687000")


ClientInitialSample = namedtuple('ClientInitialSample', [
    'dcid', 'initial_secret', 'client_initial_secret', 'key', 'iv', 'hp','unprotected_payload', 'protected_payload', 'unprotected_header', 'protected_header', 'protected_packet'
])

client_initial_sample = ClientInitialSample(
    dcid=binascii.unhexlify("8394c8f03e515708"),
    initial_secret=binascii.unhexlify("7db5df06e7a69e432496adedb00851923595221596ae2ae9fb8115c1e9ed0a44"),
    client_initial_secret=binascii.unhexlify("c00cf151ca5be075ed0ebfb5c80323c42d6b7db67881289af4008f1f6c357aea"),
    key=binascii.unhexlify("1f369613dd76d5467730efcbe3b1a22d"),
    iv=binascii.unhexlify("fa044b2f42a3fd3b46fb255c"),
    hp=binascii.unhexlify("9f50449e04a0e810283a1e9933adedd2"),
    unprotected_payload=binascii.unhexlify("060040f1010000ed0303ebf8fa56f12939b9584a3896472ec40bb863cfd3e86804fe3a47f06a2b69484c00000413011302010000c000000010000e00000b6578616d706c652e636f6dff01000100000a00080006001d0017001800100007000504616c706e000500050100000000003300260024001d00209370b2c9caa47fbabaf4559fedba753de171fa71f50f1ce15d43e994ec74d748002b0003020304000d0010000e0403050306030203080408050806002d00020101001c00024001003900320408ffffffffffffffff05048000ffff07048000ffff0801100104800075300901100f088394c8f03e51570806048000ffff"),
    protected_payload=binascii.unhexlify("d1b1c98dd7689fb8ec11d242b123dc9bd8bab936b47d92ec356c0bab7df5976d27cd449f63300099f3991c260ec4c60d17b31f8429157bb35a1282a643a8d2262cad67500cadb8e7378c8eb7539ec4d4905fed1bee1fc8aafba17c750e2c7ace01e6005f80fcb7df621230c83711b39343fa028cea7f7fb5ff89eac2308249a02252155e2347b63d58c5457afd84d05dfffdb20392844ae812154682e9cf012f9021a6f0be17ddd0c2084dce25ff9b06cde535d0f920a2db1bf362c23e596d11a4f5a6cf3948838a3aec4e15daf8500a6ef69ec4e3feb6b1d98e610ac8b7ec3faf6ad760b7bad1db4ba3485e8a94dc250ae3fdb41ed15fb6a8e5eba0fc3dd60bc8e30c5c4287e53805db059ae0648db2f64264ed5e39be2e20d82df566da8dd5998ccabdae053060ae6c7b4378e846d29f37ed7b4ea9ec5d82e7961b7f25a9323851f681d582363aa5f89937f5a67258bf63ad6f1a0b1d96dbd4faddfcefc5266ba6611722395c906556be52afe3f565636ad1b17d508b73d8743eeb524be22b3dcbc2c7468d54119c7468449a13d8e3b95811a198f3491de3e7fe942b330407abf82a4ed7c1b311663ac69890f4157015853d91e923037c227a33cdd5ec281ca3f79c44546b9d90ca00f064c99e3dd97911d39fe9c5d0b23a229a234cb36186c4819e8b9c5927726632291d6a418211cc2962e20fe47feb3edf330f2c603a9d48c0fcb5699dbfe5896425c5bac4aee82e57a85aaf4e2513e4f05796b07ba2ee47d80506f8d2c25e50fd14de71e6c418559302f939b0e1abd576f279c4b2e0feb85c1f28ff18f58891ffef132eef2fa09346aee33c28eb130ff28f5b766953334113211996d20011a198e3fc433f9f2541010ae17c1bf202580f6047472fb36857fe843b19f5984009ddc324044e847a4f4a0ab34f719595de37252d6235365e9b84392b061085349d73203a4a13e96f5432ec0fd4a1ee65accdd5e3904df54c1da510b0ff20dcc0c77fcb2c0e0eb605cb0504db87632cf3d8b4dae6e705769d1de354270123cb11450efc60ac47683d7b8d0f811365565fd98c4c8eb936bcab8d069fc33bd801b03adea2e1fbc5aa463d08ca19896d2bf59a071b851e6c239052172f296bfb5e72404790a2181014f3b94a4e97d117b438130368cc39dbb2d198065ae3986547926cd2162f40a29f0c3c8745c0f50fba3852e566d44575c29d39a03f0cda721984b6f440591f355e12d439ff150aab7613499dbd49adabc8676eef023b15b65bfc5ca06948109f23f350db82123535eb8a7433bdabcb909271a6ecbcb58b936a88cd4e8f2e6ff5800175f113253d8fa9ca8885c2f552e657dc603f252e1a8e308f76f0be79e2fb8f5d5fbbe2e30ecadd220723c8c0aea8078cdfcb3868263ff8f0940054da48781893a7e49ad5aff4af300cd804a6b6279ab3ff3afb64491c85194aab760d58a606654f9f4400e8b38591356fbf6425aca26dc85244259ff2b19c41b9f96f3ca9ec1dde434da7d2d392b905ddf3d1f9af93d1af5950bd493f5aa731b4056df31bd267b6b90a079831aaf579be0a39013137aac6d404f518cfd46840647e78bfe706ca4cf5e9c5453e9f7cfd2b8b4c8d169a44e55c88d4a9a7f9474241e221af44860018ab0856972e194cd934"),
    unprotected_header=binascii.unhexlify("c300000001088394c8f03e5157080000449e00000002"),
    protected_header=binascii.unhexlify("c000000001088394c8f03e5157080000449e7b9aec34"),
    protected_packet=binascii.unhexlify("c000000001088394c8f03e5157080000449e7b9aec34d1b1c98dd7689fb8ec11d242b123dc9bd8bab936b47d92ec356c0bab7df5976d27cd449f63300099f3991c260ec4c60d17b31f8429157bb35a1282a643a8d2262cad67500cadb8e7378c8eb7539ec4d4905fed1bee1fc8aafba17c750e2c7ace01e6005f80fcb7df621230c83711b39343fa028cea7f7fb5ff89eac2308249a02252155e2347b63d58c5457afd84d05dfffdb20392844ae812154682e9cf012f9021a6f0be17ddd0c2084dce25ff9b06cde535d0f920a2db1bf362c23e596d11a4f5a6cf3948838a3aec4e15daf8500a6ef69ec4e3feb6b1d98e610ac8b7ec3faf6ad760b7bad1db4ba3485e8a94dc250ae3fdb41ed15fb6a8e5eba0fc3dd60bc8e30c5c4287e53805db059ae0648db2f64264ed5e39be2e20d82df566da8dd5998ccabdae053060ae6c7b4378e846d29f37ed7b4ea9ec5d82e7961b7f25a9323851f681d582363aa5f89937f5a67258bf63ad6f1a0b1d96dbd4faddfcefc5266ba6611722395c906556be52afe3f565636ad1b17d508b73d8743eeb524be22b3dcbc2c7468d54119c7468449a13d8e3b95811a198f3491de3e7fe942b330407abf82a4ed7c1b311663ac69890f4157015853d91e923037c227a33cdd5ec281ca3f79c44546b9d90ca00f064c99e3dd97911d39fe9c5d0b23a229a234cb36186c4819e8b9c5927726632291d6a418211cc2962e20fe47feb3edf330f2c603a9d48c0fcb5699dbfe5896425c5bac4aee82e57a85aaf4e2513e4f05796b07ba2ee47d80506f8d2c25e50fd14de71e6c418559302f939b0e1abd576f279c4b2e0feb85c1f28ff18f58891ffef132eef2fa09346aee33c28eb130ff28f5b766953334113211996d20011a198e3fc433f9f2541010ae17c1bf202580f6047472fb36857fe843b19f5984009ddc324044e847a4f4a0ab34f719595de37252d6235365e9b84392b061085349d73203a4a13e96f5432ec0fd4a1ee65accdd5e3904df54c1da510b0ff20dcc0c77fcb2c0e0eb605cb0504db87632cf3d8b4dae6e705769d1de354270123cb11450efc60ac47683d7b8d0f811365565fd98c4c8eb936bcab8d069fc33bd801b03adea2e1fbc5aa463d08ca19896d2bf59a071b851e6c239052172f296bfb5e72404790a2181014f3b94a4e97d117b438130368cc39dbb2d198065ae3986547926cd2162f40a29f0c3c8745c0f50fba3852e566d44575c29d39a03f0cda721984b6f440591f355e12d439ff150aab7613499dbd49adabc8676eef023b15b65bfc5ca06948109f23f350db82123535eb8a7433bdabcb909271a6ecbcb58b936a88cd4e8f2e6ff5800175f113253d8fa9ca8885c2f552e657dc603f252e1a8e308f76f0be79e2fb8f5d5fbbe2e30ecadd220723c8c0aea8078cdfcb3868263ff8f0940054da48781893a7e49ad5aff4af300cd804a6b6279ab3ff3afb64491c85194aab760d58a606654f9f4400e8b38591356fbf6425aca26dc85244259ff2b19c41b9f96f3ca9ec1dde434da7d2d392b905ddf3d1f9af93d1af5950bd493f5aa731b4056df31bd267b6b90a079831aaf579be0a39013137aac6d404f518cfd46840647e78bfe706ca4cf5e9c5453e9f7cfd2b8b4c8d169a44e55c88d4a9a7f9474241e221af44860018ab0856972e194cd934")
)



def print_separator(step):
    print(f"\n{'='*10} Step {step} {'='*10}\n")


def hkdf_expand(prk: bytes, info: bytes, length: int, hash_algorithm: str = 'SHA256') -> bytes:
    """HKDF-Expand function.

    Args:
        prk (bytes): Pseudorandom key (PRK).
        info (bytes): Optional context and application-specific information.
        length (int): Length of output keying material (OKM) in octets.
        hash_algorithm (str): The hash function to use (default is SHA256).

    Returns:
        bytes: Output keying material (OKM).
    """
    
    # Choose the hash function
    # Use SHA-256 hash function
    hash_func = hashlib.sha256
    hash_len = hash_func().digest_size  # Length of the hash output in octets


    # Ensure length is within the specified limits
    if length > 255 * hash_len:
        raise ValueError("Length of OKM exceeds 255 * HashLen")

    # Calculate N (number of blocks needed)
    N = math.ceil(length / hash_len)
    
    # Initialize T and the output keying material (OKM)
    t = b''  # T is initially an empty string
    okm = b''  # Output keying material
    
    # Generate T(1), T(2), ..., T(N)
    for i in range(1, N + 1):
        # Concatenate T(i-1), info, and the byte i
        if i == 1:
            t_i = b''  # T(0) is the empty string
        else:
            t_i = t

        # Create the HMAC
        t = hmac.new(prk, t_i + info + bytes([i]), hash_func).digest()
        okm += t

    # Return the first L octets of OKM
    return okm[:length]
# Helper function to derive HKDF-Expand-Label
def hkdf_extract(salt,ikm, ikmhash_func=hashlib.sha256):
    """HKDF Extract phase."""
    print("Salt: ", binascii.hexlify(salt))
    print("IKM: ", binascii.hexlify(ikm))
    
    hash_func=hashlib.sha256
    prk = hmac.new(salt, ikm, hash_func).digest()    
    return prk


def header_unmask(hp, sample, masked_header):
    cipher = AES.new(hp, AES.MODE_ECB)
    encrypted = cipher.encrypt(sample)
    mask = encrypted[:5]  # This gives 5 bytes as in your example
    mask_hex = binascii.hexlify(mask).decode()
    print

# AES-GCM encryption and decryption functions=====================================================================

def generate_aead_nonce(iv: bytes, packet_number: int) -> bytes:
    """
    Generates the AEAD nonce by XORing the IV with the left-padded packet number.
    
    :param iv: The initialization vector (IV) used for encryption (typically 12 bytes).
    :param packet_number: The QUIC packet number (62 bits).
    :return: The generated nonce (same length as the IV, typically 12 bytes).
    """
    # Ensure packet number fits within 62 bits
    if packet_number >= (1 << 62):
        raise ValueError("Packet number exceeds 62 bits")
    
    # Convert packet number to network byte order (big-endian) and pad to the size of the IV
    packet_number_bytes = packet_number.to_bytes(8, byteorder='big')  # 8 bytes (64 bits)
    
    # Pad the packet number to the IV size (12 bytes for AES-GCM)
    # Keep only the rightmost 62 bits (remove 2 leftmost bits), then pad to match the IV size
    padded_packet_number = (b'\x00' * (len(iv) - len(packet_number_bytes))) + packet_number_bytes[-len(iv):]
    
    # XOR the padded packet number with the IV to generate the nonce
    nonce = bytes(a ^ b for a, b in zip(iv, padded_packet_number))
    
    return nonce


def aead_encrypt(key: bytes, iv: bytes, payload: bytes, unencrypted_header: bytes) -> tuple:
    """
    Encrypts the plaintext using AES-GCM with the provided key, IV, and associated data (A).
    Returns the ciphertext and authentication tag (ciphertext + tag is produced by AES-GCM).
    
    :param key: The encryption key (16, 24, or 32 bytes).
    :param iv: The initialization vector (nonce) used for encryption (typically 12 bytes for GCM).
    :param plaintext: The data to be encrypted.
    :param associated_data: The additional authenticated data (AAD), typically the packet header.
    :return: Encrypted ciphertext and authentication tag.
    """
    pn = get_pn(unencrypted_header, get_pn_length(unencrypted_header))
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(generate_aead_nonce(iv,pn), payload, unencrypted_header)
    return ciphertext

def aead_decrypt(key: bytes, iv: bytes, ciphertext: bytes, unencrypted_header: bytes) -> bytes:
    """
    Decrypts the ciphertext using AES-GCM with the provided key, IV, and associated data (A).
    Returns the decrypted plaintext.
    
    :param key: The decryption key (16, 24, or 32 bytes).
    :param iv: The initialization vector (nonce) used for decryption.
    :param ciphertext: The encrypted data (ciphertext + tag).
    :param associated_data: The additional authenticated data (AAD), typically the packet header.
    :return: Decrypted plaintext.
    """
    pn = get_pn(unencrypted_header, get_pn_length(unencrypted_header))
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(generate_aead_nonce(iv,pn), ciphertext, unencrypted_header)
    return plaintext

def pad_to_size(data: bytes, size: int) -> bytes:
    """
    Pads the input byte data with 0x00 bytes until it reaches the specified size.
    
    :param data: The input byte data to be padded.
    :param size: The desired final size of the byte data.
    :return: Padded byte data of the specified size.
    """
    if len(data) > size:
        raise ValueError("Input data is larger than the specified size")
    
    # Add padding with 0x00 until data reaches the specified size
    padding_needed = size - len(data)
    return data + b'\x00' * padding_needed

# Header Protection functions=====================================================================
def aes_ecb_encrypt(key: bytes, data: bytes) -> bytes:
    """
    Encrypts the data using AES in ECB mode with the provided key.
    
    :param key: The AES key (must be 16, 24, or 32 bytes long).
    :param data: The input data to be encrypted (must be a multiple of the block size, i.e., 16 bytes).
    :return: The encrypted data.
    """
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(data) + encryptor.finalize()

def header_protection(protected_frame: bytes, hp: bytes, unprotected_header: bytes) -> bytes:
    """
    Applies QUIC header protection based on the first 16 bytes of the protected frame (sample) and AES-ECB mode.
    
    :param protected_frame: The full QUIC packet (protected frame) in bytes.
    :param hp: The header protection key (AES key).
    :return: The modified protected frame after applying header protection.
    """
    # Step 1: Extract the first 16 bytes of the protected frame as the sample
    sample = protected_frame[:16]
    print("Sample:", binascii.hexlify(sample))
    
    # Step 2: Encrypt the sample using AES-ECB with the header protection key (hp)
    mask = aes_ecb_encrypt(hp, sample)[:5]  # Extract the first 5 bytes of the mask
    print("Mask:", binascii.hexlify(mask))
    
    pn_length = (unprotected_header[0] & 0x03) + 1
    print("Packet Number Length:", pn_length)

    # Step 3: XOR header[0] with mask[0] & 0x0f (modify header byte)
    header = bytearray(unprotected_header)  # Initialize the header with 4 zero bytes
    header[0] ^= mask[0] & 0x0f  # Modify the first byte with mask[0] & 0x0f
    print("Modified Header[0]:", binascii.hexlify(header[0:1]))
    pn_offset = get_pn_offset(header)
    
    # Step 4: XOR header[18..21] with mask[1..4] (modify bytes 18 to 21)
    header[pn_offset:pn_offset+pn_length] = bytes(a ^ b for a, b in zip(header[pn_offset:pn_offset+pn_length], mask[1:1+pn_length]))
    print("Modified Header[18..22]:", binascii.hexlify(header[pn_offset:pn_offset+pn_length]))
    print("Unprotected Header :", binascii.hexlify(unprotected_header))
    print("Protected Header   :", binascii.hexlify(header))

    # Return the modified protected frame (header)
    return bytes(header)

def remove_header_protection(protected_packet: bytes, hp: bytes) -> bytes:
    """
    Removes QUIC header protection based on the first 16 bytes of the protected packet and AES-ECB mode.
    
    :param protected_packet: The full QUIC packet (protected frame) in bytes.
    :param hp: The header protection key (AES key).
    :return: The modified unprotected packet after removing header protection.
    """
    pn_offset = get_pn_offset(protected_packet)
    
    print("Packet Number Offset:", pn_offset)
    for pn_length in range(1, 5):  # Looping through packet number lengths 1 to 5
        print("Testing Packet Number Length:", pn_length)
        print("pn_offset: ", pn_offset) 
        # Extract protected header and payload based on pn_offset and pn_length
        protected_header = protected_packet[:pn_offset + pn_length]
        protected_payload = protected_packet[pn_offset+pn_length:]

        # Get the first 16 bytes of the protected payload as the sample
        sample = protected_packet[pn_offset+4:pn_offset+4+16]
        print("Protected Header:", binascii.hexlify(protected_header))
        print("Protected Payload: ", binascii.hexlify(protected_payload))
        print("Sample:", binascii.hexlify(sample))
        
        print("HP: ", binascii.hexlify(hp))

        # Step 2: Decrypt the sample using AES-ECB with the header protection key (hp)
        mask = aes_ecb_encrypt(hp, sample)[:5]  # Extract the first 5 bytes of the mask
        print("Mask:", binascii.hexlify(mask))

        # Create a mutable bytearray for the first byte of the protected header
        demasked_header = bytearray(protected_header)

        # Modify the first byte with mask[0] & 0x0f
        demasked_header[0] ^= mask[0] & 0x0f
        print("First Byte Demasked:", binascii.hexlify(demasked_header))
        pn_length_demasked = (demasked_header[0] & 0x03) + 1
        print("pn_length_demasked: ", pn_length_demasked)
        if pn_length == ((demasked_header[0] & 0x03)+1):
            print("pn_length Matches: ", pn_length)
            break
        elif pn_length <= 4:
            print("pn_length Mismatch: ", pn_length)
            print("-" * 40)  # Separator for each loop iteration
        else:
            raise ValueError("Packet number length not found")
            return

    # Step 3: XOR the protected packet with the mask to recover the unprotected packet
    end = demasked_header[pn_offset:pn_offset+pn_length]
    print("End: ", binascii.hexlify(end))
    endMask = mask[1:1+pn_length]
    print("End Mask: ", binascii.hexlify(endMask))
    
    demasked_header[pn_offset:pn_offset+pn_length] = bytes(a ^ b for a, b in zip(demasked_header[pn_offset:pn_offset+pn_length], mask[1:1+pn_length]))
    
    print("Demasked Header:", binascii.hexlify(demasked_header))
    return demasked_header, protected_packet, protected_payload

def get_pn_length(demasked_header: bytes) -> int:
    """
    Extracts the packet number length from the demasked header.
    
    :param demasked_header: The demasked header after removing header protection.
    :return: The packet number length (in bytes).
    """
    return (demasked_header[0] & 0x03) + 1

def get_pn(demasked_header: bytes, pn_length: int) -> int:
    return  int.from_bytes(demasked_header[-int(pn_length):], byteorder='big')



def get_pn_offset(header: bytes) -> int:
    parser = 5
    token_len_len=1
    payload_len_len=2
    dcid_len = int(header[parser])
    print("DCID Length: ", dcid_len)

    # Step 2: Find the byte at position 5 + dcid and consider it as SCID
    parser += dcid_len + 1
    # print("Parser ", parser)
    scid_len = header[parser]
    print("SCID Length: ", scid_len)    

    # Step 3: Find the byte at position 3 + scid and consider it as payload
    parser += scid_len + 1
    # print("Parser ", parser)
    token = header[parser]
    print("Token Length: ", token)
    length_indicator = 3

    pn_offset=7+dcid_len+scid_len+token+payload_len_len+token_len_len  
    print("PN Offset: ", pn_offset)
    return pn_offset
 
 
def get_dcid(header: bytes) -> bytes:
    parser = 5
    dcid_len = int(header[parser])
    print("DCID Length: ", dcid_len)
    dcid = header[parser+1:parser+dcid_len+1]
    return dcid


initial_salt = binascii.unhexlify("38762cf7f55934b34d179ae6a4c80cadccbb7f0a")
cid = binascii.unhexlify("8394c8f03e515708")  # Replace with actual CID value
encrypted_header = binascii.unhexlify("c40000000108f234c00c2ca3316703f1826a00421565")
encrypted_payload = binascii.unhexlify("c38513818cb837c915ba3e2077a9fa8be76751eb076b4ae3b95847217b1ccd3bd7108b72c742d3b1a44ebff91db2f2ce4ccc87832afbc3fcea0111a98242022e4d8e71f198492433fb5c67fe22acdf178c3eeb92f4dd4e251b541e798e0bfa5c87da744fc130e7fcff89cdb4f9e99007002499b8d1b66a8f79a494fc5331ec6fa9b69a11b5c9f24ffe5e83c59ec58914cebc86594029637d40f9dcec283e88273c1113eb3cf2531b08db52aac0c9de7b00e6fc19c34a6f0e80197c85678f687c6d56d33265fdd8bd8b5d1af109c8fce9a7a01bcba4a9b37c2062129d65980b9b29aa024494e333f2cb72dca81fb41feb6d995ebf06b001f2d949095a0e4538db500e4e29c3170e64a7d19ccc116d08447621845e784de82bd11977d8b9d5051277fd5d49def0eab206280d59578b764b8d8c8f8649f8730f09319c459901a3d1454f15d449ff3d777ecec05eb673c1f75ff9e0afbd842ccae4f4bf60b18a71260b8f769fc30857733a66d133db45bc017c494ade6386738b9761f6bae743e2effac214b1058a37cbc41e1ec775fe8a4daf1e03e7a050a20e80789db7ab64a8c9f52a0df05a5ffcc76501bdf39a2e20bfdac957ba815763f61cdaa13541c65303168cc356050b022d46a3a90f150ef08a46436efb75ebd902de39c130a82ac5f08cd9f1b39736f565f179d1fc3988cbcec53883ace9706c6cd5a6269811bb2de21659ef05648ddaf861810d66bb758c6aa80e9a39")
dcid = get_dcid(encrypted_header)
print("DCID:", binascii.hexlify(dcid))

# Step 1: HKDF-Extract to generate initial secret================================================================
print_separator(1)
initial_secret = hkdf_extract(initial_salt, dcid)
# if initial_secret == client_initial_sample.initial_secret:
#     print("Initial secret matches the expected value.")
# else:
#     print("Error: Initial secret does not match the expected value.")
print("Initial Secret:", binascii.hexlify(initial_secret))

# Step 2: HKDF-Expand-Label to generate client_initial_secret
print_separator(2)
client_initial_secret = hkdf_expand(initial_secret, client_in, 32)
# if client_initial_secret == client_initial_sample.client_initial_secret:
#     print("Client initial secret matches the expected value.")
# else:
#     print("Error: Client initial secret does not match the expected value.")
print("Client Initial Secret:", binascii.hexlify(client_initial_secret))

# Step 3: Derive client key
print_separator(3)
client_key = hkdf_expand(client_initial_secret, quic_key, 16)
# if client_key == client_initial_sample.key:
#     print("Client key matches the expected value.")
# else:
#     print("Error: Client key does not match the expected value.")
print("Client Key:", binascii.hexlify(client_key))

# Step 4: Derive client IV
print_separator(4)
client_iv = hkdf_expand(client_initial_secret, quic_iv, 12)
# if client_iv == client_initial_sample.iv:
#     print("Client iv matches the expected value.")
# else:
#     print("Error: Client iv does not match the expected value.")
print("Client IV:", binascii.hexlify(client_iv))

# Step 5: Derive client HP
print_separator(5)
client_hp = hkdf_expand(client_initial_secret, quic_hp, 16)
# if client_hp == client_initial_sample.hp:
#     print("Client hp matches the expected value.")
# else:
#     print("Error: Client hp does not match the expected value.")
print("Client HP:", binascii.hexlify(client_hp))
#=======================================================================================

header_sample = binascii.unhexlify("c300000001088394c8f03e5157080000449e00000002")
payload_sample = binascii.unhexlify("060040f1010000ed0303ebf8fa56f12939b9584a3896472ec40bb863cfd3e86804fe3a47f06a2b69484c00000413011302010000c000000010000e00000b6578616d706c652e636f6dff01000100000a00080006001d0017001800100007000504616c706e000500050100000000003300260024001d00209370b2c9caa47fbabaf4559fedba753de171fa71f50f1ce15d43e994ec74d748002b0003020304000d0010000e0403050306030203080408050806002d00020101001c00024001003900320408ffffffffffffffff05048000ffff07048000ffff0801100104800075300901100f088394c8f03e51570806048000ffff")
# print("Payload Sample:", binascii.hexlify(payload_sample))
protected_payload = aead_encrypt(client_key, client_iv, payload_sample, client_initial_sample.unprotected_header)
print_separator(6)
# if protected_payload == client_initial_sample.protected_payload:
#     print("Protected payload matches the expected value.")
# else:
#     print("Error: Protected payload does not match the expected value.")
protected_header = header_protection(protected_payload, client_hp, header_sample)
print_separator(7)
protected_packet = protected_header + protected_payload
print_separator(8)
if protected_packet == client_initial_sample.protected_packet:
    print("Protected packet matches the expected value.")
else:
    print("Error: Protected packet does not match the expected value.")


print_separator(9)
print("Unmask the header protection")

protected_packet_wireshark=binascii.unhexlify("c40000000108f234c00c2ca3316703f1826a00421565c38513818cb837c915ba3e2077a9fa8be76751eb076b4ae3b95847217b1ccd3bd7108b72c742d3b1a44ebff91db2f2ce4ccc87832afbc3fcea0111a98242022e4d8e71f198492433fb5c67fe22acdf178c3eeb92f4dd4e251b541e798e0bfa5c87da744fc130e7fcff89cdb4f9e99007002499b8d1b66a8f79a494fc5331ec6fa9b69a11b5c9f24ffe5e83c59ec58914cebc86594029637d40f9dcec283e88273c1113eb3cf2531b08db52aac0c9de7b00e6fc19c34a6f0e80197c85678f687c6d56d33265fdd8bd8b5d1af109c8fce9a7a01bcba4a9b37c2062129d65980b9b29aa024494e333f2cb72dca81fb41feb6d995ebf06b001f2d949095a0e4538db500e4e29c3170e64a7d19ccc116d08447621845e784de82bd11977d8b9d5051277fd5d49def0eab206280d59578b764b8d8c8f8649f8730f09319c459901a3d1454f15d449ff3d777ecec05eb673c1f75ff9e0afbd842ccae4f4bf60b18a71260b8f769fc30857733a66d133db45bc017c494ade6386738b9761f6bae743e2effac214b1058a37cbc41e1ec775fe8a4daf1e03e7a050a20e80789db7ab64a8c9f52a0df05a5ffcc76501bdf39a2e20bfdac957ba815763f61cdaa13541c65303168cc356050b022d46a3a90f150ef08a46436efb75ebd902de39c130a82ac5f08cd9f1b39736f565f179d1fc3988cbcec53883ace9706c6cd5a6269811bb2de21659ef05648ddaf861810d66bb758c6aa80e9a39")
demasked_header, protected_wireshark_packet, protected_wireshark_payload = remove_header_protection(protected_packet_wireshark, client_hp)
decrypted_payload = aead_decrypt(client_key, client_iv, protected_wireshark_payload, demasked_header)
print("Decrypted Payload: ", binascii.hexlify(decrypted_payload))
# print("Decrypted Payload:", binascii.hexlify(decrypted_payload))
