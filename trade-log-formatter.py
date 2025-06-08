import pandas as pd
import re
import json
import os
from datetime import datetime, timedelta
from glob import glob
import fitz  # PyMuPDF for PDF processing
import csv

# Configuration
DEBUG = False  # Set to True to enable debug printing
# Set default test date to yesterday
yesterday = datetime.now() - timedelta(days=1)
# DEFAULT_TEST_DATE = datetime.now().strftime("%m.%Y")

# Add at the top with other configurations
TEST_MODE = False  # Set to True to use test files
DEFAULT_TEST_DATE = "04.2025" if TEST_MODE else datetime.now().strftime("%m.%Y")
MASTER_FILE = "master-copy-test.xlsx" if TEST_MODE else "master-trades.xlsx"
MASTER_BACKUP = "master-copy-test-backup.xlsx" if TEST_MODE else "master-copy-backup.xlsx"
PROCESSED_FILE = "processed_files_test.json" if TEST_MODE else "processed_files.json"

def debug_print(*args, **kwargs):
    """Wrapper for debug printing"""
    if DEBUG:
        print(*args, **kwargs)

def get_folder_path(date_str):
    """Find folder containing the input month-year"""
    try:
        # Parse input date string (e.g., 05.2025)
        target_date = datetime.strptime(date_str, "%m.%Y")
        target_folder = target_date.strftime("%m.%Y")
        
        # Get base directory
        base_path = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades"
        
        # Look for exact month folder
        folder_path = os.path.join(base_path, target_folder)
        
        if os.path.exists(folder_path) and os.path.isdir(folder_path):
            debug_print(f"Found matching folder: {target_folder}")
            return folder_path
            
        raise FileNotFoundError(f"No folder found for month-year: {date_str}")
            
    except ValueError as e:
        print(f"⚠️ Invalid date format: {e}. Expected MM.YYYY (e.g., 05.2025)")
        raise ValueError("Invalid date format. Please use MM.YYYY (e.g., 05.2025)")


def parse_trade_line(line):
    """Parse a single trade line from PDF report"""
    # Updated pattern to handle options symbols
    pattern = re.compile(r"""
        U\*\*\*\d+\s+               # Account ID (masked)
        (?P<symbol>[A-Z\s\d]+)\s+   # Symbol (including options)
        (?P<trade_date>\d{4}-\d{2}-\d{2}),?\s*  # Trade Date (optional comma)
        (?P<trade_time>\d{2}:\d{2}:\d{2})\s*    # Trade Time
        (?P<settle_date>\d{4}-\d{2}-\d{2})\s*   # Settle Date
        [-\s]*                      # Exchange separator
        (?P<type>BUY|SELL)\s*      # Trade Type
        (?P<quantity>-?\d+)\s*      # Quantity (allowing negative numbers)
        (?P<price>\d+\.?\d*)\s*     # Price
        [-\d.,\s]*                  # Proceeds
    """, re.VERBOSE | re.IGNORECASE)

    match = pattern.search(line)
    if not match:
        # Analyze why the pattern failed to match
        checks = [
            ("Account ID", r"U\*\*\*\d+"),
            ("Symbol", r"[A-Z\s\d]+"),
            ("Trade Date", r"\d{4}-\d{2}-\d{2}"),
            ("Time", r"\d{2}:\d{2}:\d{2}"),
            ("Trade Type", r"BUY|SELL"),
            ("Quantity", r"-?\d+"),
            ("Price", r"\d+\.?\d*")
        ]
        
        print("\n  🔍 Pattern match failure analysis:")
        for check_name, check_pattern in checks:
            if not re.search(check_pattern, line):
                print(f"    ❌ Missing {check_name}")
        print(f"    📝 Raw text: {line[:100]}...")
        return None

    trade_data = {
        "Symbol": match.group("symbol").strip(),  # Strip extra whitespace
        "Date": match.group("trade_date"),
        "Time": match.group("trade_time"),
        "Quantity": abs(int(match.group("quantity"))),  # Use absolute value
        "Price": float(match.group("price")),
        "Side": match.group("type").upper()
    }
    
    return trade_data

def is_option_trade(symbol):
    """Check if the trade is an options trade by looking for date pattern after symbol"""
    # Match pattern like: UNH 16JAN26 550 C
    return bool(re.search(r'[A-Z]+\s+\d+[A-Z]{3}\d{2}\s+\d+\s+[CP]', symbol))

def extract_trades_from_pdf(file_path):
    """Extract all trades from a PDF file and show summary"""
    trades = []
    try:
        doc = fitz.open(file_path)
        print(f"\n📄 Processing: {os.path.basename(file_path)}")
        
        for page in doc:
            text = page.get_text()
            sections = text.split('USD')
            if len(sections) > 1:
                relevant_text = sections[1].split('Financial Instrument Information')[0]
                lines = [line.strip() for line in relevant_text.splitlines() if line.strip()]
                
                i = 0
                while i < len(lines):
                    if lines[i].startswith('U***'):
                        try:
                            # Extract trade data from lines
                            account = lines[i]
                            symbol = lines[i+1]     # This might be an option symbol
                            datetime = lines[i+2]
                            trade_type = lines[i+5].strip().upper()
                            quantity = lines[i+6]
                            price = lines[i+7]
                            
                            # Skip if this is a Total line
                            if "Total" not in symbol:
                                # Keep full symbol if it's an option
                                is_option = is_option_trade(symbol)
                                trade_symbol = symbol if is_option else symbol.split()[0]
                                
                                # For options, multiply price by 100
                                raw_price = float(price.strip())
                                adjusted_price = raw_price * 100 if is_option else raw_price
                                
                                trade_data = {
                                    "Symbol": trade_symbol,
                                    "Date": datetime.split(',')[0],
                                    "Time": datetime.split(',')[1].strip(),
                                    "Quantity": int(quantity.strip()),
                                    "Price": adjusted_price,
                                    "Side": trade_type
                                }
                                
                                debug_print(f"    Parsed Trade: {'LONG' if trade_data['Side'] == 'BUY' else 'SHORT'} {trade_data['Quantity']} "
                                          f"{trade_data['Symbol']} @ ${trade_data['Price']:.2f} "
                                          f"({'Option' if is_option else 'Stock'})")
                                
                                trades.append(trade_data)
                            
                            # Skip to next potential transaction
                            i += 12
                        except (IndexError, ValueError) as e:
                            print(f"  ⚠️ Error parsing trade at line {i}")
                            print(f"  ⚠️ Error details: {str(e)}")
                            print(f"  ⚠️ Current line content: {lines[i]}")
                            i += 1
                    else:
                        i += 1
                        
        # Add summary at the end of each PDF
        if DEBUG:
            print("\n  📊 Debug Summary of Trades:")
            if trades:
                # Group trades by symbol and side
                buys = {}
                sells = {}
                
                # Debug the trade sorting
                debug_print("\n  🔍 Sorting trades:")
                for trade in trades:
                    symbol = trade['Symbol']
                    side = trade['Side']
                    debug_print(f"    Trade: {symbol} {side} {trade['Quantity']} @ {trade['Price']}")
                    
                    # Determine target dictionary based on trade side
                    if side == "SELL":
                        target_dict = sells
                    else:
                        target_dict = buys
                    
                    if symbol not in target_dict:
                        target_dict[symbol] = {
                            'qty': 0,
                            'total_cost': 0,
                            'earliest_time': trade['Time']
                        }
                    
                    current = target_dict[symbol]
                    current['qty'] += trade['Quantity']
                    current['total_cost'] += trade['Quantity'] * trade['Price']
                    current['earliest_time'] = min(current['earliest_time'], trade['Time'])
                    
                    debug_print(f"    Added to {'SELLS' if side == 'SELL' else 'BUYS'}, "
                            f"New total: {current['qty']} @ {current['total_cost']/current['qty']:.2f}")
                
                # Print summary
                print("\n  📊 PDF Summary:")
                pdf_total = 0
                
                # Print LONG summary
                if buys:
                    print("\n  🟢 LONG:")  # Changed from BUYS
                    print("  Symbol  Shares    Avg Price    Total Value    Time")
                    print("  " + "-" * 55)
                    
                    for symbol, data in buys.items():
                        if data['qty'] > 0:
                            avg_price = data['total_cost'] / data['qty']
                            total_value = data['total_cost']
                            pdf_total += total_value
                            
                            print(f"  {symbol:6} {data['qty']:8.0f} @ ${avg_price:8,.2f} = ${total_value:11,.2f}  {data['earliest_time']}")
                    
                    print("  " + "-" * 55)
                
                # Print SHORT summary
                if sells:
                    print("\n  🔴 SHORT:")  # Changed from SELLS
                    print("  Symbol  Shares    Avg Price    Total Value    Time")
                    print("  " + "-" * 55)
                    
                    for symbol, data in sells.items():
                        if data['qty'] < 0:
                            avg_price = data['total_cost'] / data['qty']
                            total_value = data['total_cost']
                            pdf_total += total_value
                            
                            print(f"  {symbol:6} {data['qty']:8.0f} @ ${avg_price:8,.2f} = ${total_value:11,.2f}  {data['earliest_time']}")
                    
                    print("  " + "-" * 55)
                
                print(f"  PDF Total Value: ${pdf_total:,.2f}\n")
        
        doc.close()
        
    except Exception as e:
        print(f"❌ Error processing {file_path}: {str(e)}")
    
    return trades

def gather_all_trades(folder):
    """Gather trades from all PDFs in chronological order"""
    all_trades = []
    # Get all PDF files and sort them by date in filename
    pdf_files = glob(os.path.join(folder, "DailyTradeReport.*.pdf"))
    
    # Sort PDFs by date in filename (format: DailyTradeReport.YYYYMMDD.pdf)
    pdf_files.sort(key=lambda x: os.path.basename(x).split('.')[1])
    
    processed_files = manage_processed_files(folder, check_only=True)
    
    new_files = False
    for pdf in pdf_files:
        filename = os.path.basename(pdf)
        if filename in processed_files:
            debug_print(f"⏭️  Skipping previously processed file: {filename}")
            continue
            
        new_files = True
        debug_print(f"\n📅 Processing {filename}")
        trades = extract_trades_from_pdf(pdf)
        all_trades.extend(trades)
        
        # Mark file as processed
        manage_processed_files(folder, filename)
    
    if not new_files:
        print("\n📝 No new trade reports to process")
    
    return all_trades

def export_to_csv(trades, output_file, folder_path):
    """Export trades to CSV file in the same folder as PDFs"""
    if not trades:
        print("No trades found to export.")
        return

    fields = ["Symbol", "Quantity", "Side", "Price", "Time", "Date"]
    
    # Create full path for output file in the same folder as PDFs
    output_path = os.path.join(folder_path, output_file)
    
    with open(output_path, mode='w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(trades)

    print(f"✅ Exported {len(trades)} trades to {output_path}")

def consolidate_trades(trades):
    """Consolidate trades by symbol and date, averaging prices for same-day trades"""
    consolidated = {}
    
    for trade in trades:
        # Update trade side before creating key
        trade['Side'] = 'LONG' if trade['Side'] == 'BUY' else 'SHORT'
        key = (trade['Symbol'], trade['Date'], trade['Side'])
        
        if key in consolidated:
            existing = consolidated[key]
            # Calculate new total quantity and weighted average price
            total_qty = existing['Quantity'] + trade['Quantity']
            weighted_price = (
                (existing['Quantity'] * existing['Price'] + 
                 trade['Quantity'] * trade['Price']) / total_qty
            )
            
            # For SHORT orders, keep the latest time
            # For LONG orders, keep the earliest time
            if trade['Side'] == 'SHORT':
                time_to_use = max(existing['Time'], trade['Time'])
            else:
                time_to_use = min(existing['Time'], trade['Time'])
            
            consolidated[key] = {
                'Symbol': trade['Symbol'],
                'Date': trade['Date'],
                'Time': time_to_use,
                'Side': trade['Side'],
                'Quantity': total_qty,
                'Price': weighted_price
            }
        else:
            consolidated[key] = trade.copy()
    
    return list(consolidated.values())

def check_open_positions(folder_path):
    """Check master copy for open positions and provide summary with totals"""
    try:
        master_file = os.path.join("/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades", MASTER_FILE)
        df = pd.read_excel(master_file)
        
        # Find rows where Exit Qty or Exit Price is empty/NaN
        open_positions = df[df['Exit Qty'].isna() | df['Exit Price'].isna()]
        
        if not open_positions.empty:
            print("\n📈 Open Positions (Detail):")
            for _, row in open_positions.iterrows():
                position_type = "LONG" if row['Side'] in ['BUY', 'LONG'] else "SHORT"
                print(f"  • {row['Symbol']}: {row['Qty']} shares ({position_type}) @ ${row['Entry Price']:.2f} "
                      f"({row['Entry Date']} {row['Entry Time']})")
            
            # Create summary by symbol
            summary = {}
            grand_total = 0
            
            for _, row in open_positions.iterrows():
                symbol = row['Symbol']
                qty = row['Qty']
                price = row['Entry Price']
                date = pd.to_datetime(row['Entry Date'])
                
                if symbol in summary:
                    existing = summary[symbol]
                    total_qty = existing['qty'] + qty
                    weighted_price = (existing['qty'] * existing['price'] + qty * price) / total_qty
                    earliest_date = min(existing['date'], date)
                    
                    summary[symbol] = {
                        'qty': total_qty,
                        'price': weighted_price,
                        'date': earliest_date,
                        'total_value': total_qty * weighted_price
                    }
                else:
                    summary[symbol] = {
                        'qty': qty,
                        'price': price,
                        'date': date,
                        'total_value': qty * price
                    }
            
            # Print summary with position values
            print("\n📊 Open Positions Summary:")
            print("  Symbol  Shares    Avg Price    Total Value    Since")
            print("  " + "-" * 55)
            
            for symbol, data in summary.items():
                position_value = data['total_value']
                grand_total += position_value
                print(f"  {symbol:6} {data['qty']:8.0f} @ ${data['price']:8,.2f} = ${position_value:11,.2f}  {data['date'].strftime('%Y-%m-%d')}")
            
            print("  " + "-" * 55)
            print(f"  Total Portfolio Value: ${grand_total:,.2f}")
            
            return open_positions.to_dict('records')
        else:
            print("\n✅ No open positions found")
            return []
            
    except FileNotFoundError:
        print(f"\n⚠️  Master copy not found: {master_file}")
        return []
    except Exception as e:
        print(f"\n❌ Error reading master copy: {str(e)}")
        return []

def match_trades_fifo(df_master, consolidated_trades):
    """Match trades using FIFO method with running balance"""
    positions = {}  # {symbol: {'qty': net_qty, 'trades': []}}
    
    # Process trades in chronological order - this is crucial!
    trades = sorted(consolidated_trades, key=lambda x: (x['Date'], x['Time']))
    print("\n🔄 Matching trades using FIFO method...")
    print("\nTrades to process:")
    print(json.dumps(trades, indent=2, default=str))

    for trade in trades:
        symbol = trade['Symbol']
        side = trade['Side']  # This is now 'LONG' or 'SHORT' after consolidate_trades
        qty = trade['Quantity']
        price = trade['Price']
        time = trade['Time']
        date = trade['Date']
        
        if symbol not in positions:
            positions[symbol] = {'qty': 0, 'trades': []}
        
        curr_pos = positions[symbol]
        print(f"\n📊 Processing {side} {qty} {symbol} @ ${price:.2f}")
        print(f"  Current {symbol} balance: {curr_pos['qty']}")
        
        if side == 'LONG':  # This handles BUY orders
            remaining_qty = qty
            
            # First try to cover SHORT positions (negative balance)
            if curr_pos['qty'] < 0:
                cover_qty = min(qty, abs(curr_pos['qty']))
                
                # Find open SHORT positions to close
                for pos in reversed(curr_pos['trades']):
                    if pos['Side'] == 'SELL' and (pos['Exit Qty'] is None or pd.isna(pos['Exit Qty'])) and cover_qty > 0:
                        pos_cover = min(cover_qty, abs(pos['Qty']))
                        pos['Exit Qty'] = pos_cover
                        pos['Exit Price'] = price
                        pos['Exit Time'] = time
                        pos['Exit Date'] = date
                        cover_qty -= pos_cover
                        remaining_qty -= pos_cover
                        print(f"  → Covered {pos_cover} shares of SHORT position")
                        if cover_qty == 0:
                            break
            
            # Update running balance
            curr_pos['qty'] += qty
            
            # Add new LONG position if there's remaining quantity
            if remaining_qty > 0:
                new_trade = {
                    'Symbol': symbol,
                    'Qty': remaining_qty,
                    'Side': 'BUY',
                    'Entry Price': price,
                    'Entry Time': time,
                    'Entry Date': date,
                    'Notes': '',
                    'Exit Qty': None,
                    'Exit Price': None,
                    'Exit Time': None,
                    'Exit Date': None
                }
                curr_pos['trades'].append(new_trade)
                print(f"  → Added LONG position of {remaining_qty} shares")
            
        elif side == 'SHORT':  # This handles SELL orders
            remaining_sell = qty
            
            # First try to close existing LONG positions
            for pos in curr_pos['trades']:
                if pos['Side'] == 'BUY' and (pos['Exit Qty'] is None or pd.isna(pos['Exit Qty'])) and remaining_sell > 0:
                    pos_close = min(remaining_sell, pos['Qty'])
                    pos['Exit Qty'] = -pos_close
                    pos['Exit Price'] = price
                    pos['Exit Time'] = time
                    pos['Exit Date'] = date
                    remaining_sell -= pos_close
                    print(f"  → Closed {pos_close} shares of LONG position")
            
            # Update running balance
            curr_pos['qty'] -= qty
            
            # If there's still quantity to sell, create new SHORT position
            if remaining_sell > 0:
                new_trade = {
                    'Symbol': symbol,
                    'Qty': -remaining_sell,
                    'Side': 'SELL',
                    'Entry Price': price,
                    'Entry Time': time,
                    'Entry Date': date,
                    'Notes': '',
                    'Exit Qty': None,
                    'Exit Price': None,
                    'Exit Time': None,
                    'Exit Date': None
                }
                curr_pos['trades'].append(new_trade)
                print(f"  → Added SHORT position of {remaining_sell} shares")
        
        print(f"  → New {symbol} balance: {curr_pos['qty']}")
    
    # Convert all trades back to DataFrame
    all_trades = []
    for symbol_trades in positions.values():
        all_trades.extend(symbol_trades['trades'])
    
    # Sort by date and time
    df_result = pd.DataFrame(all_trades)
    if not df_result.empty:
        df_result['datetime'] = pd.to_datetime(df_result['Entry Date'] + ' ' + df_result['Entry Time'].astype(str))
        df_result = df_result.sort_values('datetime').drop('datetime', axis=1)
    
    return df_result

def update_master_sheet(consolidated_trades, folder_path):
    """Update master balance sheet with new trades after backing up"""
    try:
        base_path = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades"
        master_file = os.path.join(base_path, MASTER_FILE)
        backup_file = os.path.join(base_path, MASTER_BACKUP)
        
        # Create backup of current master file
        if os.path.exists(master_file):
            print(f"\n📑 Creating backup of master sheet...")
            # Read existing workbook with all sheets
            with pd.ExcelFile(master_file) as xls:
                all_sheets = {}
                for sheet_name in xls.sheet_names:
                    all_sheets[sheet_name] = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Save backup with all sheets
            with pd.ExcelWriter(backup_file, engine='openpyxl') as writer:
                for sheet_name, df in all_sheets.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"✅ Backup created: {os.path.basename(MASTER_BACKUP)}")
            
            # Load existing sheets with proper names - handle both old and new sheet names
            df_master = pd.DataFrame()
            df_raw_trades = pd.DataFrame()
            df_consolidated = pd.DataFrame()
            
            # Get Trades sheet (formerly Sheet1)
            if 'Trades' in all_sheets:
                df_master = all_sheets['Trades'].copy()
            elif 'Sheet1' in all_sheets:
                df_master = all_sheets['Sheet1'].copy()
            else:
                df_master = pd.DataFrame(columns=[
                    "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
                    "Entry Date", "Notes", "Exit Qty", "Exit Price", 
                    "Exit Time", "Exit Date"
                ])
            
            # Get Raw Trades sheet (formerly Trades)
            if 'Raw Trades' in all_sheets:
                df_raw_trades = all_sheets['Raw Trades'].copy()
            elif 'Trades' in all_sheets and 'Symbol' in all_sheets['Trades'].columns and 'Date' in all_sheets['Trades'].columns:
                # This is the old "Trades" sheet that should be "Raw Trades"
                df_raw_trades = all_sheets['Trades'].copy()
            else:
                df_raw_trades = pd.DataFrame(columns=[
                    "Symbol", "Date", "Time", "Side", "Quantity", "Price"
                ])
            
            # Get Consolidated Trades sheet
            if 'Consolidated Trades' in all_sheets:
                df_consolidated = all_sheets['Consolidated Trades'].copy()
            else:
                df_consolidated = pd.DataFrame(columns=[
                    "Symbol", "Date", "Time", "Side", "Quantity", "Avg_Price", "Total_Value"
                ])
                
        else:
            # Create new master file with headers
            df_master = pd.DataFrame(columns=[
                "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
                "Entry Date", "Notes", "Exit Qty", "Exit Price", 
                "Exit Time", "Exit Date"
            ])
            df_raw_trades = pd.DataFrame(columns=[
                "Symbol", "Date", "Time", "Side", "Quantity", "Price"
            ])
            df_consolidated = pd.DataFrame(columns=[
                "Symbol", "Date", "Time", "Side", "Quantity", "Avg_Price", "Total_Value"
            ])
        
        print(f"📊 Current data before processing:")
        print(f"   - Trades sheet: {len(df_master)} rows")
        print(f"   - Raw Trades sheet: {len(df_raw_trades)} rows")
        print(f"   - Consolidated Trades sheet: {len(df_consolidated)} rows")
        
        # Create unique identifier for existing trades in master sheet
        if not df_master.empty:
            df_master['trade_key'] = (
                df_master['Symbol'].astype(str) + '_' + 
                df_master['Qty'].astype(str) + '_' + 
                df_master['Side'].astype(str) + '_' + 
                df_master['Entry Price'].astype(str) + '_' + 
                df_master['Entry Time'].astype(str) + '_' + 
                df_master['Entry Date'].astype(str)
            )
        
        # Create unique identifier for existing trades in raw trades sheet
        if not df_raw_trades.empty:
            df_raw_trades['trade_key'] = (
                df_raw_trades['Symbol'].astype(str) + '_' + 
                df_raw_trades['Date'].astype(str) + '_' + 
                df_raw_trades['Time'].astype(str) + '_' + 
                df_raw_trades['Side'].astype(str) + '_' + 
                df_raw_trades['Quantity'].astype(str) + '_' + 
                df_raw_trades['Price'].astype(str)
            )
        
        # Create unique identifier for existing consolidated trades
        if not df_consolidated.empty:
            df_consolidated['trade_key'] = (
                df_consolidated['Symbol'].astype(str) + '_' + 
                df_consolidated['Date'].astype(str) + '_' + 
                df_consolidated['Side'].astype(str)
            )
        
        # Track new trades for all sheets
        new_position_trades = []
        new_raw_trades = []
        
        # Group consolidated trades by symbol, date, and side for the consolidated sheet
        consolidated_by_day = {}
        
        for trade in consolidated_trades:
            # Create trade keys
            position_trade_key = (
                f"{trade['Symbol']}_{trade['Quantity']}_{trade['Side']}_"
                f"{trade['Price']}_{trade['Time']}_{trade['Date']}"
            )
            
            raw_trade_key = (
                f"{trade['Symbol']}_{trade['Date']}_{trade['Time']}_{trade['Side']}_"
                f"{trade['Quantity']}_{trade['Price']}"
            )
            
            consolidated_trade_key = f"{trade['Symbol']}_{trade['Date']}_{trade['Side']}"
            
            # Add to raw trades sheet if not already exists
            if df_raw_trades.empty or raw_trade_key not in df_raw_trades['trade_key'].values:
                new_raw_trade = {
                    "Symbol": trade['Symbol'],
                    "Date": pd.to_datetime(trade['Date']).strftime('%Y-%m-%d'),
                    "Time": trade['Time'],
                    "Side": trade['Side'],
                    "Quantity": trade['Quantity'],
                    "Price": trade['Price']
                }
                new_raw_trades.append(new_raw_trade)
            
            # Group for consolidated trades sheet (by symbol, date, side)
            if consolidated_trade_key not in consolidated_by_day:
                consolidated_by_day[consolidated_trade_key] = {
                    "Symbol": trade['Symbol'],
                    "Date": pd.to_datetime(trade['Date']).strftime('%Y-%m-%d'),
                    "Side": trade['Side'],
                    "total_qty": 0,
                    "total_value": 0,
                    "time": trade['Time']  # Initialize with first trade's time
                }
            
            group = consolidated_by_day[consolidated_trade_key]
            group['total_qty'] += trade['Quantity']
            group['total_value'] += trade['Quantity'] * trade['Price']
            
            # Update time based on trade side:
            # LONG: keep earliest time
            # SHORT: keep latest time
            if trade['Side'] == 'LONG':
                group['time'] = min(group['time'], trade['Time'])
            else:  # SHORT
                group['time'] = max(group['time'], trade['Time'])
            
            # Add LONG positions to master sheet for position tracking
            if trade['Side'] in ['BUY', 'LONG']:
                # Check if trade already exists in master
                if df_master.empty or position_trade_key not in df_master['trade_key'].values:
                    new_trade = {
                        "Symbol": trade['Symbol'],
                        "Qty": trade['Quantity'],
                        "Side": 'LONG',
                        "Entry Price": trade['Price'],
                        "Entry Time": trade['Time'],
                        "Entry Date": pd.to_datetime(trade['Date']).strftime('%Y-%m-%d'),
                        "Notes": "",
                        "Exit Qty": None,
                        "Exit Price": None,
                        "Exit Time": None,
                        "Exit Date": None
                    }
                    new_position_trades.append(new_trade)
        
        # Create new consolidated trades for the consolidated sheet
        new_consolidated_trades = []
        for key, group in consolidated_by_day.items():
            # Check if this consolidated trade already exists
            if df_consolidated.empty or key not in df_consolidated['trade_key'].values:
                # Fix the average price calculation for SHORT positions
                if group['total_qty'] != 0:
                    avg_price = abs(group['total_value'] / group['total_qty'])
                else:
                    avg_price = 0
                    
                new_consolidated_trade = {
                    "Symbol": group['Symbol'],
                    "Date": group['Date'],
                    "Time": group['time'],
                    "Side": group['Side'],
                    "Quantity": group['total_qty'],
                    "Avg_Price": avg_price,
                    "Total_Value": group['total_value']
                }
                new_consolidated_trades.append(new_consolidated_trade)
        
        # APPEND new trades to respective DataFrames (not replace)
        if new_position_trades:
            df_new_positions = pd.DataFrame(new_position_trades)
            df_master = pd.concat([df_master, df_new_positions], ignore_index=True)
        
        if new_raw_trades:
            df_new_raw = pd.DataFrame(new_raw_trades)
            df_raw_trades = pd.concat([df_raw_trades, df_new_raw], ignore_index=True)
        
        if new_consolidated_trades:
            df_new_consolidated = pd.DataFrame(new_consolidated_trades)
            df_consolidated = pd.concat([df_consolidated, df_new_consolidated], ignore_index=True)
        
        # Drop the temporary trade_key columns before saving
        df_master = df_master.drop('trade_key', axis=1, errors='ignore')
        df_raw_trades = df_raw_trades.drop('trade_key', axis=1, errors='ignore')
        df_consolidated = df_consolidated.drop('trade_key', axis=1, errors='ignore')
        
        # Match SELL trades to open positions using FIFO
        df_master = match_trades_fifo(df_master, consolidated_trades)
        
        # Final sort and cleanup for master sheet
        if not df_master.empty:
            df_master['datetime'] = pd.to_datetime(df_master['Entry Date'] + ' ' + df_master['Entry Time'])
            df_master = df_master.sort_values('datetime').drop('datetime', axis=1)
            
            # Remove any duplicate rows
            df_master = df_master.drop_duplicates(
                subset=['Symbol', 'Qty', 'Side', 'Entry Price', 'Entry Time', 'Entry Date'],
                keep='first'
            )
        
        # Sort raw trades sheet by date and time
        if not df_raw_trades.empty:
            df_raw_trades['datetime'] = pd.to_datetime(df_raw_trades['Date'] + ' ' + df_raw_trades['Time'])
            df_raw_trades = df_raw_trades.sort_values('datetime').drop('datetime', axis=1)
        
        # Sort consolidated trades sheet by date
        if not df_consolidated.empty:
            df_consolidated['datetime'] = pd.to_datetime(df_consolidated['Date'])
            df_consolidated = df_consolidated.sort_values(['datetime', 'Symbol', 'Side']).drop('datetime', axis=1)
        
        # Save updated master file with proper sheet names
        with pd.ExcelWriter(master_file, engine='openpyxl') as writer:
            df_master.to_excel(writer, sheet_name='Trades', index=False)  # Position tracking
            df_raw_trades.to_excel(writer, sheet_name='Raw Trades', index=False)  # All individual trades
            df_consolidated.to_excel(writer, sheet_name='Consolidated Trades', index=False)  # Daily consolidation
        
        parent_dir = os.path.basename(os.path.dirname(master_file))
        filename = os.path.basename(master_file)
        print(f"✅ Updated {parent_dir}/{filename}:")
        print(f"   - Added {len(new_position_trades)} new positions to 'Trades' sheet")
        print(f"   - Added {len(new_raw_trades)} new trades to 'Raw Trades' sheet")
        print(f"   - Added {len(new_consolidated_trades)} new entries to 'Consolidated Trades' sheet")
        print(f"📊 Final data after processing:")
        print(f"   - Trades sheet: {len(df_master)} rows")
        print(f"   - Raw Trades sheet: {len(df_raw_trades)} rows")
        print(f"   - Consolidated Trades sheet: {len(df_consolidated)} rows")
        
    except Exception as e:
        print(f"❌ Error updating master sheet: {str(e)}")
        import traceback
        traceback.print_exc()

def manage_processed_files(folder_path, pdf_file=None, check_only=False):
    """Track processed PDF files using a JSON file"""
    tracking_file = os.path.join(folder_path, PROCESSED_FILE)  # Use test file if in test mode
    
    # Load existing processed files
    if os.path.exists(tracking_file):
        with open(tracking_file, 'r') as f:
            processed_files = json.load(f)
    else:
        processed_files = []
    
    if check_only:
        return processed_files
    
    # Add new file and save
    if pdf_file and pdf_file not in processed_files:
        processed_files.append(pdf_file)
        with open(tracking_file, 'w') as f:
            json.dump(processed_files, f, indent=2)
    
    return processed_files

def reset_test_files(folder_path):
    """Reset test files before running script"""
    if TEST_MODE:
        base_path = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades"
        
        # Reset processed files JSON
        test_json_path = os.path.join(folder_path, PROCESSED_FILE)
        with open(test_json_path, 'w') as f:
            json.dump([], f)
        print("🔄 Reset processed files tracking")
        
        # Create empty test master copy if it doesn't exist
        test_master_path = os.path.join(base_path, MASTER_FILE)
        if not os.path.exists(test_master_path):
            df_empty = pd.DataFrame(columns=[
                "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
                "Entry Date", "Notes", "Exit Qty", "Exit Price", 
                "Exit Time", "Exit Date"
            ])
            df_empty.to_excel(test_master_path, index=False)
        print("🔄 Reset master copy test file")

def reset_master_sheet():
    """Reset all spreadsheets and processed files tracking"""
    try:
        base_path = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades"
        master_file = os.path.join(base_path, MASTER_FILE)
        backup_file = os.path.join(base_path, MASTER_BACKUP)
        
        print(f"\n🔄 Resetting all spreadsheets and processed files...")
        
        # Create backup before reset
        if os.path.exists(master_file):
            print(f"📑 Creating backup before reset...")
            with pd.ExcelFile(master_file) as xls:
                all_sheets = {}
                for sheet_name in xls.sheet_names:
                    all_sheets[sheet_name] = pd.read_excel(xls, sheet_name=sheet_name)
            
            # Save backup with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            reset_backup = os.path.join(base_path, f"master_pre_reset_{timestamp}.xlsx")
            with pd.ExcelWriter(reset_backup, engine='openpyxl') as writer:
                for sheet_name, df in all_sheets.items():
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
            print(f"✅ Pre-reset backup created: {os.path.basename(reset_backup)}")
        
        # Create fresh empty sheets with headers only
        df_master = pd.DataFrame(columns=[
            "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
            "Entry Date", "Notes", "Exit Qty", "Exit Price", 
            "Exit Time", "Exit Date"
        ])
        
        df_raw_trades = pd.DataFrame(columns=[
            "Symbol", "Date", "Time", "Side", "Quantity", "Price"
        ])
        
        df_consolidated = pd.DataFrame(columns=[
            "Symbol", "Date", "Time", "Side", "Quantity", "Avg_Price", "Total_Value"
        ])
        
        # Save empty master file
        with pd.ExcelWriter(master_file, engine='openpyxl') as writer:
            df_master.to_excel(writer, sheet_name='Trades', index=False)
            df_raw_trades.to_excel(writer, sheet_name='Raw Trades', index=False)
            df_consolidated.to_excel(writer, sheet_name='Consolidated Trades', index=False)
        
        # Reset all processed_files.json in subdirectories
        reset_count = 0
        for root, dirs, files in os.walk(base_path):
            processed_file = os.path.join(root, "processed_files.json")
            if os.path.exists(processed_file):
                # Clear the processed files list
                with open(processed_file, 'w') as f:
                    json.dump([], f, indent=2)
                reset_count += 1
                rel_path = os.path.relpath(root, base_path)
                print(f"   📂 Reset processed files in: {rel_path}")
        
        # Remove backup file if it exists
        if os.path.exists(backup_file):
            os.remove(backup_file)
        
        print(f"✅ Reset complete!")
        print(f"   - Cleared all 3 spreadsheet tabs (keeping headers)")
        print(f"   - Reset {reset_count} processed_files.json files")
        print(f"   - All trade data has been cleared")
        print(f"   - You can now reprocess folders from scratch")
        
    except Exception as e:
        print(f"❌ Error during reset: {str(e)}")

def process_folder(date_str):
    """Process a single folder based on date string"""
    try:
        folder_path = get_folder_path(date_str)
        print(f"\n📁 Processing folder: {os.path.basename(folder_path)}")
        
        # Reset test files if in test mode
        if TEST_MODE:
            reset_test_files(folder_path)
        
        # Get all trades from PDFs in the folder
        all_trades = gather_all_trades(folder_path)
        
        if not all_trades:
            print("No new trades found to process.")
            return
        
        # Consolidate trades by symbol and date
        consolidated_trades = consolidate_trades(all_trades)
        
        print(f"\n📊 Trade Summary:")
        print(f"   - Total individual trades: {len(all_trades)}")
        print(f"   - Consolidated trades: {len(consolidated_trades)}")
        
        # Update master sheet with consolidated trades
        update_master_sheet(consolidated_trades, folder_path)
        
        # Check and display open positions
        check_open_positions(folder_path)
        
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Error: {str(e)}")
    except Exception as e:
        print(f"❌ Unexpected error processing folder: {str(e)}")

def main():
    print("=" * 60)
    print("📊 TRADE LOG FORMATTER")
    print("=" * 60)
    

    choice = input("\n'RESET' or enter a date (e.g. 01.2025): ").strip()
    
    if choice == 'RESET':
        confirm = input("⚠️  This will DELETE ALL trade data. Type 'y' to confirm: ").strip()
        if confirm == 'y':
            reset_master_sheet()
        else:
            print("❌ Reset cancelled")
    else:
        if choice:
            process_folder(choice)
        else:
            print("❌ Please enter a valid folder name")

if __name__ == "__main__":
    main()