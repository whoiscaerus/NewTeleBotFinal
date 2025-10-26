//+------------------------------------------------------------------+
//| Caerus Models Module                                            |
//| Signal, Order, Position, Account data structures                |
//+------------------------------------------------------------------+

#ifndef __CAERUS_MODELS_MQH__
#define __CAERUS_MODELS_MQH__

//+------------------------------------------------------------------+
//| Signal Model (from server /poll endpoint)                       |
//+------------------------------------------------------------------+

struct Signal
{
    string id;
    string instrument;
    int side;               // 0=BUY, 1=SELL
    double entry_price;
    double stop_loss;
    double take_profit;
    double volume;
    long created_at_ms;
    int status;            // 0=pending, 1=approved, 2=executed, 3=rejected

    Signal()
    {
        id = "";
        instrument = "";
        side = 0;
        entry_price = 0.0;
        stop_loss = 0.0;
        take_profit = 0.0;
        volume = 0.0;
        created_at_ms = 0;
        status = 0;
    }
};

//+------------------------------------------------------------------+
//| Order Model                                                     |
//+------------------------------------------------------------------+

struct Order
{
    ulong ticket;
    string signal_id;
    string instrument;
    int type;              // 0=BUY, 1=SELL
    double volume;
    double entry_price;
    double stop_loss;
    double take_profit;
    long opened_at_ms;
    int status;            // 0=pending, 1=open, 2=closed

    Order()
    {
        ticket = 0;
        signal_id = "";
        instrument = "";
        type = 0;
        volume = 0.0;
        entry_price = 0.0;
        stop_loss = 0.0;
        take_profit = 0.0;
        opened_at_ms = 0;
        status = 0;
    }
};

//+------------------------------------------------------------------+
//| Position Model                                                  |
//+------------------------------------------------------------------+

struct Position
{
    ulong ticket;
    string symbol;
    int type;              // 0=BUY, 1=SELL
    double volume;
    double open_price;
    double current_price;
    double stop_loss;
    double take_profit;
    double profit;
    double profit_percent;

    Position()
    {
        ticket = 0;
        symbol = "";
        type = 0;
        volume = 0.0;
        open_price = 0.0;
        current_price = 0.0;
        stop_loss = 0.0;
        take_profit = 0.0;
        profit = 0.0;
        profit_percent = 0.0;
    }
};

//+------------------------------------------------------------------+
//| Account Info Model                                              |
//+------------------------------------------------------------------+

struct AccountInfo
{
    long account_number;
    double balance;
    double equity;
    double free_margin;
    double margin_level;
    int leverage;

    AccountInfo()
    {
        account_number = 0;
        balance = 0.0;
        equity = 0.0;
        free_margin = 0.0;
        margin_level = 0.0;
        leverage = 100;
    }
};

//+------------------------------------------------------------------+
//| Poll Response (batch of pending signals)                        |
//+------------------------------------------------------------------+

struct PollResponse
{
    Signal signals[];
    int signal_count;
    string timestamp;
    bool success;

    PollResponse()
    {
        signal_count = 0;
        timestamp = "";
        success = false;
    }
};

//+------------------------------------------------------------------+
//| Acknowledgment Request (confirm signal execution)               |
//+------------------------------------------------------------------+

struct AckRequest
{
    string signal_id;
    ulong order_ticket;
    int status;            // 0=executed, 1=rejected, 2=failed
    string error_message;

    AckRequest()
    {
        signal_id = "";
        order_ticket = 0;
        status = 0;
        error_message = "";
    }
};

#endif // __CAERUS_MODELS_MQH__
