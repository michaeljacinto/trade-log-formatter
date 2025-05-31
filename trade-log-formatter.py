import fitz  # PyMuPDF
import re
import os
import csv
from glob import glob
import pandas as pd
from datetime import datetime, timedelta
import json

# Configuration
DEBUG = True  # Set to True to enable debug printing
# Set default test date to yesterday
yesterday = datetime.now() - timedelta(days=1)
DEFAULT_TEST_DATE = datetime.now().strftime("%m.%Y")

# Add at the top with other configurations
TEST_MODE = True  # Set to True to use test files
MASTER_FILE = "master-copy-test.xlsx" if TEST_MODE else "master-copy.xlsx"
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
                time_to_use = min(existing['earliest_time'], trade['Time'])
            
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

def check_open_positions(folder_path, new_trades=None):
    """Check master copy for open positions and maintain running balance"""
    try:
        master_file = os.path.join("/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades", MASTER_FILE)
        df = pd.read_excel(master_file)
        
        # Initialize positions dictionary
        positions = {}
        
        # First process existing positions from master file
        for _, row in df.iterrows():
            symbol = row['Symbol']
            side = row['Side']
            qty = row['Qty']
            price = row['Entry Price']
            date = pd.to_datetime(row['Entry Date'])
            exit_qty = row['Exit Qty'] if pd.notna(row['Exit Qty']) else 0
            
            if symbol not in positions:
                positions[symbol] = {
                    'qty': 0,
                    'total_cost': 0,
                    'date': date,
                    'trades': []
                }
            
            # Update position based on side and exit quantity
            if side == 'LONG':
                positions[symbol]['qty'] += (qty - exit_qty)
                positions[symbol]['total_cost'] += (qty - exit_qty) * price
            else:  # SHORT
                positions[symbol]['qty'] -= (qty - exit_qty)
                positions[symbol]['total_cost'] -= (qty - exit_qty) * price
            
            positions[symbol]['date'] = min(positions[symbol]['date'], date)
            positions[symbol]['trades'].append({
                'side': side,
                'qty': qty,
                'price': price,
                'date': date,
                'exit_qty': exit_qty
            })
        
        # Process any new trades if provided
        if new_trades:
            for trade in new_trades:
                symbol = trade['Symbol']
                side = trade['Side']
                qty = trade['Quantity']
                price = trade['Price']
                date = pd.to_datetime(trade['Date'])
                
                if symbol not in positions:
                    positions[symbol] = {
                        'qty': 0,
                        'total_cost': 0,
                        'date': date,
                        'trades': []
                    }
                
                # Update running balance
                if side in ['LONG', 'BUY']:
                    positions[symbol]['qty'] += qty
                    positions[symbol]['total_cost'] += qty * price
                else:  # SHORT or SELL
                    positions[symbol]['qty'] -= qty
                    positions[symbol]['total_cost'] -= qty * price
                
                positions[symbol]['trades'].append({
                    'side': side,
                    'qty': qty,
                    'price': price,
                    'date': date,
                    'exit_qty': 0
                })
        
        # Print running balances
        print("\n📊 Current Position Balances:")
        print("  Symbol  Net Pos    Avg Price    Total Value    Since")
        print("  " + "-" * 55)
        
        grand_total = 0
        for symbol, data in positions.items():
            if data['qty'] != 0:  # Only show active positions
                avg_price = abs(data['total_cost'] / data['qty']) if data['qty'] != 0 else 0
                position_value = data['total_cost']
                grand_total += position_value
                
                print(f"  {symbol:6} {data['qty']:8.0f} @ ${avg_price:8,.2f} = ${position_value:11,.2f}  "
                      f"{data['date'].strftime('%Y-%m-%d')}")
        
        print("  " + "-" * 55)
        print(f"  Total Portfolio Value: ${grand_total:,.2f}")
        
        return positions
            
    except FileNotFoundError:
        print(f"\n⚠️  Master copy not found: {master_file}")
        return {}
    except Exception as e:
        print(f"\n❌ Error reading master copy: {str(e)}")
        return {}

def match_trades_fifo(df_master, consolidated_trades):
    """Match trades using FIFO method and maintain running balances"""
    df_new = df_master.copy()
    
    # Initialize running positions dictionary
    running_positions = {}
    
    # First, load existing positions from master sheet
    for idx, row in df_new.iterrows():
        symbol = row['Symbol']
        if symbol not in running_positions:
            running_positions[symbol] = []
            
        # Add position to running balance
        position = {
            'idx': idx,
            'qty': row['Qty'],
            'remaining_qty': row['Qty'] - (row['Exit Qty'] if pd.notna(row['Exit Qty']) else 0),
            'price': row['Entry Price'],
            'time': row['Entry Time'],
            'date': row['Entry Date'],
            'side': row['Side']
        }
        running_positions[symbol].append(position)
    
    # Sort trades chronologically
    consolidated_trades = sorted(consolidated_trades, key=lambda x: (x['Date'], x['Time']))
    
    for trade in consolidated_trades:
        symbol = trade['Symbol']
        qty = abs(trade['Quantity'])
        price = trade['Price']
        time = trade['Time']
        date = trade['Date']
        side = 'LONG' if trade['Side'] in ['BUY', 'LONG'] else 'SHORT'
        
        if side == 'SHORT':
            # Check for existing LONG positions to offset
            remaining_short_qty = qty
            
            if symbol in running_positions:
                for pos in running_positions[symbol]:
                    if pos['side'] == 'LONG' and pos['remaining_qty'] > 0:
                        # Calculate how much to offset
                        offset_qty = min(remaining_short_qty, pos['remaining_qty'])
                        
                        # Update exit information in master sheet
                        df_new.at[pos['idx'], 'Exit Qty'] = (
                            df_new.at[pos['idx'], 'Exit Qty'] if pd.notna(df_new.at[pos['idx'], 'Exit Qty']) else 0
                        ) + offset_qty
                        df_new.at[pos['idx'], 'Exit Price'] = price
                        df_new.at[pos['idx'], 'Exit Time'] = time
                        df_new.at[pos['idx'], 'Exit Date'] = date
                        
                        # Update running position
                        pos['remaining_qty'] -= offset_qty
                        remaining_short_qty -= offset_qty
                        
                        if remaining_short_qty == 0:
                            break
            
            # If there's still remaining short quantity, create new SHORT position
            if remaining_short_qty > 0:
                new_short = {
                    "Symbol": symbol,
                    "Qty": remaining_short_qty,
                    "Side": "SHORT",
                    "Entry Price": price,
                    "Entry Time": time,
                    "Entry Date": date,
                    "Notes": "Short Position",
                    "Exit Qty": None,
                    "Exit Price": None,
                    "Exit Time": None,
                    "Exit Date": None
                }
                df_new = pd.concat([df_new, pd.DataFrame([new_short])], ignore_index=True)
                
                # Add to running positions
                if symbol not in running_positions:
                    running_positions[symbol] = []
                running_positions[symbol].append({
                    'idx': len(df_new) - 1,
                    'qty': remaining_short_qty,
                    'remaining_qty': remaining_short_qty,
                    'price': price,
                    'time': time,
                    'date': date,
                    'side': 'SHORT'
                })
        
        else:  # LONG position
            # Similar logic for LONG positions offsetting existing SHORT positions
            remaining_long_qty = qty
            
            if symbol in running_positions:
                for pos in running_positions[symbol]:
                    if pos['side'] == 'SHORT' and pos['remaining_qty'] > 0:
                        offset_qty = min(remaining_long_qty, pos['remaining_qty'])
                        
                        df_new.at[pos['idx'], 'Exit Qty'] = (
                            df_new.at[pos['idx'], 'Exit Qty'] if pd.notna(df_new.at[pos['idx'], 'Exit Qty']) else 0
                        ) + offset_qty
                        df_new.at[pos['idx'], 'Exit Price'] = price
                        df_new.at[pos['idx'], 'Exit Time'] = time
                        df_new.at[pos['idx'], 'Exit Date'] = date
                        
                        pos['remaining_qty'] -= offset_qty
                        remaining_long_qty -= offset_qty
                        
                        if remaining_long_qty == 0:
                            break
            
            # Add remaining long quantity as new position
            if remaining_long_qty > 0:
                new_long = {
                    "Symbol": symbol,
                    "Qty": remaining_long_qty,
                    "Side": "LONG",
                    "Entry Price": price,
                    "Entry Time": time,
                    "Entry Date": date,
                    "Notes": "",
                    "Exit Qty": None,
                    "Exit Price": None,
                    "Exit Time": None,
                    "Exit Date": None
                }
                df_new = pd.concat([df_new, pd.DataFrame([new_long])], ignore_index=True)
                
                if symbol not in running_positions:
                    running_positions[symbol] = []
                running_positions[symbol].append({
                    'idx': len(df_new) - 1,
                    'qty': remaining_long_qty,
                    'remaining_qty': remaining_long_qty,
                    'price': price,
                    'time': time,
                    'date': date,
                    'side': 'LONG'
                })
    
    # Sort the final dataframe by date and time
    df_new['datetime'] = pd.to_datetime(df_new['Entry Date'] + ' ' + df_new['Entry Time'])
    df_new = df_new.sort_values('datetime').drop('datetime', axis=1)
    
    return df_new

def update_master_sheet(consolidated_trades, folder_path):
    """Update master balance sheet with new trades after backing up"""
    try:
        base_path = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades"
        master_file = os.path.join(base_path, MASTER_FILE)
        backup_file = os.path.join(base_path, MASTER_BACKUP)
        
        # Create backup of current master file
        if os.path.exists(master_file):
            print(f"\n📑 Creating backup of master sheet...")
            df_master = pd.read_excel(master_file)
            df_master.to_excel(backup_file, index=False)
            print(f"✅ Backup created: master-copy-backup.xlsx")
        else:
            # Create new master file with headers
            df_master = pd.DataFrame(columns=[
                "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
                "Entry Date", "Notes", "Exit Qty", "Exit Price", 
                "Exit Time", "Exit Date"
            ])
        
        # Track unique trades to prevent duplication
        unique_trades = set()
        new_trades = []
        
        for trade in consolidated_trades:
            # Create unique key for trade
            trade_key = (
                trade['Symbol'],
                trade['Quantity'],
                trade['Side'],
                trade['Price'],
                trade['Time'],
                trade['Date']
            )
            
            # Only process if we haven't seen this trade before
            if trade_key not in unique_trades and trade['Side'] in ['BUY', 'LONG']:
                unique_trades.add(trade_key)
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
                new_trades.append(new_trade)
        
        if new_trades:
            # Convert new trades to DataFrame
            df_new = pd.DataFrame(new_trades)
            
            # Sort by date and time
            df_new['datetime'] = pd.to_datetime(df_new['Entry Date'] + ' ' + df_new['Entry Time'])
            df_new = df_new.sort_values('datetime')
            df_new = df_new.drop('datetime', axis=1)
            
            # Append new trades
            df_master = pd.concat([df_master, df_new], ignore_index=True)
        
        # Match SELL trades to open positions using FIFO
        df_master = match_trades_fifo(df_master, consolidated_trades)
        
        # Final sort
        df_master['datetime'] = pd.to_datetime(df_master['Entry Date'] + ' ' + df_master['Entry Time'])
        df_master = df_master.sort_values('datetime').drop('datetime', axis=1)
        
        # Save updated master file
        df_master.to_excel(master_file, index=False)
        print(f"✅ Updated master sheet with {len(new_trades)} new trades and matched SELL orders")
        
    except Exception as e:
        print(f"❌ Error updating master sheet: {str(e)}")

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

def main():
    # Reset test files if in test mode
    if TEST_MODE:
        print("\n🧪 Running in test mode")
        folder_path = get_folder_path(DEFAULT_TEST_DATE)
        reset_test_files(folder_path)
    
    # Get date input from user, default to test date if empty
    date_input = input("Enter month-year (MM.YYYY) or press Enter for default test date: ").strip()
    
    try:
        if not date_input:
            date_input = DEFAULT_TEST_DATE
            print(f"Using test date: {date_input}")
            
        # Get folder path based on month-year
        folder_path = get_folder_path(date_input)
        print(f"📂 Processing trades from: {folder_path}")
        
        # Check for open positions first
        open_positions = check_open_positions(folder_path)
        
        # Process trades
        all_trades = gather_all_trades(folder_path)
        
        # Exit if no new trades
        if not all_trades:
            print("✅ No updates needed for master sheet")
            return
        
        # Consolidate trades
        consolidated_trades = consolidate_trades(all_trades)
        
        # Update running balances with new trades
        check_open_positions(folder_path, consolidated_trades)
        
        # Generate output filename with date
        date_obj = datetime.strptime(date_input, "%m.%Y")
        output_filename = f"trades_{date_obj.strftime('%Y%m')}_consolidated.csv"
        
        # Export consolidated trades
        export_to_csv(consolidated_trades, output_filename, folder_path)
        
        # Update master balance sheet
        update_master_sheet(consolidated_trades, folder_path)
        
    except (ValueError, FileNotFoundError) as e:
        print(f"❌ Error: {str(e)}")
        return

if __name__ == "__main__":
    main()