#include "quicFunctions.h"


/* 
 * Thread function for parallel HKDF expansion. 
 */
void* hkdf_expand_thread(void* arg) {
    HkdfExpandArgs* args = (HkdfExpandArgs*)arg;
    hkdf_expand(args->secret, args->secret_len, 
                args->info, args->info_len, 
                args->output, args->output_len);
    return NULL;
}

/* =============================================================================
 * Header Parsing Functions
 * =============================================================================
 */

/**
 * @brief Retrieves the packet number length (pn_length) from the demasked header.
 *
 * @param demasked_header Pointer to the demasked header bytes.
 * @return The length of the packet number (1 to 4 bytes).
 */
int pn_length(const uint8_t* demasked_header) {
    return (demasked_header[0] & 0x03) + 1;
}

/**
 * @brief Extract the packet number from the demasked header.
 *
 * @param demasked_header Pointer to the demasked header bytes.
 * @param pn_length The length of the packet number (in bytes).
 * @param header_length The total length of the demasked header (in bytes).
 * @return The packet number as a 32-bit integer.
 */
uint32_t pn(const uint8_t *demasked_header, int pn_length, int header_length) {
    if (pn_length < 1 || pn_length > header_length) {
        fprintf(stderr, "Invalid packet number length.\n");
        exit(EXIT_FAILURE);
    }

    uint32_t packet_number = 0;
    for (int i = 0; i < pn_length; i++) {
        packet_number = (packet_number << 8) | demasked_header[header_length - pn_length + i];
    }
    return packet_number;
}

/**
 * @brief Compute the offset to the packet number in a QUIC header.
 *
 * @param header Pointer to the header bytes.
 * @return The byte offset of the packet number within the header.
 */
int pn_offset(const uint8_t* header) {
    int base_offset = 5;
    int dcid_len    = header[base_offset];
    int scid_offset = base_offset + dcid_len + 1;
    int scid_len    = header[scid_offset];
    int token_offset = scid_offset + scid_len + 1;
    int token_length = header[token_offset];

    return base_offset + dcid_len + scid_len + token_length + 1 + 2 + 2;
}

/**
 * @brief Retrieve the DCID from the header (client or server perspective).
 *
 * @param header Pointer to the header bytes.
 * @param isClient `true` if extracting from client perspective, `false` otherwise.
 * @param dcid_length Will be populated with the DCID length.
 * @return Pointer to the start of the DCID.
 */
uint8_t* get_dcid(const uint8_t* header, bool isClient, uint8_t* dcid_length) {
    uint8_t initial_dcid_length = header[5];
    *dcid_length = initial_dcid_length;

    if (isClient) {
        return (uint8_t*)(header + 6);
    } else {
        *dcid_length = header[6 + initial_dcid_length];
        return (uint8_t*)(header + 6 + initial_dcid_length + 1);
    }
}


/**
 * @brief Decodes a QUIC VarInt and returns its length in bytes.
 * @param buf Pointer to the buffer containing the VarInt.
 * @param value Output parameter for the decoded value.
 * @return Number of bytes consumed (1, 2, 4, or 8), or -1 on error.
 */
 int decode_varint(const uint8_t *buf, uint64_t *value) {
    uint8_t first_byte = buf[0];
    uint8_t prefix = (first_byte & 0xC0) >> 6; // Extract first 2 bits
    size_t len;
    switch (prefix) {
        case 0: len = 1; *value = first_byte & 0x3F; break;         // 6 bits
        case 1: len = 2; *value = ((uint64_t)(first_byte & 0x3F) << 8)  | buf[1]; break; // 14 bits
        case 2: len = 4; *value = ((uint64_t)(first_byte & 0x3F) << 24) | (buf[1] << 16) | (buf[2] << 8) | buf[3]; break; // 30 bits
        case 3: len = 8; *value = ((uint64_t)(first_byte & 0x3F) << 56) | ((uint64_t)buf[1] << 48) | ((uint64_t)buf[2] << 40) | ((uint64_t)buf[3] << 32)
                               | (buf[4] << 24) | (buf[5] << 16) | (buf[6] << 8) | buf[7]; break; // 62 bits
        default: return -1; // Should never happen
    }
    return len;
}

/**
 * @brief Compute the packet number offset from the start of the QUIC packet.
 * @param header Pointer to the packet header bytes.
 * @param header_len Total length of the header.
 * @return The offset where the packet number starts, or -1 on error.
 */
int get_pn_offset(const uint8_t *header, size_t header_len) {
    const int base_offset = 5; // Fixed part of the QUIC header before DCID
    const int dcid_len_len = 1; // DCID length is always 1 byte
    const int scid_len_len = 1; // SCID length is always 1 byte

    if (header_len < base_offset + dcid_len_len) {
        fprintf(stderr, "Error: Header too short for DCID length.\n");
        return -1;
    }

    // Read DCID length (1 byte)
    uint8_t dcid_len = header[base_offset];
    size_t scid_offset = base_offset + dcid_len_len + dcid_len;

    if (scid_offset + scid_len_len > header_len) {
        fprintf(stderr, "Error: SCID offset out of bounds.\n");
        return -1;
    }

    // Read SCID length (1 byte)
    uint8_t scid_len = header[scid_offset];
    size_t token_offset = scid_offset + scid_len_len + scid_len;

    if (token_offset >= header_len) {
        fprintf(stderr, "Error: Token offset out of bounds.\n");
        return -1;
    }

    // Decode Token Length (VarInt, 1-8 bytes)
    uint64_t token_length;
    int token_len_bytes = decode_varint(&header[token_offset], &token_length);
    if (token_len_bytes == -1) {
        fprintf(stderr, "Error: Invalid Token Length VarInt.\n");
        return -1;
    }

    size_t payload_len_offset = token_offset + token_len_bytes + token_length;
    if (payload_len_offset >= header_len) {
        fprintf(stderr, "Error: Payload Length offset out of bounds.\n");
        return -1;
    }

    // Decode Payload Length (VarInt, usually 1-2 bytes)
    uint64_t payload_length;
    int len_len = decode_varint(&header[payload_len_offset], &payload_length);
    if (len_len == -1) {
        fprintf(stderr, "Error: Invalid Payload Length VarInt.\n");
        return -1;
    }

    // Final Packet Number offset calculation
    int pn_offset = base_offset 
                  + dcid_len_len + dcid_len 
                  + scid_len_len + scid_len 
                  + token_len_bytes + token_length 
                  + len_len;

    // printf("base_offset    : %d\n", base_offset);
    // printf("dcid_len       : %d\n", dcid_len);
    // printf("scid_len       : %d\n", scid_len);
    // printf("token_len_bytes: %d\n", token_len_bytes);
    // printf("token_length   : %lu\n", token_length);
    // printf("len_len        : %d\n", len_len);
    // printf("---------------\n");
    // printf("pn_offset      : %d\n", pn_offset);

    if (pn_offset >= (int)header_len) {
        fprintf(stderr, "Error: Packet Number offset out of bounds.\n");
        return -1;
    }

    return pn_offset;
}
/* =============================================================================
 * Header Protection
 * =============================================================================
 */

/**
 * @brief Remove header protection from a QUIC packet (Initial, Handshake, or 1-RTT).
 *
 * This function attempts different packet number lengths from 1 to 4, demasking
 * the first byte and comparing the PN length bits. Once it matches, it applies
 * the PN mask for the recognized PN length.
 *
 * @param protected_packet Pointer to the protected packet bytes.
 * @param packet_len Length of the protected packet.
 * @param hp_key The header protection key (AES-128 in this example).
 * @param output Pointer to a buffer pointer that will hold the demasked header.
 *               This buffer may be reallocated to fit the demasked header.
 * @param output_len Will be set to the length of the demasked header.
 */
void header_unmask(const uint8_t* protected_packet, size_t packet_len,
                   const uint8_t* hp_key, uint8_t** output, size_t* output_len) 
{
    if (packet_len < 5) {
        fprintf(stderr, "Packet too short!\n");
        return;
    }

    int pn_offset_val = get_pn_offset(protected_packet, packet_len);
    if (pn_offset_val < 0) {
        return;  // Error already reported by get_pn_offset
    }

    // Calculate maximum possible header length
    size_t max_header_len = pn_offset_val + 4;
    if (max_header_len > packet_len) {
        fprintf(stderr, "Calculated header length exceeds packet length.\n");
        return;
    }

    uint8_t demasked_header[max_header_len];
    memcpy(demasked_header, protected_packet, max_header_len);

    uint8_t mask[16] = {0};
    AES_KEY aes_key;
    AES_set_encrypt_key(hp_key, 128, &aes_key);

    /* 
     * Try packet number lengths from 1 to 4. 
     * We demask the first byte and check if pn_length bits match 
     * the expected value. 
     */
    int found_pn_length = 0;
    for (int pn_len_try = 1; pn_len_try <= 4; pn_len_try++) {
        size_t header_len_try = pn_offset_val + pn_len_try;

        if (pn_offset_val + 4 + 16 > packet_len) {
            fprintf(stderr, "Not enough data in the packet for the sample.\n");
            return;
        }

        // Reset header for each iteration
        memcpy(demasked_header, protected_packet, header_len_try);

        // Encrypt a sample of 16 bytes starting at [pn_offset_val + 4]
        // to produce mask

        // printf("Protected packet sampled: ");
        // for(int i = 0; i < 16; i++){
        //     printf("%02x", protected_packet[pn_offset_val + 4 + i]);
        // }
        // printf("\n");

        AES_encrypt(&protected_packet[pn_offset_val + 4], mask, &aes_key);

        // Demask the first byte
        demasked_header[0] ^= (mask[0] & 0x0F);

        int actual_pn_length = (demasked_header[0] & 0x03) + 1;
        if (pn_len_try == actual_pn_length) {
            found_pn_length = pn_len_try;
            break;
        }
    }

    if (found_pn_length == 0) {
        fprintf(stderr, "Error: Packet number length not found.\n");
        return;
    }

    // At this point, mask is set from the sample above; apply it to the PN bytes
    size_t final_header_len = pn_offset_val + found_pn_length;
    for (int i = 0; i < found_pn_length; i++) {
        demasked_header[pn_offset_val + i] ^= mask[i + 1];
    }

    // Reallocate output to fit the demasked header length
    uint8_t* tmp_ptr = (uint8_t*)realloc(*output, final_header_len);
    if (!tmp_ptr) {
        perror("Memory allocation failed");
        return;
    }
    *output = tmp_ptr;
    *output_len = final_header_len;

    memcpy(*output, demasked_header, final_header_len);
}



void header_mask(const uint8_t* protected_packet, size_t packet_len,int header_offset, const uint8_t* hp_key, uint8_t** output, size_t* output_len)  {
    uint8_t sample[16];  // Sample: first 16 bytes of the protected frame
    uint8_t mask[16];     // Mask derived from AES encryption
    AES_KEY aes_key;

    size_t temp_hdr_len = header_offset;
    uint8_t* temp_hdr = (uint8_t*)malloc(temp_hdr_len);
    uint8_t out_temp[temp_hdr_len];
    memcpy(temp_hdr, protected_packet, temp_hdr_len);  // Assuming a max header size of 22

    // Step 1: Extract the first 16 bytes from the protected frame as sample
    int pn_offset_val = get_pn_offset(protected_packet, packet_len);
    
    // Step 2: Encrypt the sample using AES-ECB with the header protection key (hp)
    AES_set_encrypt_key(hp_key, 128, &aes_key);
    AES_encrypt(&protected_packet[pn_offset_val + 4], mask, &aes_key);
    // Step 3: Get the pn length from the first byte of the header
    int pn_length = (temp_hdr[0] & 0x03) + 1;
    // Step 4: Demask the first byte of the header
    temp_hdr[0] ^= (mask[0] & 0x0f);
    // Step 5: Apply mask to the PN field
    for (int i = 0; i < pn_length; i++) {
        temp_hdr[pn_offset_val + i] ^= mask[i + 1];
    }
    // Reallocate output to fit the demasked header length
    uint8_t* tmp_ptr = (uint8_t*)realloc(*output, temp_hdr_len);
    if (!tmp_ptr) {
        perror("Memory allocation failed");
        free(temp_hdr);  // Free the temp buffer before exiting!
        return;
    }
    *output = tmp_ptr;
    memcpy(*output, temp_hdr, temp_hdr_len);
    *output_len = temp_hdr_len;
    free(temp_hdr);  // Free temporary buffer after copying
}





/* =============================================================================
 * Key Derivation (HKDF)
 * =============================================================================
 */

/**
 * @brief HKDF-Extract (RFC 5869).
 *
 * @param salt The salt value.
 * @param salt_len Length of the salt.
 * @param ikm Input keying material.
 * @param ikm_len Length of the IKM.
 * @param prk Output buffer to store the pseudorandom key (PRK).
 * @param prk_len Length of the PRK buffer.
 */
void hkdf_extract(const uint8_t* salt, size_t salt_len,
                  const uint8_t* ikm, size_t ikm_len,
                  uint8_t* prk, size_t prk_len) 
{
    (void)prk_len;  // Usually determined by EVP_sha256 (32 bytes).
    HMAC(EVP_sha256(), salt, salt_len, ikm, ikm_len, prk, NULL);
}

/**
 * @brief HKDF-Expand (RFC 5869).
 *
 * @param prk The pseudorandom key from HKDF-Extract.
 * @param prk_len Length of the PRK.
 * @param info The info field for HKDF expansion.
 * @param info_len Length of the info field.
 * @param output Buffer to store the expanded key material.
 * @param output_len Length of the output buffer.
 */
void hkdf_expand(const uint8_t* prk, size_t prk_len, 
                 const uint8_t* info, size_t info_len, 
                 uint8_t* output, size_t output_len) 
{
    size_t hash_len = EVP_MD_size(EVP_sha256());
    uint8_t t[EVP_MAX_MD_SIZE];  // Enough for any supported hash
    size_t t_len = 0;
    size_t generated = 0;

    for (uint8_t i = 1; generated < output_len; i++) {
        HMAC_CTX* ctx = HMAC_CTX_new();
        if (!ctx) {
            fprintf(stderr, "Error: Failed to create HMAC_CTX\n");
            return;
        }

        HMAC_Init_ex(ctx, prk, prk_len, EVP_sha256(), NULL);

        if (t_len > 0) {
            HMAC_Update(ctx, t, t_len);
        }
        HMAC_Update(ctx, info, info_len);
        HMAC_Update(ctx, &i, 1);

        HMAC_Final(ctx, t, (unsigned int*)&t_len);
        HMAC_CTX_free(ctx);

        size_t copy_len = (output_len - generated > t_len) ? t_len : (output_len - generated);
        memcpy(output + generated, t, copy_len);
        generated += copy_len;
    }
}



/**
 * @brief Derive initial AEAD keys for QUIC using the Initial Salt and HKDF (draft-ietf-quic-tls).
 *
 * @param dcid Destination Connection ID.
 * @param is_client `true` if deriving client keys, `false` if server keys.
 * @param keys Output struct to store derived keys (initial secrets, QUIC key, IV, HP key).
 */
 void derive_initial_keys(const uint8_t* dcid, int dcid_size, bool is_client, QuicCryptoKeys* keys) {
    static const uint8_t initial_salt[] = {
        0x38, 0x76, 0x2c, 0xf7, 0xf5, 0x59, 0x34, 0xb3, 
        0x4d, 0x17, 0x9a, 0xe6, 0xa4, 0xc8, 0x0c, 0xad, 
        0xcc, 0xbb, 0x7f, 0x0a
    };

    static const uint8_t client_key_info[] = {
        0x00, 0x20, 0x0f, 0x74, 0x6c, 0x73, 0x31, 0x33,
        0x20, 0x63, 0x6c, 0x69, 0x65, 0x6e, 0x74, 0x20,
        0x69, 0x6e, 0x00
    };

    static const uint8_t server_key_info[] = {
        0x00, 0x20, 0x0f, 0x74, 0x6c, 0x73, 0x31, 0x33,
        0x20, 0x73, 0x65, 0x72, 0x76, 0x65, 0x72, 0x20,
        0x69, 0x6e, 0x00
    };

    static const uint8_t quic_key_info[] = {
        0x00, 0x10, 0x0e, 0x74, 0x6c, 0x73, 0x31, 0x33,
        0x20, 0x71, 0x75, 0x69, 0x63, 0x20, 0x6b, 0x65,
        0x79, 0x00
    };

    static const uint8_t quic_iv_info[] = {
        0x00, 0x0c, 0x0d, 0x74, 0x6c, 0x73, 0x31, 0x33,
        0x20, 0x71, 0x75, 0x69, 0x63, 0x20, 0x69, 0x76,
        0x00
    };

    static const uint8_t quic_hp_info[] = {
        0x00, 0x10, 0x0d, 0x74, 0x6c, 0x73, 0x31, 0x33,
        0x20, 0x71, 0x75, 0x69, 0x63, 0x20, 0x68, 0x70,
        0x00
    };

    // initial_secret = HKDF-Extract(salt, dcid)
    // NOTE: 'dcid' size typically comes from QUIC header. Ensure correct length is used.
    HMAC(EVP_sha256(), initial_salt, sizeof(initial_salt),
         dcid, dcid_size,
         keys->initial_secret, 
         (unsigned int[]){sizeof(keys->initial_secret)});

    // client_initial_secret = HKDF-Expand(initial_secret, "tls13 client in")
    hkdf_expand(keys->initial_secret, sizeof(keys->initial_secret),
                client_key_info, sizeof(client_key_info),
                keys->client_initial_secret, sizeof(keys->client_initial_secret));

    // server_initial_secret = HKDF-Expand(initial_secret, "tls13 server in")
    hkdf_expand(keys->initial_secret, sizeof(keys->initial_secret),
                server_key_info, sizeof(server_key_info),
                keys->server_initial_secret, sizeof(keys->server_initial_secret));

    // Prepare arguments for parallel HKDF expansions
    HkdfExpandArgs args[6];

    args[0] = (HkdfExpandArgs){
        keys->client_initial_secret, sizeof(keys->client_initial_secret),
        quic_key_info, sizeof(quic_key_info),
        keys->quic_key, sizeof(keys->quic_key)
    };
    args[1] = (HkdfExpandArgs){
        keys->client_initial_secret, sizeof(keys->client_initial_secret),
        quic_iv_info, sizeof(quic_iv_info),
        keys->quic_iv, sizeof(keys->quic_iv)
    };
    args[2] = (HkdfExpandArgs){
        keys->client_initial_secret, sizeof(keys->client_initial_secret),
        quic_hp_info, sizeof(quic_hp_info),
        keys->quic_hp, sizeof(keys->quic_hp)
    };
    args[3] = (HkdfExpandArgs){
        keys->server_initial_secret, sizeof(keys->server_initial_secret),
        quic_key_info, sizeof(quic_key_info),
        keys->quic_key_server, sizeof(keys->quic_key_server)
    };
    args[4] = (HkdfExpandArgs){
        keys->server_initial_secret, sizeof(keys->server_initial_secret),
        quic_iv_info, sizeof(quic_iv_info),
        keys->quic_iv_server, sizeof(keys->quic_iv_server)
    };
    args[5] = (HkdfExpandArgs){
        keys->server_initial_secret, sizeof(keys->server_initial_secret),
        quic_hp_info, sizeof(quic_hp_info),
        keys->quic_hp_server, sizeof(keys->quic_hp_server)
    };
    
    // Run HKDF expansions sequentially in a single thread
    for (int i = 0; i < 6; i++) {
        hkdf_expand_thread(&args[i]);  // Directly call the function instead of creating threads
    }

    // printf("\n");

}

/* =============================================================================
 * AEAD Decryption
 * =============================================================================
 */

/**
 * @brief Generate AEAD nonce by XORing the IV with the packet number.
 *
 * @param iv Initialization vector (IV).
 * @param iv_len Length of the IV (usually 12 for AES-GCM).
 * @param packet_number The QUIC packet number (62 bits).
 * @param nonce Output buffer to store the generated nonce (must be at least iv_len).
 */
void generate_aead_nonce(const uint8_t *iv, size_t iv_len, 
                         uint64_t packet_number, uint8_t *nonce) 
{
    // Ensure packet number fits within 62 bits
    if (packet_number >= (1ULL << 62)) {
        fprintf(stderr, "Packet number exceeds 62 bits.\n");
        exit(EXIT_FAILURE);
    }

    // Convert packet_number to network byte order (big-endian)
    uint8_t packet_number_bytes[8];
    for (int i = 0; i < 8; i++) {
        packet_number_bytes[i] = (packet_number >> (8 * (7 - i))) & 0xFF;
    }

    // Create a padded PN array matching iv_len (commonly 12)
    uint8_t padded_packet_number[iv_len];
    memset(padded_packet_number, 0, iv_len);
    memcpy(padded_packet_number + (iv_len - 8), packet_number_bytes, 8);

    // XOR with the IV
    for (size_t i = 0; i < iv_len; i++) {
        nonce[i] = iv[i] ^ padded_packet_number[i];
    }
}

/**
 * @brief Decrypt data using AES-GCM.
 *
 * @param encryption_key Pointer to the AEAD key (16 bytes for AES-128, etc.).
 * @param key_len Length of the key in bytes.
 * @param iv Pointer to the IV.
 * @param iv_len Length of the IV (commonly 12).
 * @param associated_data Additional authenticated data (AAD).
 * @param ad_len Length of the AAD.
 * @param ciphertext_with_tag The ciphertext followed by the 16-byte GCM tag.
 * @param ciphertext_with_tag_len Length of the combined ciphertext+tag.
 * @param plaintext Output buffer for decrypted data.
 * @return The length of decrypted plaintext on success, or -1 on failure.
 */
int aead_decrypt(
    const uint8_t *encryption_key, uint32_t key_len,
    const uint8_t *iv, uint32_t iv_len,
    const uint8_t *associated_data, uint32_t ad_len,
    const uint8_t *ciphertext_with_tag, uint32_t ciphertext_with_tag_len,
    uint8_t *plaintext)
{

    // Separate ciphertext and tag
    uint32_t ciphertext_len = ciphertext_with_tag_len - 16;
    const uint8_t *ciphertext = ciphertext_with_tag;
    const uint8_t *tag = ciphertext_with_tag + ciphertext_len;
    uint8_t out[ciphertext_len];

    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) {
        printf("Failed to create EVP_CIPHER_CTX\n");
        return -1;
    }

    const EVP_CIPHER *cipher = (key_len == 16) ? EVP_aes_128_gcm() : EVP_aes_256_gcm();
    if (EVP_DecryptInit_ex(ctx, cipher, NULL, NULL, NULL) != 1) {
        printf("DecryptInit failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, iv_len, NULL) != 1) {
        printf("IV length setting failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    if (EVP_DecryptInit_ex(ctx, NULL, NULL, encryption_key, iv) != 1) {
        printf("DecryptInit with key and IV failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    int len, plaintext_len = 0;
    if (associated_data && ad_len > 0) {
        if (EVP_DecryptUpdate(ctx, NULL, &len, associated_data, ad_len) != 1) {
            printf("AAD update failed\n");
            EVP_CIPHER_CTX_free(ctx);
            return -1;
        }
    }

    if (EVP_DecryptUpdate(ctx, out, &len, ciphertext, ciphertext_len) != 1) {
        printf("Decryption failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }
    plaintext_len = len;

    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, 16, (void *)tag) != 1) {
        printf("Tag setting failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    if (EVP_DecryptFinal_ex(ctx, out + len, &len) != 1) {
        printf("Decryption finalization failed - authentication failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }
    // printf("==================================Decryption Success===============================");

    plaintext_len += len;

    EVP_CIPHER_CTX_free(ctx);
    // printf("out: ");
    // for (uint32_t i = 0; i < sizeof(out); i++) {
    //     printf("%02x", out[i]);
    // }

    memcpy(plaintext, out, plaintext_len);

    return plaintext_len;
}


// AEAD Encryption using AES-GCM
int aead_encrypt(
    const uint8_t *encryption_key, uint32_t key_len,
    const uint8_t *iv, uint32_t iv_len,
    const uint8_t *associated_data, uint32_t ad_len,
    const uint8_t *plaintext, uint32_t plaintext_len,
    uint8_t *ciphertext_with_tag)
{
    EVP_CIPHER_CTX *ctx = EVP_CIPHER_CTX_new();
    if (!ctx) {
        printf("Failed to create EVP_CIPHER_CTX\n");
        return -1;
    }

    const EVP_CIPHER *cipher = (key_len == 16) ? EVP_aes_128_gcm() : EVP_aes_256_gcm();
    if (EVP_EncryptInit_ex(ctx, cipher, NULL, NULL, NULL) != 1) {
        printf("EncryptInit failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, iv_len, NULL) != 1) {
        printf("IV length setting failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    if (EVP_EncryptInit_ex(ctx, NULL, NULL, encryption_key, iv) != 1) {
        printf("EncryptInit with key and IV failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    int len, ciphertext_len = 0;
    uint8_t out[plaintext_len];

    if (associated_data && ad_len > 0) {
        if (EVP_EncryptUpdate(ctx, NULL, &len, associated_data, ad_len) != 1) {
            printf("AAD update failed\n");
            EVP_CIPHER_CTX_free(ctx);
            return -1;
        }
    }

    if (EVP_EncryptUpdate(ctx, out, &len, plaintext, plaintext_len) != 1) {
        printf("Encryption failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }
    ciphertext_len = len;

    if (EVP_EncryptFinal_ex(ctx, out + len, &len) != 1) {
        printf("Encryption finalization failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }
    ciphertext_len += len;

    // Get the GCM authentication tag (16 bytes)
    uint8_t tag[16];
    if (EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_GET_TAG, 16, tag) != 1) {
        printf("Tag retrieval failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }
    EVP_CIPHER_CTX_free(ctx);

    // Copy ciphertext and tag to the output buffer
    memcpy(ciphertext_with_tag, out, ciphertext_len);
    memcpy(ciphertext_with_tag + ciphertext_len, tag, 16);
    
    return ciphertext_len + 16;

}