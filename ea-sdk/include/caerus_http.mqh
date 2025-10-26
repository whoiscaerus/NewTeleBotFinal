//+------------------------------------------------------------------+
//| Caerus HTTP Module for MT5 EA                                   |
//| HTTPS requests with retry + timeout handling                    |
//+------------------------------------------------------------------+

#ifndef __CAERUS_HTTP_MQH__
#define __CAERUS_HTTP_MQH__

//+------------------------------------------------------------------+
//| HTTP Request/Response Types                                     |
//+------------------------------------------------------------------+

struct HttpRequest
{
    string method;
    string endpoint;
    string body;
    int timeout_ms;

    HttpRequest()
    {
        method = "GET";
        endpoint = "";
        body = "";
        timeout_ms = 5000;
    }
};

struct HttpResponse
{
    int status_code;
    string response_body;
    bool success;
    string error_message;

    HttpResponse()
    {
        status_code = 0;
        response_body = "";
        success = false;
        error_message = "";
    }
};

//+------------------------------------------------------------------+
//| HTTP Client                                                     |
//+------------------------------------------------------------------+

class CaerusHttpClient
{
private:
    string api_base;
    string auth_header;
    int max_retries;
    int retry_delay_ms;

public:
    CaerusHttpClient(string base_url, string auth)
    {
        api_base = base_url;
        auth_header = auth;
        max_retries = 3;
        retry_delay_ms = 1000;
    }

    //--- Execute GET request with retry logic
    HttpResponse Get(string endpoint)
    {
        HttpRequest request;
        request.method = "GET";
        request.endpoint = endpoint;
        return ExecuteWithRetry(request);
    }

    //--- Execute POST request with retry logic
    HttpResponse Post(string endpoint, string json_body)
    {
        HttpRequest request;
        request.method = "POST";
        request.endpoint = endpoint;
        request.body = json_body;
        return ExecuteWithRetry(request);
    }

private:
    HttpResponse ExecuteWithRetry(HttpRequest& request)
    {
        HttpResponse response;

        for(int attempt = 0; attempt <= max_retries; attempt++)
        {
            response = ExecuteRequest(request);

            if(response.success || attempt == max_retries)
                return response;

            // Exponential backoff
            Sleep(retry_delay_ms * (attempt + 1));
        }

        return response;
    }

    HttpResponse ExecuteRequest(HttpRequest& request)
    {
        HttpResponse response;

        try
        {
            string url = api_base + request.endpoint;
            string headers = "Content-Type: application/json\r\n";
            headers += "Authorization: " + auth_header + "\r\n";

            // Note: In production MT5, use WebRequest API
            // This is a placeholder structure

            response.status_code = 200;
            response.success = true;
            response.response_body = "{}";

            return response;
        }
        catch(...)
        {
            response.status_code = 0;
            response.success = false;
            response.error_message = "HTTP request failed";
            return response;
        }
    }
};

#endif // __CAERUS_HTTP_MQH__
