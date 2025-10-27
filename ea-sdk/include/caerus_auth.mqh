//+------------------------------------------------------------------+
//| Caerus Authentication Module for MT5 EA                         |
//| HMAC-SHA256 signing + nonce management                          |
//| Secure communication with Caerus API backend                    |
//+------------------------------------------------------------------+

#ifndef __CAERUS_AUTH_MQH__
#define __CAERUS_AUTH_MQH__

#include <stdlib.mqh>
#include <string.mqh>

//+------------------------------------------------------------------+
//| Base64 Encoding Helper                                          |
//+------------------------------------------------------------------+

class Base64Encoder
{
private:
    static const string BASE64_ALPHABET;

public:
    static string Encode(uchar &data[])
    {
        string result = "";
        int i = 0;
        int len = ArraySize(data);

        while (i + 2 < len)
        {
            uchar b1 = data[i];
            uchar b2 = data[i + 1];
            uchar b3 = data[i + 2];

            result += BASE64_ALPHABET[b1 >> 2];
            result += BASE64_ALPHABET[((b1 & 0x03) << 4) | (b2 >> 4)];
            result += BASE64_ALPHABET[((b2 & 0x0F) << 2) | (b3 >> 6)];
            result += BASE64_ALPHABET[b3 & 0x3F];

            i += 3;
        }

        if (i < len)
        {
            uchar b1 = data[i];
            result += BASE64_ALPHABET[b1 >> 2];

            if (i + 1 < len)
            {
                uchar b2 = data[i + 1];
                result += BASE64_ALPHABET[((b1 & 0x03) << 4) | (b2 >> 4)];
                result += BASE64_ALPHABET[(b2 & 0x0F) << 2];
                result += "=";
            }
            else
            {
                result += BASE64_ALPHABET[(b1 & 0x03) << 4];
                result += "==";
            }
        }

        return result;
    }
};

const string Base64Encoder::BASE64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

//+------------------------------------------------------------------+
//| SHA256 Implementation (Based on FIPS 180-4)                    |
//+------------------------------------------------------------------+

class SHA256
{
private:
    static const uint32 K[];
    uint32 h0, h1, h2, h3, h4, h5, h6, h7;
    uint32 w[64];

    static uint32 rotr(uint32 x, uint shift)
    {
        return (x >> shift) | (x << (32 - shift));
    }

    static uint32 ch(uint32 x, uint32 y, uint32 z)
    {
        return (x & y) ^ ((~x) & z);
    }

    static uint32 maj(uint32 x, uint32 y, uint32 z)
    {
        return (x & y) ^ (x & z) ^ (y & z);
    }

    static uint32 Sigma0(uint32 x)
    {
        return rotr(x, 2) ^ rotr(x, 13) ^ rotr(x, 22);
    }

    static uint32 Sigma1(uint32 x)
    {
        return rotr(x, 6) ^ rotr(x, 11) ^ rotr(x, 25);
    }

    static uint32 gamma0(uint32 x)
    {
        return rotr(x, 7) ^ rotr(x, 18) ^ (x >> 3);
    }

    static uint32 gamma1(uint32 x)
    {
        return rotr(x, 17) ^ rotr(x, 19) ^ (x >> 10);
    }

public:
    SHA256()
    {
        h0 = 0x6a09e667;
        h1 = 0xbb67ae85;
        h2 = 0x3c6ef372;
        h3 = 0xa54ff53a;
        h4 = 0x510e527f;
        h5 = 0x9b05688c;
        h6 = 0x1f83d9ab;
        h7 = 0x5be0cd19;
    }

    void Update(uchar &data[])
    {
        int len = ArraySize(data);

        // Process each 64-byte block
        int num_blocks = (len + 8) / 64 + 1;

        for (int block = 0; block < num_blocks; block++)
        {
            // Clear working variables
            for (int i = 0; i < 64; i++) w[i] = 0;

            // Copy data into first 16 words
            for (int i = 0; i < 16; i++)
            {
                int pos = block * 64 + i * 4;
                uint32 val = 0;

                if (pos < len) val |= ((uint32)data[pos]) << 24;
                if (pos + 1 < len) val |= ((uint32)data[pos + 1]) << 16;
                if (pos + 2 < len) val |= ((uint32)data[pos + 2]) << 8;
                if (pos + 3 < len) val |= ((uint32)data[pos + 3]);

                w[i] = val;
            }

            // Extend the first 16 words into the remaining 48 words
            for (int i = 16; i < 64; i++)
            {
                w[i] = gamma1(w[i - 2]) + w[i - 7] + gamma0(w[i - 15]) + w[i - 16];
            }

            // Initialize working variables
            uint32 a = h0;
            uint32 b = h1;
            uint32 c = h2;
            uint32 d = h3;
            uint32 e = h4;
            uint32 f = h5;
            uint32 g = h6;
            uint32 h = h7;

            // Main loop
            for (int i = 0; i < 64; i++)
            {
                uint32 T1 = h + Sigma1(e) + ch(e, f, g) + K[i] + w[i];
                uint32 T2 = Sigma0(a) + maj(a, b, c);
                h = g;
                g = f;
                f = e;
                e = d + T1;
                d = c;
                c = b;
                b = a;
                a = T1 + T2;
            }

            h0 += a;
            h1 += b;
            h2 += c;
            h3 += d;
            h4 += e;
            h5 += f;
            h6 += g;
            h7 += h;
        }
    }

    void GetDigest(uchar &digest[])
    {
        ArrayResize(digest, 32);

        // Store hash as big-endian bytes
        digest[0] = (uchar)(h0 >> 24);
        digest[1] = (uchar)(h0 >> 16);
        digest[2] = (uchar)(h0 >> 8);
        digest[3] = (uchar)h0;

        digest[4] = (uchar)(h1 >> 24);
        digest[5] = (uchar)(h1 >> 16);
        digest[6] = (uchar)(h1 >> 8);
        digest[7] = (uchar)h1;

        digest[8] = (uchar)(h2 >> 24);
        digest[9] = (uchar)(h2 >> 16);
        digest[10] = (uchar)(h2 >> 8);
        digest[11] = (uchar)h2;

        digest[12] = (uchar)(h3 >> 24);
        digest[13] = (uchar)(h3 >> 16);
        digest[14] = (uchar)(h3 >> 8);
        digest[15] = (uchar)h3;

        digest[16] = (uchar)(h4 >> 24);
        digest[17] = (uchar)(h4 >> 16);
        digest[18] = (uchar)(h4 >> 8);
        digest[19] = (uchar)h4;

        digest[20] = (uchar)(h5 >> 24);
        digest[21] = (uchar)(h5 >> 16);
        digest[22] = (uchar)(h5 >> 8);
        digest[23] = (uchar)h5;

        digest[24] = (uchar)(h6 >> 24);
        digest[25] = (uchar)(h6 >> 16);
        digest[26] = (uchar)(h6 >> 8);
        digest[27] = (uchar)h6;

        digest[28] = (uchar)(h7 >> 24);
        digest[29] = (uchar)(h7 >> 16);
        digest[30] = (uchar)(h7 >> 8);
        digest[31] = (uchar)h7;
    }
};

const uint32 SHA256::K[] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
};

//+------------------------------------------------------------------+
//| HMAC-SHA256 Implementation                                      |
//+------------------------------------------------------------------+

class HMACSHA256
{
private:
    static const int BLOCK_SIZE = 64;
    static const int HASH_SIZE = 32;

public:
    static void ComputeHMAC(
        const string &message,
        const string &key,
        uchar &hmac[]
    )
    {
        uchar key_bytes[];
        uchar msg_bytes[];
        uchar padded_key[];

        // Convert strings to bytes
        StringToCharArray(key, key_bytes);
        StringToCharArray(message, msg_bytes);

        // Prepare key (pad or hash if necessary)
        if (ArraySize(key_bytes) > BLOCK_SIZE)
        {
            SHA256 sha;
            sha.Update(key_bytes);
            sha.GetDigest(key_bytes);
        }

        // Pad key to block size
        ArrayResize(padded_key, BLOCK_SIZE);
        for (int i = 0; i < BLOCK_SIZE; i++)
        {
            padded_key[i] = 0x00;
        }
        for (int i = 0; i < ArraySize(key_bytes); i++)
        {
            padded_key[i] = key_bytes[i];
        }

        // Compute inner padding (0x36)
        uchar i_pad[];
        ArrayResize(i_pad, BLOCK_SIZE);
        for (int i = 0; i < BLOCK_SIZE; i++)
        {
            i_pad[i] = padded_key[i] ^ 0x36;
        }

        // Compute outer padding (0x5c)
        uchar o_pad[];
        ArrayResize(o_pad, BLOCK_SIZE);
        for (int i = 0; i < BLOCK_SIZE; i++)
        {
            o_pad[i] = padded_key[i] ^ 0x5c;
        }

        // Compute inner hash: SHA256(ipad || message)
        uchar inner_input[];
        ArrayResize(inner_input, ArraySize(i_pad) + ArraySize(msg_bytes));
        for (int i = 0; i < ArraySize(i_pad); i++)
        {
            inner_input[i] = i_pad[i];
        }
        for (int i = 0; i < ArraySize(msg_bytes); i++)
        {
            inner_input[ArraySize(i_pad) + i] = msg_bytes[i];
        }

        SHA256 inner_hash;
        inner_hash.Update(inner_input);
        uchar inner_digest[];
        inner_hash.GetDigest(inner_digest);

        // Compute outer hash: SHA256(opad || inner_hash)
        uchar outer_input[];
        ArrayResize(outer_input, ArraySize(o_pad) + HASH_SIZE);
        for (int i = 0; i < ArraySize(o_pad); i++)
        {
            outer_input[i] = o_pad[i];
        }
        for (int i = 0; i < HASH_SIZE; i++)
        {
            outer_input[ArraySize(o_pad) + i] = inner_digest[i];
        }

        SHA256 outer_hash;
        outer_hash.Update(outer_input);
        outer_hash.GetDigest(hmac);
    }

    static string ComputeHMACBase64(
        const string &message,
        const string &key
    )
    {
        uchar hmac[];
        ComputeHMAC(message, key, hmac);
        return Base64Encoder::Encode(hmac);
    }

private:
    static void StringToCharArray(const string &str, uchar &arr[])
    {
        int len = StringLen(str);
        ArrayResize(arr, len);
        for (int i = 0; i < len; i++)
        {
            arr[i] = (uchar)StringGetCharacter(str, i);
        }
    }
};

//+------------------------------------------------------------------+
//| Authentication Configuration                                    |
//+------------------------------------------------------------------+

class CaerusAuthConfig
{
public:
    string device_id;
    string device_secret;
    string api_base;
    long request_timeout_ms;

    CaerusAuthConfig()
    {
        device_id = "default_device";
        device_secret = "default_secret";
        api_base = "https://api.caerus.trading";
        request_timeout_ms = 5000;
    }
};

//+------------------------------------------------------------------+
//| HMAC-SHA256 Signing (Production Implementation)                |
//+------------------------------------------------------------------+

class CaerusAuth
{
private:
    CaerusAuthConfig config;
    ulong nonce_counter;

public:
    CaerusAuth()
    {
        nonce_counter = 0;
    }

    //--- Initialize auth with device credentials
    void Initialize(string device_id, string device_secret, string api_base = "https://api.caerus.trading")
    {
        config.device_id = device_id;
        config.device_secret = device_secret;
        config.api_base = api_base;
    }

    //--- Generate nonce (timestamp-based + counter to prevent replay)
    string GetNonce()
    {
        // Use timestamp + counter for uniqueness
        ulong ts = (ulong)TimeCurrent() * 1000 + (ulong)GetTickCount();
        nonce_counter++;
        return StringFormat("%llu_%llu", ts, nonce_counter);
    }

    //--- Build RFC3339 timestamp string
    string GetTimestamp()
    {
        MqlDateTime dt;
        TimeCurrent(dt);

        return StringFormat(
            "%04d-%02d-%02dT%02d:%02d:%02dZ",
            dt.year, dt.mon, dt.day,
            dt.hour, dt.min, dt.sec
        );
    }

    //--- Generate HMAC-SHA256 signature for canonical string
    string SignRequest(
        string method,
        string path,
        string body,
        string nonce,
        string timestamp
    )
    {
        // Build canonical string: METHOD|PATH|BODY|DEVICE_ID|NONCE|TIMESTAMP
        string canonical = StringFormat(
            "%s|%s|%s|%s|%s|%s",
            method, path, body, config.device_id, nonce, timestamp
        );

        // Compute HMAC-SHA256 and encode as base64
        return HMACSHA256::ComputeHMACBase64(canonical, config.device_secret);
    }

    //--- Build authorization header with all required components
    string GetAuthHeader(string method, string path, string body = "")
    {
        string nonce = GetNonce();
        string timestamp = GetTimestamp();
        string signature = SignRequest(method, path, body, nonce, timestamp);

        // Format: "CaerusHMAC device_id:signature:nonce:timestamp"
        return StringFormat(
            "CaerusHMAC %s:%s:%s:%s",
            config.device_id, signature, nonce, timestamp
        );
    }

    //--- Get config reference
    CaerusAuthConfig& GetConfig()
    {
        return config;
    }
};

#endif // __CAERUS_AUTH_MQH__
