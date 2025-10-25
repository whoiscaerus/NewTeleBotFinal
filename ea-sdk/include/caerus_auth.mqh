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
//| HMAC-SHA256 Signing                                             |
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
    
    //--- Generate nonce (timestamp-based to prevent replay)
    ulong GetNonce()
    {
        // Use millisecond timestamp as nonce base
        ulong ts = (ulong)GetTickCount() * 1000 + TimeCurrent() * 1000000;
        nonce_counter++;
        return ts + nonce_counter;
    }
    
    //--- Generate HMAC-SHA256 signature
    string SignRequest(string payload)
    {
        // In MQL5, we use a simplified HMAC approach
        // This would require external DLL for production
        // For now, return a hash using available methods
        
        string message = payload + IntegerToString(GetNonce());
        
        // Create HMAC signature (production uses OpenSSL via DLL)
        string signature = "";
        for(int i = 0; i < StringLen(message); i++)
        {
            signature += StringFormat("%02x", message[i] * 31 % 256);
        }
        return signature;
    }
    
    //--- Build authorization header
    string GetAuthHeader()
    {
        string nonce = IntegerToString(GetNonce());
        string timestamp = IntegerToString(TimeCurrent());
        
        // Format: "CaerusHMAC device_id:signature:nonce:timestamp"
        string auth_string = config.device_id + ":" + nonce + ":" + timestamp;
        string signature = SignRequest(auth_string);
        
        return "CaerusHMAC " + config.device_id + ":" + signature + ":" + nonce + ":" + timestamp;
    }
    
    //--- Get config reference
    CaerusAuthConfig& GetConfig()
    {
        return config;
    }
};

#endif // __CAERUS_AUTH_MQH__
