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
    all_trades = []
    pdf_files = glob(os.path.join(folder, "DailyTradeReport.*.pdf"))
    processed_files = manage_processed_files(folder, check_only=True)
    
    new_files = False
    for pdf in pdf_files:
        filename = os.path.basename(pdf)
        if filename in processed_files:
            debug_print(f"⏭️  Skipping previously processed file: {filename}")
            continue
            
        new_files = True
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
        master_file = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades/master-copy.xlsx"
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
    """Match trades using FIFO method, handling both long and short positions"""
    df_new = df_master.copy()
    
    # Ensure numeric types
    df_new['Qty'] = pd.to_numeric(df_new['Qty'])
    df_new['Entry Price'] = pd.to_numeric(df_new['Entry Price'])
    
    # Sort trades chronologically
    consolidated_trades = sorted(consolidated_trades, key=lambda x: (x['Date'], x['Time']))
    
    for trade in consolidated_trades:
        trade['Side'] = 'LONG' if trade['Side'] == 'BUY' else 'SHORT'
        symbol = trade['Symbol']
        qty = abs(trade['Quantity'])
        price = trade['Price']
        time = trade['Time']
        date = trade['Date']
        
        if trade['Side'] == "SHORT":
            # Look for matching LONG positions to close
            mask = (
                (df_new['Symbol'] == symbol) & 
                (df_new['Side'] == 'LONG') &
                (df_new['Exit Qty'].isna()) &  # Only get unfilled positions
                (pd.to_datetime(df_new['Entry Date'] + ' ' + df_new['Entry Time']) 
                 <= pd.to_datetime(date + ' ' + time))
            )
            
            open_positions = df_new[mask].sort_values(['Entry Date', 'Entry Time'])
            remaining_short_qty = qty
            
            if not open_positions.empty:
                for idx in open_positions.index:
                    if remaining_short_qty <= 0:
                        break
                        
                    position_qty = df_new.at[idx, 'Qty']
                    
                    if remaining_short_qty >= position_qty:
                        # Full position exit
                        df_new.at[idx, 'Exit Qty'] = position_qty
                        df_new.at[idx, 'Exit Price'] = price
                        df_new.at[idx, 'Exit Time'] = time
                        df_new.at[idx, 'Exit Date'] = date
                        remaining_short_qty -= position_qty
                    else:
                        # Partial position exit
                        df_new.at[idx, 'Exit Qty'] = remaining_short_qty
                        df_new.at[idx, 'Exit Price'] = price
                        df_new.at[idx, 'Exit Time'] = time
                        df_new.at[idx, 'Exit Date'] = date
                        remaining_short_qty = 0
            
            # If there's remaining quantity after closing LONG positions, create new SHORT position
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
                print(f"  📉 New short position: {symbol} {remaining_short_qty} shares @ {price}")
        
        else:  # LONG position
            # First check if this covers any existing SHORT positions
            mask = (
                (df_new['Symbol'] == symbol) & 
                (df_new['Side'] == 'SHORT') &
                (df_new['Exit Qty'].isna()) &
                (pd.to_datetime(df_new['Entry Date'] + ' ' + df_new['Entry Time']) 
                 <= pd.to_datetime(date + ' ' + time))
            )
            
            short_positions = df_new[mask].sort_values(['Entry Date', 'Entry Time'])
            remaining_long_qty = qty
            
            if not short_positions.empty:
                for idx in short_positions.index:
                    if remaining_long_qty <= 0:
                        break
                    
                    short_qty = df_new.at[idx, 'Qty']
                    exit_qty = min(remaining_long_qty, short_qty)
                    
                    df_new.at[idx, 'Exit Qty'] = exit_qty
                    df_new.at[idx, 'Exit Price'] = price
                    df_new.at[idx, 'Exit Time'] = time
                    df_new.at[idx, 'Exit Date'] = date
                    
                    remaining_long_qty -= exit_qty
            
            # Add remaining as new LONG position
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
    
    # Clear duplicate Exit columns if they exist
    df_new = df_new.loc[:, ~df_new.columns.duplicated()]
    
    return df_new

def update_master_sheet(consolidated_trades, folder_path):
    """Update master balance sheet with new trades after backing up, sorted by date and time"""
    try:
        # Define file paths
        master_file = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades/master-copy.xlsx"
        backup_file = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades/master-copy-backup.xlsx"
        
        # Create backup of current master file
        if os.path.exists(master_file):
            print(f"\n📑 Creating backup of master sheet...")
            df_master = pd.read_excel(master_file)
            df_master.to_excel(backup_file, index=False)
            print(f"✅ Backup created: master-copy-backup.xlsx")
        else:
            # Create new master file with headers if it doesn't exist
            df_master = pd.DataFrame(columns=[
                "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
                "Entry Date", "Notes", "Exit Qty", "Exit Price", 
                "Exit Time", "Exit Date"
            ])
        
        # Prepare new LONG trades for append
        new_trades = []
        for trade in consolidated_trades:
            if trade['Side'] in ['BUY', 'LONG']:  # Handle both old and new formats
                new_trade = {
                    "Symbol": trade['Symbol'],
                    "Qty": trade['Quantity'],
                    "Side": 'LONG',  # Always use LONG here
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
            # Convert new trades to DataFrame and sort
            df_new = pd.DataFrame(new_trades)
            df_new['datetime'] = pd.to_datetime(df_new['Entry Date'] + ' ' + df_new['Entry Time'])
            df_new = df_new.sort_values('datetime')
            df_new = df_new.drop('datetime', axis=1)
            
            # Append new BUY trades
            df_master = pd.concat([df_master, df_new], ignore_index=True)
        
        # Match SELL trades to open positions using FIFO
        df_master = match_trades_fifo(df_master, consolidated_trades)
        
        # Sort entire master sheet by entry date/time
        df_master['datetime'] = pd.to_datetime(df_master['Entry Date'] + ' ' + df_master['Entry Time'])
        df_master = df_master.sort_values('datetime')
        df_master = df_master.drop('datetime', axis=1)
        
        # Save updated master file
        df_master.to_excel(master_file, index=False)
        print(f"✅ Updated master sheet with {len(new_trades)} new trades and matched SELL orders")
        
    except Exception as e:
        print(f"❌ Error updating master sheet: {str(e)}")

def manage_processed_files(folder_path, pdf_file=None, check_only=False):
    """Track processed PDF files using a JSON file"""
    tracking_file = os.path.join(folder_path, "processed_files.json")
    
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

def main():
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
            
        # Continue with existing code...
        # Consolidate trades
        consolidated_trades = consolidate_trades(all_trades)
        print(f"\n📊 Consolidated {len(all_trades)} trades into {len(consolidated_trades)} positions "
              f"(LONG/SHORT)")
        
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