//+------------------------------------------------------------------+
//|                                                  ForexBridge.mq5 |
//|                                  Forex Trading Signal System EA  |
//|                   Local TCP Socket Bridge for macOS / Windows    |
//+------------------------------------------------------------------+
#property copyright "Forex Trading Signal System"
#property link      "https://github.com"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>
#include <Trade\SymbolInfo.mqh>

input int InpPort = 5555;            // TCP Server Port
input int InpTimerMs = 100;          // Polling Timer (milliseconds)

CTrade         m_trade;
CPositionInfo  m_position;
CAccountInfo   m_account;
CSymbolInfo    m_symbol;

int g_server_socket = INVALID_HANDLE;
int g_client_socket = INVALID_HANDLE;

//+------------------------------------------------------------------+
//| Helper: Convert timeframe string to ENUM_TIMEFRAMES              |
//+------------------------------------------------------------------+
ENUM_TIMEFRAMES StringToTimeframe(string tf_str)
{
   if(tf_str == "M1"  || tf_str == "1m")  return PERIOD_M1;
   if(tf_str == "M5"  || tf_str == "5m")  return PERIOD_M5;
   if(tf_str == "M15" || tf_str == "15m") return PERIOD_M15;
   if(tf_str == "M30" || tf_str == "30m") return PERIOD_M30;
   if(tf_str == "H1"  || tf_str == "1h")  return PERIOD_H1;
   if(tf_str == "H4"  || tf_str == "4h")  return PERIOD_H4;
   if(tf_str == "D1"  || tf_str == "1d")  return PERIOD_D1;
   return PERIOD_M5;
}

//+------------------------------------------------------------------+
//| Helper: Extract string value from JSON by key                    |
//+------------------------------------------------------------------+
string JsonGetString(string json, string key)
{
   string search = "\"" + key + "\":";
   int pos = StringFind(json, search);
   if(pos < 0) return "";
   pos += StringLen(search);
   while(pos < StringLen(json) && (StringGetCharacter(json, pos) == ' ' || StringGetCharacter(json, pos) == '\"'))
      pos++;
   int end_pos = pos;
   while(end_pos < StringLen(json) && StringGetCharacter(json, end_pos) != '\"' && StringGetCharacter(json, end_pos) != ',' && StringGetCharacter(json, end_pos) != '}')
      end_pos++;
   return StringSubstr(json, pos, end_pos - pos);
}

//+------------------------------------------------------------------+
//| Helper: Extract double value from JSON by key                    |
//+------------------------------------------------------------------+
double JsonGetDouble(string json, string key)
{
   string val = JsonGetString(json, key);
   if(val == "") return 0.0;
   return StringToDouble(val);
}

//+------------------------------------------------------------------+
//| Helper: Extract long value from JSON by key                      |
//+------------------------------------------------------------------+
long JsonGetLong(string json, string key)
{
   string val = JsonGetString(json, key);
   if(val == "") return 0;
   return StringToInteger(val);
}

//+------------------------------------------------------------------+
//| Helper: Send raw string response to connected client             |
//+------------------------------------------------------------------+
bool SendClientResponse(int client_sock, string response)
{
   if(client_sock == INVALID_HANDLE) return false;
   string msg = response + "\n";
   uchar data[];
   StringToCharArray(msg, data, 0, StringLen(msg));
   int sent = SocketSend(client_sock, data, ArraySize(data));
   return (sent > 0);
}

//+------------------------------------------------------------------+
//| Command Handler: Process JSON Request                            |
//+------------------------------------------------------------------+
string ProcessCommand(string request_json)
{
   string action = JsonGetString(request_json, "action");
   
   // 1. PING
   if(action == "PING")
   {
      return StringFormat("{\"status\":\"OK\",\"time\":\"%s\",\"server\":\"%s\",\"account\":%I64d}",
                          TimeToString(TimeCurrent(), TIME_DATE|TIME_SECONDS),
                          AccountInfoString(ACCOUNT_SERVER),
                          AccountInfoInteger(ACCOUNT_LOGIN));
   }
   
   // 2. ACCOUNT_INFO
   if(action == "ACCOUNT_INFO")
   {
      return StringFormat("{\"status\":\"OK\",\"login\":%I64d,\"server\":\"%s\",\"currency\":\"%s\",\"balance\":%.2f,\"equity\":%.2f,\"margin\":%.2f,\"free_margin\":%.2f,\"leverage\":%d}",
                          AccountInfoInteger(ACCOUNT_LOGIN),
                          AccountInfoString(ACCOUNT_SERVER),
                          AccountInfoString(ACCOUNT_CURRENCY),
                          AccountInfoDouble(ACCOUNT_BALANCE),
                          AccountInfoDouble(ACCOUNT_EQUITY),
                          AccountInfoDouble(ACCOUNT_MARGIN),
                          AccountInfoDouble(ACCOUNT_MARGIN_FREE),
                          (int)AccountInfoInteger(ACCOUNT_LEVERAGE));
   }
   
   // 3. SYMBOL_INFO
   if(action == "SYMBOL_INFO")
   {
      string sym = JsonGetString(request_json, "symbol");
      if(sym == "") sym = _Symbol;
      
      if(!SymbolSelect(sym, true))
      {
         return StringFormat("{\"status\":\"ERROR\",\"error_message\":\"Symbol not found: %s\"}", sym);
      }
      
      m_symbol.Name(sym);
      m_symbol.RefreshRates();
      
      int digits = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
      double point = SymbolInfoDouble(sym, SYMBOL_POINT);
      double pip_size = (digits == 3 || digits == 5) ? point * 10 : point;
      int spread_pts = (int)SymbolInfoInteger(sym, SYMBOL_SPREAD);
      double spread_pips = spread_pts * point / pip_size;
      double min_lot = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
      double max_lot = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
      double lot_step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
      int stop_level = (int)SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);
      double contract = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
      
      return StringFormat("{\"status\":\"OK\",\"symbol\":\"%s\",\"digits\":%d,\"point\":%.8f,\"pip_size\":%.8f,\"spread_points\":%d,\"spread_pips\":%.2f,\"min_lot\":%.2f,\"max_lot\":%.2f,\"lot_step\":%.2f,\"stop_level\":%d,\"contract_size\":%.2f}",
                          sym, digits, point, pip_size, spread_pts, spread_pips, min_lot, max_lot, lot_step, stop_level, contract);
   }
   
   // 4. GET_CANDLES
   if(action == "GET_CANDLES")
   {
      string sym = JsonGetString(request_json, "symbol");
      if(sym == "") sym = _Symbol;
      string tf_str = JsonGetString(request_json, "timeframe");
      ENUM_TIMEFRAMES tf = StringToTimeframe(tf_str);
      int count = (int)JsonGetLong(request_json, "count");
      if(count <= 0) count = 100;
      
      MqlRates rates[];
      ArraySetAsSeries(rates, false);
      int copied = CopyRates(sym, tf, 0, count, rates);
      
      if(copied <= 0)
      {
         return StringFormat("{\"status\":\"ERROR\",\"error_message\":\"Failed to copy rates for %s\"}", sym);
      }
      
      string candles_json = "[";
      for(int i = 0; i < copied; i++)
      {
         string candle = StringFormat("{\"timestamp\":%I64d,\"open\":%.5f,\"high\":%.5f,\"low\":%.5f,\"close\":%.5f,\"volume\":%.0f}",
                                      rates[i].time, rates[i].open, rates[i].high, rates[i].low, rates[i].close, (double)rates[i].tick_volume);
         candles_json += candle;
         if(i < copied - 1) candles_json += ",";
      }
      candles_json += "]";
      
      return StringFormat("{\"status\":\"OK\",\"count\":%d,\"candles\":%s}", copied, candles_json);
   }
   
   // 5. ORDER_SEND
   if(action == "ORDER_SEND")
   {
      string sym = JsonGetString(request_json, "symbol");
      if(sym == "") sym = _Symbol;
      string type = JsonGetString(request_json, "type");
      double volume = JsonGetDouble(request_json, "volume");
      double sl = JsonGetDouble(request_json, "sl");
      double tp = JsonGetDouble(request_json, "tp");
      ulong deviation = (ulong)JsonGetLong(request_json, "deviation");
      ulong magic = (ulong)JsonGetLong(request_json, "magic");
      string comment = JsonGetString(request_json, "comment");
      if(comment == "") comment = "forex_signals_bot";
      
      m_trade.SetExpertMagicNumber(magic);
      m_trade.SetDeviationInPoints(deviation);
      
      bool res = false;
      if(type == "BUY")
      {
         res = m_trade.Buy(volume, sym, 0, sl, tp, comment);
      }
      else if(type == "SELL")
      {
         res = m_trade.Sell(volume, sym, 0, sl, tp, comment);
      }
      else
      {
         return StringFormat("{\"status\":\"ERROR\",\"error_message\":\"Invalid order type: %s\"}", type);
      }
      
      uint retcode = m_trade.ResultRetcode();
      ulong ticket = m_trade.ResultOrder();
      double price = m_trade.ResultPrice();
      
      if(res || retcode == TRADE_RETCODE_DONE || retcode == TRADE_RETCODE_PLACED)
      {
         return StringFormat("{\"status\":\"OK\",\"ticket\":%I64d,\"price\":%.5f,\"retcode\":%d,\"volume\":%.2f,\"comment\":\"%s\"}",
                             ticket, price, retcode, volume, m_trade.ResultComment());
      }
      else
      {
         return StringFormat("{\"status\":\"ERROR\",\"retcode\":%d,\"error_message\":\"%s\"}",
                             retcode, m_trade.ResultComment());
      }
   }
   
   // 6. ORDER_CLOSE
   if(action == "ORDER_CLOSE")
   {
      ulong ticket = (ulong)JsonGetLong(request_json, "ticket");
      ulong deviation = (ulong)JsonGetLong(request_json, "deviation");
      if(deviation == 0) deviation = 10;
      
      m_trade.SetDeviationInPoints(deviation);
      bool res = m_trade.PositionClose(ticket);
      uint retcode = m_trade.ResultRetcode();
      
      if(res || retcode == TRADE_RETCODE_DONE)
      {
         return StringFormat("{\"status\":\"OK\",\"ticket\":%I64d,\"retcode\":%d,\"comment\":\"Closed\"}",
                             ticket, retcode);
      }
      else
      {
         return StringFormat("{\"status\":\"ERROR\",\"ticket\":%I64d,\"retcode\":%d,\"error_message\":\"%s\"}",
                             ticket, retcode, m_trade.ResultComment());
      }
   }
   
   // 7. GET_POSITIONS
   if(action == "GET_POSITIONS")
   {
      ulong filter_magic = (ulong)JsonGetLong(request_json, "magic");
      int total = PositionsTotal();
      string pos_json = "[";
      int matched = 0;
      
      for(int i = 0; i < total; i++)
      {
         if(m_position.SelectByIndex(i))
         {
            ulong p_magic = m_position.Magic();
            if(filter_magic != 0 && p_magic != filter_magic) continue;
            
            if(matched > 0) pos_json += ",";
            string p_type = (m_position.PositionType() == POSITION_TYPE_BUY) ? "BUY" : "SELL";
            string single_pos = StringFormat("{\"ticket\":%I64d,\"symbol\":\"%s\",\"type\":\"%s\",\"volume\":%.2f,\"open_price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"open_time\":%I64d,\"current_price\":%.5f,\"profit\":%.2f,\"magic\":%I64d,\"comment\":\"%s\"}",
                                             m_position.Ticket(),
                                             m_position.Symbol(),
                                             p_type,
                                             m_position.Volume(),
                                             m_position.PriceOpen(),
                                             m_position.StopLoss(),
                                             m_position.TakeProfit(),
                                             m_position.Time(),
                                             m_position.PriceCurrent(),
                                             m_position.Profit(),
                                             p_magic,
                                             m_position.Comment());
            pos_json += single_pos;
            matched++;
         }
      }
      pos_json += "]";
      return StringFormat("{\"status\":\"OK\",\"count\":%d,\"positions\":%s}", matched, pos_json);
   }
   
   return StringFormat("{\"status\":\"ERROR\",\"error_message\":\"Unknown action: %s\"}", action);
}

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   PrintFormat("[ForexBridge] Starting TCP Socket Server on Port %d...", InpPort);
   
   g_server_socket = SocketCreate();
   if(g_server_socket == INVALID_HANDLE)
   {
      PrintFormat("[ForexBridge] SocketCreate failed, error: %d", GetLastError());
      return INIT_FAILED;
   }
   
   if(!SocketBind(g_server_socket, "127.0.0.1", InpPort))
   {
      PrintFormat("[ForexBridge] SocketBind on 127.0.0.1:%d failed, error: %d", InpPort, GetLastError());
      SocketClose(g_server_socket);
      g_server_socket = INVALID_HANDLE;
      return INIT_FAILED;
   }
   
   if(!SocketListen(g_server_socket, 5))
   {
      PrintFormat("[ForexBridge] SocketListen failed, error: %d", GetLastError());
      SocketClose(g_server_socket);
      g_server_socket = INVALID_HANDLE;
      return INIT_FAILED;
   }
   
   EventSetMillisecondTimer(InpTimerMs);
   PrintFormat("[ForexBridge] Server listening on 127.0.0.1:%d. Ready for macOS Python connections.", InpPort);
   return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   if(g_client_socket != INVALID_HANDLE)
   {
      SocketClose(g_client_socket);
      g_client_socket = INVALID_HANDLE;
   }
   if(g_server_socket != INVALID_HANDLE)
   {
      SocketClose(g_server_socket);
      g_server_socket = INVALID_HANDLE;
   }
   Print("[ForexBridge] Socket server stopped.");
}

//+------------------------------------------------------------------+
//| Timer event function: Read and process client requests           |
//+------------------------------------------------------------------+
void OnTimer()
{
   if(g_server_socket == INVALID_HANDLE) return;
   
   // Check for new client connection
   if(g_client_socket == INVALID_HANDLE)
   {
      g_client_socket = SocketAccept(g_server_socket);
      if(g_client_socket != INVALID_HANDLE)
      {
         Print("[ForexBridge] Client connected from macOS Python.");
      }
   }
   
   if(g_client_socket == INVALID_HANDLE) return;
   
   // Read incoming bytes
   uint readable = SocketIsReadable(g_client_socket);
   if(readable > 0)
   {
      uchar buffer[];
      ArrayResize(buffer, readable);
      int read = SocketRead(g_client_socket, buffer, readable, 100);
      if(read > 0)
      {
         string request = CharArrayToString(buffer, 0, read);
         string lines[];
         int num_lines = StringSplit(request, '\n', lines);
         
         for(int i = 0; i < num_lines; i++)
         {
            string line = lines[i];
            StringTrimLeft(line);
            StringTrimRight(line);
            if(StringLen(line) == 0) continue;
            
            string response = ProcessCommand(line);
            SendClientResponse(g_client_socket, response);
         }
      }
      else if(read < 0)
      {
         Print("[ForexBridge] Client disconnected.");
         SocketClose(g_client_socket);
         g_client_socket = INVALID_HANDLE;
      }
   }
}
//+------------------------------------------------------------------+
