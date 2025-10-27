//+------------------------------------------------------------------+
//| Caerus Reference EA - Approval & Copy Trading Modes             |
//| Connects to Caerus API, polls for signals, executes with modes  |
//+------------------------------------------------------------------+

#property copyright "Caerus Trading"
#property link "https://caerus.trading"
#property version "1.0"
#property strict

#include "include/caerus_auth.mqh"
#include "include/caerus_http.mqh"
#include "include/caerus_models.mqh"
#include "include/caerus_json.mqh"

//+------------------------------------------------------------------+
//| EA Inputs                                                        |
//+------------------------------------------------------------------+

input string DEVICE_ID = "ea_device_001";
input string DEVICE_SECRET = "device_secret_key_here";
input string API_BASE = "https://api.caerus.trading";
input int POLL_INTERVAL_SECONDS = 10;
input int MAX_SPREAD_POINTS = 50;
input double SLIPPAGE_PIPS = 0.5;
input bool AUTO_EXECUTE_COPY_TRADING = false;  // false=approval mode, true=copy mode
input double MAX_POSITION_SIZE_LOT = 1.0;
input int MAX_POSITIONS_PER_SYMBOL = 5;

//+------------------------------------------------------------------+
//| Global Objects                                                   |
//+------------------------------------------------------------------+

CaerusAuth auth;
CaerusHttpClient* http_client = NULL;
PollResponse last_poll;
Signal pending_signals[];
int pending_count = 0;
datetime last_poll_time = 0;

//+------------------------------------------------------------------+
//| EA Initialization                                                |
//+------------------------------------------------------------------+

int OnInit()
{
    Print("[Caerus EA] Initializing EA - Device: ", DEVICE_ID);

    // Initialize authentication
    auth.Initialize(DEVICE_ID, DEVICE_SECRET, API_BASE);

    // Create HTTP client (pass auth object for per-request signing)
    if(http_client != NULL)
        delete http_client;

    http_client = new CaerusHttpClient(API_BASE, auth);

    if(http_client == NULL)
    {
        Print("[ERROR] Failed to create HTTP client");
        return INIT_FAILED;
    }

    Print("[Caerus EA] Mode: ", (AUTO_EXECUTE_COPY_TRADING ? "COPY-TRADING (Auto)" : "APPROVAL (Manual)"));
    Print("[Caerus EA] Polling interval: ", POLL_INTERVAL_SECONDS, " seconds");

    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EA Deinitialization                                              |
//+------------------------------------------------------------------+

void OnDeinit(const int reason)
{
    if(http_client != NULL)
    {
        delete http_client;
        http_client = NULL;
    }

    Print("[Caerus EA] Deinitialized - Reason: ", reason);
}

//+------------------------------------------------------------------+
//| EA Main Loop (Tick Handler)                                     |
//+------------------------------------------------------------------+

void OnTick()
{
    // Poll at regular intervals
    if(TimeCurrent() - last_poll_time >= POLL_INTERVAL_SECONDS)
    {
        PollForSignals();
        last_poll_time = TimeCurrent();
    }

    // Process pending signals based on mode
    ProcessSignals();
}

//+------------------------------------------------------------------+
//| Poll Server for Pending Signals                                 |
//+------------------------------------------------------------------+

void PollForSignals()
{
    if(http_client == NULL)
        return;

    // GET /api/v1/devices/poll
    HttpResponse response = http_client->Get("/api/v1/devices/poll");

    if(!response.success)
    {
        Print("[WARNING] Poll failed: ", response.error_message);
        return;
    }

    // In production, parse JSON response here
    // For now, simulate response handling
    ParsePollResponse(response.response_body);

    Print("[Caerus EA] Poll complete. Pending signals: ", pending_count);
}

//+------------------------------------------------------------------+
//| Parse Poll Response (simplified JSON handling)                  |
//+------------------------------------------------------------------+

void ParsePollResponse(string json_response)
{
    /**
     * Parse poll response from backend with full error handling.
     *
     * Expected JSON format:
     * {
     *   "signals": [
     *     {
     *       "id": "signal_001",
     *       "instrument": "XAUUSD",
     *       "side": 0,
     *       "entry_price": 1950.50,
     *       "stop_loss": 1940.50,
     *       "take_profit": 1960.50,
     *       "volume": 0.5,
     *       "status": 0
     *     }
     *   ],
     *   "count": 1,
     *   "timestamp": "2025-10-26T10:30:45Z"
     * }
     *
     * Handles:
     * - Empty responses
     * - Malformed JSON
     * - Missing fields
     * - Type errors
     * - Array bounds
     * - Invalid signal data
     */

    pending_count = 0;

    // === STEP 1: Validate Input ===
    if(StringLen(json_response) == 0)
    {
        Print("[Caerus EA] ERROR: Empty poll response");
        return;
    }

    if(StringLen(json_response) > 1000000)  // 1MB max
    {
        Print("[Caerus EA] ERROR: Response too large (", StringLen(json_response), " bytes)");
        return;
    }

    // === STEP 2: Extract Signals Array with Error Handling ===
    JSONException error;
    string signals_array = JSONParser::GetArrayValue(json_response, "signals", error);

    if(error.error_code != JSON_OK)
    {
        Print("[Caerus EA] ERROR: Failed to extract signals array: ", error.error_message, " at position ", error.error_position);
        return;
    }

    if(StringLen(signals_array) == 0)
    {
        Print("[Caerus EA] WARNING: No signals array in response");
        return;
    }

    // === STEP 3: Get Signal Count with Error Handling ===
    int signal_count = JSONParser::GetArrayLength(signals_array, error);

    if(error.error_code != JSON_OK)
    {
        Print("[Caerus EA] ERROR: Failed to count signals: ", error.error_message);
        return;
    }

    if(signal_count == 0)
    {
        Print("[Caerus EA] INFO: Empty signals array (no pending approvals)");
        return;
    }

    if(signal_count > 100)  // Safety limit
    {
        Print("[Caerus EA] ERROR: Too many signals (", signal_count, "), limit is 100");
        return;
    }

    // === STEP 4: Resize Array ===
    if(!ArrayResize(pending_signals, signal_count))
    {
        Print("[Caerus EA] ERROR: Failed to resize pending_signals array to ", signal_count);
        return;
    }

    // === STEP 5: Parse Each Signal with Full Validation ===
    int successfully_parsed = 0;

    for(int i = 0; i < signal_count; i++)
    {
        // Extract signal object from array
        string signal_json = JSONParser::GetArrayElement(signals_array, i, error);

        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Failed to extract signal[", i, "]: ", error.error_message);
            continue;
        }

        if(StringLen(signal_json) == 0)
        {
            Print("[Caerus EA] WARNING: Empty signal object at index ", i);
            continue;
        }

        // === Parse ID (required) ===
        string signal_id = JSONParser::GetStringValue(signal_json, "id", error);
        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] missing/invalid id: ", error.error_message);
            continue;
        }

        if(StringLen(signal_id) == 0)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] has empty id");
            continue;
        }

        // === Parse Instrument (required) ===
        string instrument = JSONParser::GetStringValue(signal_json, "instrument", error);
        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] missing/invalid instrument: ", error.error_message);
            continue;
        }

        if(StringLen(instrument) == 0)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] has empty instrument");
            continue;
        }

        // Validate instrument is known
        if(!IsValidInstrument(instrument))
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] has unknown instrument: ", instrument);
            continue;
        }

        // === Parse Side (required, 0=buy, 1=sell) ===
        double side_value = JSONParser::GetNumberValue(signal_json, "side", error);
        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] missing/invalid side: ", error.error_message);
            continue;
        }

        int side = (int)side_value;
        if(side != 0 && side != 1)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] invalid side (expected 0/1, got ", side, ")");
            continue;
        }

        // === Parse Entry Price (required, must be positive) ===
        double entry_price = JSONParser::GetNumberValue(signal_json, "entry_price", error);
        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] missing/invalid entry_price: ", error.error_message);
            continue;
        }

        if(entry_price <= 0)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] invalid entry_price: ", entry_price);
            continue;
        }

        // === Parse Stop Loss (required, must be valid) ===
        double stop_loss = JSONParser::GetNumberValue(signal_json, "stop_loss", error);
        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] missing/invalid stop_loss: ", error.error_message);
            continue;
        }

        if(stop_loss <= 0)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] invalid stop_loss: ", stop_loss);
            continue;
        }

        // Validate SL is on correct side
        if(side == 0 && stop_loss >= entry_price)  // BUY: SL must be below entry
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] BUY SL must be below entry. Entry=", entry_price, ", SL=", stop_loss);
            continue;
        }

        if(side == 1 && stop_loss <= entry_price)  // SELL: SL must be above entry
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] SELL SL must be above entry. Entry=", entry_price, ", SL=", stop_loss);
            continue;
        }

        // === Parse Take Profit (required, must be valid) ===
        double take_profit = JSONParser::GetNumberValue(signal_json, "take_profit", error);
        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] missing/invalid take_profit: ", error.error_message);
            continue;
        }

        if(take_profit <= 0)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] invalid take_profit: ", take_profit);
            continue;
        }

        // Validate TP is on correct side
        if(side == 0 && take_profit <= entry_price)  // BUY: TP must be above entry
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] BUY TP must be above entry. Entry=", entry_price, ", TP=", take_profit);
            continue;
        }

        if(side == 1 && take_profit >= entry_price)  // SELL: TP must be below entry
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] SELL TP must be below entry. Entry=", entry_price, ", TP=", take_profit);
            continue;
        }

        // === Parse Volume (required, must be positive) ===
        double volume = JSONParser::GetNumberValue(signal_json, "volume", error);
        if(error.error_code != JSON_OK)
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] missing/invalid volume: ", error.error_message);
            continue;
        }

        if(volume <= 0 || volume > 100)  // Reasonable range
        {
            Print("[Caerus EA] WARNING: Signal[", i, "] invalid volume: ", volume);
            continue;
        }

        // === Parse Status (optional, default 0) ===
        double status_value = JSONParser::GetNumberValue(signal_json, "status", error);
        int status = (int)status_value;
        // Status errors are non-fatal

        // === All validation passed - store signal ===
        pending_signals[i].id = signal_id;
        pending_signals[i].instrument = instrument;
        pending_signals[i].side = side;
        pending_signals[i].entry_price = entry_price;
        pending_signals[i].stop_loss = stop_loss;
        pending_signals[i].take_profit = take_profit;
        pending_signals[i].volume = volume;
        pending_signals[i].status = status;

        successfully_parsed++;

        // Log successful parse with all details
        Print(
            "[Caerus EA] ✓ Parsed signal[", i, "]: ",
            "ID=", signal_id, " ",
            "Instrument=", instrument, " ",
            "Side=", (side == 0 ? "BUY" : "SELL"), " ",
            "Entry=", DoubleToString(entry_price, 5), " ",
            "SL=", DoubleToString(stop_loss, 5), " ",
            "TP=", DoubleToString(take_profit, 5), " ",
            "Volume=", DoubleToString(volume, 2)
        );
    }

    // === STEP 6: Summary ===
    Print("[Caerus EA] Poll parsing complete: ", successfully_parsed, "/", signal_count, " signals valid");

    if(successfully_parsed > 0)
    {
        pending_count = successfully_parsed;
        Print("[Caerus EA] Ready to process ", pending_count, " pending approvals");
    }
    else
    {
        Print("[Caerus EA] No valid signals to process");
    }
}

//+------------------------------------------------------------------+
//| Validate Instrument is Known                                    |
//+------------------------------------------------------------------+

bool IsValidInstrument(string instrument)
{
    // List of valid instruments on MT5
    string valid_instruments[] = {
        "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "AUDUSD",
        "NZDUSD", "USDCHF", "XAUUSD", "XAGUSD", "BRENT",
        "XPTUSD", "XPDUSD", "US30", "DE30", "FR40",
        "BTCUSD", "ETHUSD", "AAPL", "MSFT", "GOOGL",
        "AMZN", "TSLA", "SPY", "QQQ", "IWM"
    };

    for(int i = 0; i < ArraySize(valid_instruments); i++)
    {
        if(instrument == valid_instruments[i])
            return true;
    }

    return false;
}
            pending_signals[i].id,
            " ",
            pending_signals[i].instrument,
            " ",
            (pending_signals[i].side == 0 ? "BUY" : "SELL"),
            " @ ",
            DoubleToString(pending_signals[i].entry_price, 2)
        );

        pending_count++;
    }

    Print("[Caerus EA] Successfully parsed ", pending_count, " signals");
}

//+------------------------------------------------------------------+
//| Process Signals Based on Mode                                   |
//+------------------------------------------------------------------+

void ProcessSignals()
{
    for(int i = 0; i < pending_count; i++)
    {
        Signal& sig = pending_signals[i];

        if(sig.status != 0)
            continue; // Skip if not pending

        if(AUTO_EXECUTE_COPY_TRADING)
        {
            // Copy-trading mode: auto-execute
            ExecuteSignal(sig);
        }
        else
        {
            // Approval mode: wait for user confirmation
            // (User would confirm in Telegram/Mini App)
            // For now, log pending
            Print("[Approval] Pending signal: ", sig.id, " - ", sig.instrument, " ", (sig.side==0?"BUY":"SELL"));
        }
    }
}

//+------------------------------------------------------------------+
//| Execute Signal as Market Order                                  |
//+------------------------------------------------------------------+

void ExecuteSignal(Signal& signal)
{
    // Validate spread
    double spread = Ask - Bid;
    if(spread > MAX_SPREAD_POINTS * Point())
    {
        Print("[WARNING] Spread too wide: ", spread / Point(), " points. Skipping signal.");
        AckSignal(signal.id, 0, 1, "Spread too wide");
        return;
    }

    // Validate position count
    if(CountOpenPositions(signal.instrument) >= MAX_POSITIONS_PER_SYMBOL)
    {
        Print("[WARNING] Max positions reached for ", signal.instrument);
        AckSignal(signal.id, 0, 1, "Max positions reached");
        return;
    }

    // Execute order
    int order_type = (signal.side == 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
    double volume = MathMin(signal.volume, MAX_POSITION_SIZE_LOT);

    CTrade trade;
    bool result = false;

    if(signal.side == 0) // BUY
        result = trade.Buy(volume, signal.instrument, Ask, signal.stop_loss, signal.take_profit, signal.id);
    else // SELL
        result = trade.Sell(volume, signal.instrument, Bid, signal.stop_loss, signal.take_profit, signal.id);

    if(result)
    {
        Print("[SUCCESS] Order executed: ", signal.id, " - Ticket: ", trade.ResultOrder());
        AckSignal(signal.id, trade.ResultOrder(), 0, "");
        signal.status = 2; // executed
    }
    else
    {
        Print("[ERROR] Order failed: ", signal.id, " - Error: ", GetLastError());
        AckSignal(signal.id, 0, 2, "Order execution failed");
        signal.status = 3; // rejected
    }
}

//+------------------------------------------------------------------+
//| Count Open Positions for Symbol                                 |
//+------------------------------------------------------------------+

int CountOpenPositions(string symbol)
{
    int count = 0;
    int total = PositionsTotal();

    for(int i = total - 1; i >= 0; i--)
    {
        if(PositionSelectByTicket(i))
        {
            if(PositionGetString(POSITION_SYMBOL) == symbol)
                count++;
        }
    }

    return count;
}

//+------------------------------------------------------------------+
//| Send Acknowledgment to Server                                   |
//+------------------------------------------------------------------+

void AckSignal(string signal_id, ulong order_ticket, int status, string error_msg)
{
    if(http_client == NULL)
        return;

    // Build ACK JSON
    string ack_json = "{\"signal_id\":\"" + signal_id + "\",";
    ack_json += "\"order_ticket\":" + IntegerToString(order_ticket) + ",";
    ack_json += "\"status\":" + IntegerToString(status) + ",";
    ack_json += "\"error_message\":\"" + error_msg + "\"}";

    // POST /api/v1/devices/ack
    HttpResponse response = http_client->Post("/api/v1/devices/ack", ack_json);

    if(response.success)
        Print("[ACK] Signal acknowledged: ", signal_id);
    else
        Print("[WARNING] ACK failed for signal: ", signal_id);
}

//+------------------------------------------------------------------+
//| Placeholder for CTrade class                                    |
//+------------------------------------------------------------------+

class CTrade
{
public:
    ulong result_order;

    CTrade() { result_order = 0; }

    bool Buy(double volume, string symbol, double price, double sl, double tp, string comment)
    {
        result_order = 1000001;
        return true;
    }

    bool Sell(double volume, string symbol, double price, double sl, double tp, string comment)
    {
        result_order = 1000002;
        return true;
    }

    ulong ResultOrder() { return result_order; }
};
