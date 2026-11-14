#include <stdio.h>
#include <string.h>
#include <openssl/evp.h>
#include <openssl/err.h>

/*
 * aead_decrypt
 *
 * Parameters:
 *   ciphertext     - pointer to the ciphertext to decrypt.
 *   ciphertext_len - length of the ciphertext in bytes.
 *   aad            - pointer to additional authenticated data (can be NULL if not used).
 *   aad_len        - length of the AAD in bytes.
 *   tag            - pointer to the 16-byte authentication tag.
 *   key            - pointer to the 32-byte (256-bit) decryption key.
 *   iv             - pointer to the initialization vector (nonce).
 *   iv_len         - length of the IV in bytes (often 12 bytes for GCM).
 *   plaintext      - pointer to a buffer where the decrypted plaintext will be written.
 *
 * Returns:
 *   On success: the number of plaintext bytes written.
 *   On failure: -1.
 */
int aead_decrypt(const unsigned char *ciphertext, int ciphertext_len,
                 const unsigned char *aad, int aad_len,
                 const unsigned char *tag,
                 const unsigned char *key,
                 const unsigned char *iv, int iv_len,
                 unsigned char *plaintext)
{
    EVP_CIPHER_CTX *ctx = NULL;
    int len = 0;
    int plaintext_len = 0;
    int ret = 0;

    /* Create and initialise the context */
    if (!(ctx = EVP_CIPHER_CTX_new())) {
        fprintf(stderr, "Error: Could not create cipher context\n");
        return -1;
    }

    /* Initialise decryption operation with AES-256-GCM */
    if (1 != EVP_DecryptInit_ex(ctx, EVP_aes_256_gcm(), NULL, NULL, NULL)) {
        fprintf(stderr, "Error: DecryptInit failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    /* Set IV length if not the default 12 bytes */
    if (1 != EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_IVLEN, iv_len, NULL)) {
        fprintf(stderr, "Error: Could not set IV length\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    /* Initialise key and IV */
    if (1 != EVP_DecryptInit_ex(ctx, NULL, NULL, key, iv)) {
        fprintf(stderr, "Error: Could not initialise key and IV\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    /* Provide AAD data (if any) */
    if (aad && aad_len > 0) {
        if (1 != EVP_DecryptUpdate(ctx, NULL, &len, aad, aad_len)) {
            fprintf(stderr, "Error: AAD processing failed\n");
            EVP_CIPHER_CTX_free(ctx);
            return -1;
        }
    }

    /* Decrypt the ciphertext */
    if (1 != EVP_DecryptUpdate(ctx, plaintext, &len, ciphertext, ciphertext_len)) {
        fprintf(stderr, "Error: Decryption update failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }
    plaintext_len = len;

    /* Set expected tag value for GCM authentication */
    if (1 != EVP_CIPHER_CTX_ctrl(ctx, EVP_CTRL_GCM_SET_TAG, 16, (void *)tag)) {
        fprintf(stderr, "Error: Setting tag failed\n");
        EVP_CIPHER_CTX_free(ctx);
        return -1;
    }

    /* Finalise decryption. If the tag does not verify, this will fail. */
    ret = EVP_DecryptFinal_ex(ctx, plaintext + len, &len);
    EVP_CIPHER_CTX_free(ctx);

    if (ret > 0) {
        plaintext_len += len;
        return plaintext_len;
    } else {
        /* Authentication failed */
        fprintf(stderr, "Error: Decryption failed (authentication tag mismatch)\n");
        return -1;
    }
}

/* Example usage */

int main(void)
{
    /* Example key, IV, AAD, ciphertext, and tag.
     * In a real scenario, these values should come from your encryption routine.
     */
    unsigned char key[32] = { /* 32 bytes key */ };
    unsigned char iv[12] = { /* 12 bytes IV */ };
    unsigned char aad[] = { /* any AAD bytes if used */ };
    unsigned char ciphertext[] = { /* your ciphertext bytes */ };
    unsigned char tag[16] = { /* 16 bytes authentication tag */ };

    /* Buffer for the plaintext. Make sure it is large enough. */
    unsigned char plaintext[1024] = {0};

    int decrypted_len = aead_decrypt(ciphertext, sizeof(ciphertext),
                                     aad, sizeof(aad),
                                     tag, key, iv, sizeof(iv),
                                     plaintext);
    if (decrypted_len < 0) {
        fprintf(stderr, "Decryption failed\n");
        return 1;
    }

    printf("Decrypted text (%d bytes):\n", decrypted_len);
    fwrite(plaintext, 1, decrypted_len, stdout);
    printf("\n");

    return 0;
}
