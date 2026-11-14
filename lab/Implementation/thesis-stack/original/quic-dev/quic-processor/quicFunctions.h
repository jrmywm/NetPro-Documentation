#ifndef QUIC_FUNCTIONS_H
#define QUIC_FUNCTIONS_H

#include <openssl/evp.h>
#include <openssl/aes.h>
#include <openssl/hmac.h>
#include <openssl/kdf.h>
#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <arpa/inet.h>
#include <pthread.h>
#include <time.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ====================== */
/*      CONSTANTS         */
/* ====================== */

/**
 * Size of the salt used in key derivation.
 */
#define SALT_SIZE 20

/**
 * Size of the secret used in key derivation.
 */
#define SECRET_SIZE 32

/**
 * Size of the QUIC key used for encryption/decryption.
 */
#define QUIC_KEY_SIZE 16

/**
 * Size of the QUIC Initialization Vector (IV) used for encryption/decryption.
 */
#define QUIC_IV_SIZE 12

/**
 * Size of the QUIC Header Protection (HP) key.
 */
#define QUIC_HP_SIZE 16

/* ====================== */
/*      DATA STRUCTURES   */
/* ====================== */

/**
 * Structure containing all cryptographic keys necessary for QUIC encryption/decryption.
 */
typedef struct {
    uint8_t initial_secret[SECRET_SIZE];          /**< Initial secret derived from the connection ID. */
    uint8_t client_initial_secret[SECRET_SIZE];   /**< Client initial secret. */
    uint8_t server_initial_secret[SECRET_SIZE];   /**< Server initial secret. */
    uint8_t quic_key[QUIC_KEY_SIZE];              /**< QUIC encryption key for the client. */
    uint8_t quic_iv[QUIC_IV_SIZE];                /**< QUIC IV for the client. */
    uint8_t quic_hp[QUIC_HP_SIZE];                /**< QUIC header protection key for the client. */
    uint8_t quic_key_server[QUIC_KEY_SIZE];       /**< QUIC encryption key for the server. */
    uint8_t quic_iv_server[QUIC_IV_SIZE];         /**< QUIC IV for the server. */
    uint8_t quic_hp_server[QUIC_HP_SIZE];         /**< QUIC header protection key for the server. */
} QuicCryptoKeys;

/**
 * Structure containing arguments for HKDF expand operation.
 */
typedef struct {
    const uint8_t* secret;        /**< Input secret for HKDF. */
    size_t secret_len;            /**< Length of the input secret. */
    const uint8_t* info;          /**< Additional info for HKDF. */
    size_t info_len;              /**< Length of the additional info. */
    uint8_t* output;              /**< Output buffer for the derived key. */
    size_t output_len;            /**< Length of the output buffer. */
} HkdfExpandArgs;

/* ====================== */
/*    HEADER OPERATIONS   */
/* ====================== */

/**
 * Extracts the packet number length from a demasked QUIC header.
 *
 * @param demasked_header The demasked QUIC header.
 * @return The length of the packet number in bytes.
 */
int pn_length(const uint8_t* demasked_header);

/**
 * Extracts the packet number from a demasked QUIC header.
 *
 * @param demasked_header The demasked QUIC header.
 * @param pn_length Length of the packet number.
 * @param header_length Length of the header.
 * @return The extracted packet number.
 */
uint32_t pn(const uint8_t* demasked_header, int pn_length, int header_length);

/**
 * Retrieves the offset of the packet number in a QUIC header.
 *
 * @param header The QUIC header.
 * @param header_len Length of the header.
 * @return The offset of the packet number.
 */
int get_pn_offset(const uint8_t* header, size_t header_len);

/**
 * Extracts the Destination Connection ID (DCID) from a QUIC header.
 *
 * @param header The QUIC header.
 * @param is_client Whether the packet is from a client.
 * @param dcid_length Pointer to store the length of the DCID.
 * @return A pointer to the DCID.
 */
uint8_t* get_dcid(const uint8_t* header, bool is_client, uint8_t* dcid_length);

/**
 * Generates a nonce for AEAD encryption/decryption.
 *
 * @param iv The initialization vector.
 * @param iv_len Length of the IV.
 * @param packet_number The packet number.
 * @param nonce Output buffer for the generated nonce.
 */
void generate_aead_nonce(
    const uint8_t* iv,
    size_t iv_len,
    uint64_t packet_number,
    uint8_t* nonce
);

/* ====================== */
/*  HEADER PROTECTION     */
/* ====================== */

/**
 * Unmasks the header of a protected QUIC packet.
 *
 * @param protected_packet The protected QUIC packet.
 * @param packet_len Length of the packet.
 * @param hp_key The header protection key.
 * @param output Output buffer for the unmasked header.
 * @param output_len Length of the output buffer.
 */
void header_unmask(
    const uint8_t* protected_packet,
    size_t packet_len,
    const uint8_t* hp_key,
    uint8_t** output,
    size_t* output_len
);

/**
 * Masks the header of a protected QUIC packet.
 *
 * @param protected_packet The protected QUIC packet.
 * @param packet_len Length of the packet.
 * @param header_offset Offset of the header in the packet.
 * @param hp_key The header protection key.
 * @param output Output buffer for the masked header.
 * @param output_len Length of the output buffer.
 */
void header_mask(
    const uint8_t* protected_packet,
    size_t packet_len,
    int header_offset,
    const uint8_t* hp_key,
    uint8_t** output,
    size_t* output_len
);

/* ====================== */
/*  KEY DERIVATION        */
/* ====================== */

/**
 * Performs HKDF extract operation.
 *
 * @param salt The salt for HKDF.
 * @param salt_len Length of the salt.
 * @param ikm The input key material.
 * @param ikm_len Length of the input key material.
 * @param prk Output buffer for the pseudorandom key.
 * @param prk_len Length of the pseudorandom key.
 */
void hkdf_extract(
    const uint8_t* salt,
    size_t salt_len,
    const uint8_t* ikm,
    size_t ikm_len,
    uint8_t* prk,
    size_t prk_len
);

/**
 * Performs HKDF expand operation.
 *
 * @param prk The pseudorandom key.
 * @param prk_len Length of the pseudorandom key.
 * @param info Additional info for HKDF.
 * @param info_len Length of the additional info.
 * @param okm Output buffer for the derived key.
 * @param okm_len Length of the output key material.
 */
void hkdf_expand(
    const uint8_t* prk,
    size_t prk_len,
    const uint8_t* info,
    size_t info_len,
    uint8_t* okm,
    size_t okm_len
);

/**
 * Derives initial cryptographic keys using the Destination Connection ID (DCID).
 *
 * @param dcid The Destination Connection ID.
 * @param dcid_size Length of the DCID.
 * @param is_client Whether the keys are for a client.
 * @param keys Pointer to the QuicCryptoKeys structure to store derived keys.
 */
void derive_initial_keys(const uint8_t* dcid, int dcid_size, bool is_client, QuicCryptoKeys* keys);

/* ====================== */
/*  ENCRYPTION/DECRYPTION */
/* ====================== */

/**
 * Decrypts AEAD-encrypted data.
 *
 * @param encryption_key The encryption key.
 * @param key_len Length of the encryption key.
 * @param iv The initialization vector.
 * @param iv_len Length of the IV.
 * @param associated_data The associated data.
 * @param ad_len Length of the associated data.
 * @param ciphertext_with_tag The ciphertext including the authentication tag.
 * @param ciphertext_with_tag_len Length of the ciphertext with tag.
 * @param plaintext Output buffer for the decrypted plaintext.
 * @return 0 on success, non-zero on failure.
 */
int aead_decrypt(
    const uint8_t* encryption_key,
    uint32_t key_len,
    const uint8_t* iv,
    uint32_t iv_len,
    const uint8_t* associated_data,
    uint32_t ad_len,
    const uint8_t* ciphertext_with_tag,
    uint32_t ciphertext_with_tag_len,
    uint8_t* plaintext
);

/**
 * Encrypts data using AEAD.
 *
 * @param encryption_key The encryption key.
 * @param key_len Length of the encryption key.
 * @param iv The initialization vector.
 * @param iv_len Length of the IV.
 * @param associated_data The associated data.
 * @param ad_len Length of the associated data.
 * @param plaintext The plaintext to encrypt.
 * @param plaintext_len Length of the plaintext.
 * @param ciphertext_with_tag Output buffer for the ciphertext including the authentication tag.
 * @return 0 on success, non-zero on failure.
 */
int aead_encrypt(
    const uint8_t* encryption_key,
    uint32_t key_len,
    const uint8_t* iv,
    uint32_t iv_len,
    const uint8_t* associated_data,
    uint32_t ad_len,
    const uint8_t* plaintext,
    uint32_t plaintext_len,
    uint8_t* ciphertext_with_tag
);

/* ====================== */
/*  UTILITY FUNCTIONS     */
/* ====================== */

/**
 * Extracts the domain name from a QUIC packet.
 *
 * @param packet The QUIC packet.
 * @param packet_len Length of the packet.
 * @param isClient Whether the packet is from a client.
 * @param keys Pointer to the QuicCryptoKeys structure.
 * @return The extracted domain name as a string.
 */
char* getDomain(
    const uint8_t* packet,
    int packet_len,
    bool isClient,
    QuicCryptoKeys* keys
);

/**
 * Crafts a QUIC Initial Connection Close Packet.
 *
 * @param scid The Source Connection ID.
 * @param scid_len Length of the SCID.
 * @param dcid The Destination Connection ID.
 * @param dcid_len Length of the DCID.
 * @param output Output buffer for the crafted packet.
 * @param output_len Length of the output buffer.
 * @param keys Pointer to the QuicCryptoKeys structure.
 * @param to_server Whether the packet is intended for the server.
 */
void quic_payload_crafter(
    const uint8_t* scid,
    uint8_t scid_len,
    const uint8_t* dcid,
    uint8_t dcid_len,
    uint8_t* output,
    uint32_t* output_len,
    QuicCryptoKeys* keys,
    bool to_server
);

#endif // QUIC_FUNCTIONS_H