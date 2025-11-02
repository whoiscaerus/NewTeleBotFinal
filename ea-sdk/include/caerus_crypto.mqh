//+------------------------------------------------------------------+
//| Caerus Crypto Module - AES-256-GCM AEAD Decryption                |
//| PR-042: Encrypted Signal Transport                               |
//+------------------------------------------------------------------+
//| Decrypts AES-256-GCM (AEAD) envelopes from poll response signals. |
//| Matches Python cryptography.hazmat.primitives.ciphers.aead API.  |
//+------------------------------------------------------------------+

#ifndef CAERUS_CRYPTO_MQH
#define CAERUS_CRYPTO_MQH

#include <Crypto\Crypto.mqh>
#include <String\String.mqh>

//+------------------------------------------------------------------+
//| Base64 Decoding Helper                                           |
//+------------------------------------------------------------------+
class Base64Decoder {
private:
    // Base64 alphabet
    static const string ALPHABET;

public:
    // Decode base64 string to binary
    static uchar[] Decode(const string encoded) {
        int len = StringLen(encoded);
        int padLen = 0;

        // Count padding characters
        if (len > 0 && encoded[len-1] == '=') padLen++;
        if (len > 1 && encoded[len-2] == '=') padLen++;

        // Calculate decoded length
        int decodedLen = (len / 4) * 3 - padLen;
        uchar result[];
        ArrayResize(result, decodedLen);

        // Decode groups of 4 characters
        int outIdx = 0;
        for (int i = 0; i < len; i += 4) {
            uchar b1 = CharToBase64Value(encoded[i]);
            uchar b2 = (i+1 < len) ? CharToBase64Value(encoded[i+1]) : 0;
            uchar b3 = (i+2 < len && encoded[i+2] != '=') ? CharToBase64Value(encoded[i+2]) : 0;
            uchar b4 = (i+3 < len && encoded[i+3] != '=') ? CharToBase64Value(encoded[i+3]) : 0;

            // Combine 4 base64 chars into 3 bytes
            if (outIdx < decodedLen) result[outIdx++] = (uchar)((b1 << 2) | (b2 >> 4));
            if (outIdx < decodedLen) result[outIdx++] = (uchar)(((b2 & 0x0F) << 4) | (b3 >> 2));
            if (outIdx < decodedLen) result[outIdx++] = (uchar)(((b3 & 0x03) << 6) | b4);
        }

        return result;
    }

private:
    // Convert base64 character to 6-bit value
    static uchar CharToBase64Value(uchar c) {
        if (c >= 'A' && c <= 'Z') return c - 'A';          // 0-25
        if (c >= 'a' && c <= 'z') return c - 'a' + 26;     // 26-51
        if (c >= '0' && c <= '9') return c - '0' + 52;     // 52-61
        if (c == '+') return 62;                            // 62
        if (c == '/') return 63;                            // 63
        return 0;                                            // Padding or invalid
    }
};

//+------------------------------------------------------------------+
//| AESGCM Cipher Class                                              |
//+------------------------------------------------------------------+
class AESGCM {
private:
    uchar key[];        // 32-byte AES-256 key
    int keyLen;

public:
    // Constructor - initialize with 32-byte key
    AESGCM(const uchar &keyBytes[]) {
        keyLen = ArraySize(keyBytes);
        if (keyLen != 32) {
            PrintFormat("ERROR: AESGCM requires 32-byte key, got %d", keyLen);
        }
        ArrayCopy(key, keyBytes);
    }

    // Decrypt AEAD cipher
    // ciphertext: encrypted data with authentication tag appended
    // nonce: 12-byte nonce
    // aad: additional authenticated data (not encrypted)
    // plaintext: output buffer for decrypted data
    // returns: true if decryption successful and tag verified, false otherwise
    bool Decrypt(const uchar &ciphertext[],
                 const uchar &nonce[],
                 const uchar &aad[],
                 uchar &plaintext[]) {

        // Validate inputs
        if (ArraySize(nonce) != 12) {
            PrintFormat("ERROR: GCM nonce must be 12 bytes, got %d", ArraySize(nonce));
            return false;
        }

        if (ArraySize(ciphertext) < 16) {
            PrintFormat("ERROR: Ciphertext too short (must include 16-byte tag)");
            return false;
        }

        // Split ciphertext and tag (last 16 bytes are authentication tag)
        int ctLen = ArraySize(ciphertext) - 16;
        uchar ct[];
        uchar tag[];
        ArrayResize(ct, ctLen);
        ArrayResize(tag, 16);

        for (int i = 0; i < ctLen; i++) ct[i] = ciphertext[i];
        for (int i = 0; i < 16; i++) tag[i] = ciphertext[ctLen + i];

        // Create cipher context
        CryptoCipherContext context;
        if (!context.Create(_CRYPT_AES, _CRYPT_MODE_GCM)) {
            PrintFormat("ERROR: Failed to create GCM context");
            return false;
        }

        // Set key and nonce
        if (!context.SetKey(key, keyLen)) {
            PrintFormat("ERROR: Failed to set GCM key");
            return false;
        }

        if (!context.SetIV(nonce, ArraySize(nonce))) {
            PrintFormat("ERROR: Failed to set GCM nonce");
            return false;
        }

        // Add authenticated data
        if (ArraySize(aad) > 0) {
            if (!context.AADAdd(aad, ArraySize(aad))) {
                PrintFormat("ERROR: Failed to add AAD");
                return false;
            }
        }

        // Decrypt ciphertext
        ArrayResize(plaintext, ctLen);
        if (!context.Decrypt(ct, plaintext)) {
            PrintFormat("ERROR: GCM decryption failed");
            return false;
        }

        // Verify authentication tag
        if (!context.VerifyTag(tag)) {
            PrintFormat("ERROR: GCM tag verification failed - ciphertext tampered or AAD mismatch");
            return false;
        }

        return true;
    }
};

//+------------------------------------------------------------------+
//| Signal Envelope Class - PR-042                                   |
//+------------------------------------------------------------------+
//| Manages decryption of encrypted signal envelopes from poll.      |
//+------------------------------------------------------------------+
class SignalEnvelopeDecryptor {
private:
    uchar encryptionKey[];     // 32-byte encryption key from registration

public:
    // Constructor - initialize with base64-encoded encryption key
    SignalEnvelopeDecryptor(const string &base64Key) {
        Base64Decoder decoder;
        uchar decodedKey[] = decoder.Decode(base64Key);

        if (ArraySize(decodedKey) != 32) {
            PrintFormat("ERROR: Encryption key must be 32 bytes, got %d", ArraySize(decodedKey));
        }
        ArrayCopy(encryptionKey, decodedKey);
    }

    // Decrypt signal envelope
    // ciphertext_b64: base64-encoded AES-256-GCM ciphertext (includes tag)
    // nonce_b64: base64-encoded 12-byte nonce
    // aad: device_id (additional authenticated data)
    // plaintext: output JSON string
    // returns: true if successful
    bool DecryptSignal(const string &ciphertext_b64,
                      const string &nonce_b64,
                      const string &aad,
                      string &plaintext) {

        // Decode ciphertext and nonce
        Base64Decoder decoder;
        uchar ciphertext[] = decoder.Decode(ciphertext_b64);
        uchar nonce[] = decoder.Decode(nonce_b64);
        uchar aadBytes[];

        // Convert AAD string to bytes
        int aadLen = StringLen(aad);
        ArrayResize(aadBytes, aadLen);
        for (int i = 0; i < aadLen; i++) {
            aadBytes[i] = (uchar)aad[i];
        }

        // Create cipher and decrypt
        AESGCM cipher(encryptionKey);
        uchar decrypted[];

        if (!cipher.Decrypt(ciphertext, nonce, aadBytes, decrypted)) {
            return false;
        }

        // Convert decrypted bytes to string (JSON)
        plaintext = CharArrayToString(decrypted);
        return true;
    }

private:
    // Convert uchar array to string
    static string CharArrayToString(const uchar &data[]) {
        int len = ArraySize(data);
        string result = "";
        for (int i = 0; i < len; i++) {
            result += CharToString((uchar)data[i]);
        }
        return result;
    }
};

#endif // CAERUS_CRYPTO_MQH

//+------------------------------------------------------------------+
//| USAGE EXAMPLE                                                     |
//+------------------------------------------------------------------+
//|
//| When device registers:
//|   response = POST /api/v1/devices
//|   encryption_key = response.encryption_key  // base64-encoded 32-byte key
//|
//| When polling signals:
//|   response = GET /api/v1/client/poll
//|   signal = response.approvals[0]
//|
//|   // Decrypt using SDK
//|   SignalEnvelopeDecryptor decryptor(encryption_key);
//|   string plaintext = "";
//|   if (decryptor.DecryptSignal(signal.ciphertext, signal.nonce, signal.aad, plaintext)) {
//|       // Parse plaintext as JSON
//|       // {"approval_id": "...", "instrument": "XAUUSD", "side": "buy", ...}
//|   } else {
//|       Print("Decryption failed - signal tampered or key mismatch");
//|   }
//|
//+------------------------------------------------------------------+
