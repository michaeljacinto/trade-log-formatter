import fitz  # PyMuPDF
import re
import os
import csv
from glob import glob
from datetime import datetime
import pandas as pd  # Add this import at the top

# Configuration
DEBUG = False  # Set to True to enable debug printing
DEFAULT_TEST_DATE = "05.19.25"

def debug_print(*args, **kwargs):
    """Wrapper for debug printing"""
    if DEBUG:
        print(*args, **kwargs)

def get_folder_path(date_str):
    """Find folder containing the input date within its date range"""
    try:
        # Parse input date string (e.g., 5.20.25 -> 2025-05-20)
        target_date = datetime.strptime(date_str, "%m.%d.%y")
        
        # Get base directory
        base_path = "/Users/michaeljacinto/Library/CloudStorage/OneDrive-Personal/Desktop/trades"
        
        # List all folders
        for folder in os.listdir(base_path):
            if '-' in folder:  # Check if folder name contains a date range
                start_str, end_str = folder.split('-')
                
                # Convert date range strings to datetime objects
                try:
                    start_date = datetime.strptime(start_str.strip(), "%m.%d.%y")
                    end_date = datetime.strptime(end_str.strip(), "%m.%d.%y")
                    
                    # Check if target date falls within range
                    if start_date <= target_date <= end_date:
                        folder_path = os.path.join(base_path, folder)
                        return folder_path
                except ValueError:
                    continue  # Skip folders that don't match expected format
        
        raise FileNotFoundError(f"No folder found containing date: {date_str}")
            
    except ValueError:
        raise ValueError("Invalid date format. Please use MM.DD.YY (e.g., 5.20.25)")


def parse_trade_line(line):
    """Parse a single trade line from PDF report"""
    # More flexible pattern to catch variations
    pattern = re.compile(r"""
        U\*\*\*\d+\s+               # Account ID (masked)
        (?P<symbol>[A-Z]+)\s+       # Symbol (uppercase letters)
        (?P<trade_date>\d{4}-\d{2}-\d{2}),?\s*  # Trade Date (optional comma)
        (?P<trade_time>\d{2}:\d{2}:\d{2})\s*    # Trade Time
        (?P<settle_date>\d{4}-\d{2}-\d{2})\s*   # Settle Date
        [-\s]*                      # Exchange separator (more flexible)
        (?P<type>BUY|SELL)\s*      # Trade Type
        (?P<quantity>\d+)\s*        # Quantity
        (?P<price>\d+\.?\d*)\s*     # Price (more flexible decimal)
        [-\d.,\s]*                  # Proceeds (more flexible)
    """, re.VERBOSE | re.IGNORECASE)  # Added case-insensitive flag

    match = pattern.search(line)
    if not match:
        # Analyze why the pattern failed to match
        checks = [
            ("Account ID", r"U\*\*\*\d+"),
            ("Symbol", r"[A-Z]+"),
            ("Trade Date", r"\d{4}-\d{2}-\d{2}"),
            ("Time", r"\d{2}:\d{2}:\d{2}"),
            ("Trade Type", r"BUY|SELL"),
            ("Quantity", r"\d+"),
            ("Price", r"\d+\.?\d*")
        ]
        
        print("\n  🔍 Pattern match failure analysis:")
        for check_name, check_pattern in checks:
            if not re.search(check_pattern, line):
                print(f"    ❌ Missing {check_name}")
        print(f"    📝 Raw text: {line[:100]}...")
        return None

    trade_data = {
        "Symbol": match.group("symbol"),
        "Date": match.group("trade_date"),
        "Time": match.group("trade_time"),
        "Quantity": int(match.group("quantity")),
        "Price": float(match.group("price")),
        "Side": "BUY" if match.group("type").upper() == "BUY" else "SELL"
    }
    
    # print(f"💱 Trade: {trade_data['Side']} {trade_data['Quantity']} {trade_data['Symbol']} @ ${trade_data['Price']:.2f} ({trade_data['Date']} {trade_data['Time']})")
    return trade_data

def extract_trades_from_pdf(file_path):
    """Extract all trades from a PDF file"""
    trades = []
    try:
        doc = fitz.open(file_path)
        debug_print(f"\n📄 Processing: {os.path.basename(file_path)}")
        
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
                            # Debug line numbers and values
                            debug_print(f"\n  🔍 Debug values at line {i}:")
                            debug_print(f"    Account: {lines[i]}")
                            debug_print(f"    Symbol: {lines[i+1]}")
                            debug_print(f"    DateTime: {lines[i+2]}")
                            debug_print(f"    Type: {lines[i+5]}")
                            debug_print(f"    Quantity: {lines[i+6]}")
                            debug_print(f"    Price: {lines[i+7]}")

                            # Extract trade data from next lines
                            account = lines[i]      # U***3749
                            symbol = lines[i+1]     # HIMS
                            datetime = lines[i+2]   # 2025-05-19, 09:30:40
                            trade_type = lines[i+5] # BUY/SELL
                            quantity = lines[i+6]   # 35
                            price = lines[i+7]      # 62.3950
                            
                            # Skip if this is a Total line
                            if "Total" not in symbol:
                                trade_data = {
                                    "Symbol": symbol.split()[0],  # Remove "(Stock)" if present
                                    "Date": datetime.split(',')[0],
                                    "Time": datetime.split(',')[1].strip(),
                                    "Quantity": int(quantity.strip()),  # Convert quantity to int
                                    "Price": float(price.strip()),     # Convert price to float
                                    "Side": "BUY" if trade_type.upper() == "BUY" else "SELL"
                                }
                                
                                # print(f"💱 Trade: {trade_data['Side']} {trade_data['Quantity']} {trade_data['Symbol']} "
                                #       f"@ ${trade_data['Price']:.2f} ({trade_data['Date']} {trade_data['Time']})")
                                
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
                        
        doc.close()
        print(f"\n  ✅ Found {len(trades)} trades\n")
        
    except Exception as e:
        print(f"❌ Error processing {file_path}: {str(e)}")
    
    return trades

def gather_all_trades(folder):
    all_trades = []
    pdf_files = glob(os.path.join(folder, "DailyTradeReport.*.pdf"))
    for pdf in pdf_files:
        trades = extract_trades_from_pdf(pdf)
        all_trades.extend(trades)
    return all_trades

def export_to_csv(trades, output_file, folder_path):
    """Export trades to CSV file in the same folder as PDFs"""
    if not trades:
        print("No trades found to export.")
        return

    # Updated column order
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
        key = (trade['Symbol'], trade['Date'], trade['Side'])
        
        if key in consolidated:
            existing = consolidated[key]
            # Calculate new total quantity and weighted average price
            total_qty = existing['Quantity'] + trade['Quantity']
            weighted_price = (
                (existing['Quantity'] * existing['Price'] + 
                 trade['Quantity'] * trade['Price']) / total_qty
            )
            # Keep earliest time
            earliest_time = min(existing['Time'], trade['Time'])
            
            consolidated[key] = {
                'Symbol': trade['Symbol'],
                'Date': trade['Date'],
                'Time': earliest_time,
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
                print(f"  • {row['Symbol']}: {row['Qty']} shares @ ${row['Entry Price']:.2f} "
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

def main():
    # Get date input from user, default to test date if empty
    date_input = input("Enter trade date (MM.DD.YY) or press Enter for default test date: ").strip()
    
    try:
        if not date_input:
            date_input = DEFAULT_TEST_DATE
            print(f"Using test date: {date_input}")
        
        # Get folder path based on date
        folder_path = get_folder_path(date_input)
        print(f"📂 Processing trades from: {folder_path}")
        
        # Check for open positions first
        open_positions = check_open_positions(folder_path)
        
        # Process trades
        all_trades = gather_all_trades(folder_path)
        
        # Consolidate trades
        consolidated_trades = consolidate_trades(all_trades)
        print(f"\n📊 Consolidated {len(all_trades)} trades into {len(consolidated_trades)} positions")
        
        # Generate output filename with date
        date_obj = datetime.strptime(date_input, "%m.%d.%y")
        output_filename = f"trades_{date_obj.strftime('%Y%m%d')}_consolidated.csv"
        
        # Export consolidated trades
        export_to_csv(consolidated_trades, output_filename, folder_path)
        
    except (ValueError, FileNotFoundError) as e:
        print(f"❌ Error: {str(e)}")
        return

if __name__ == "__main__":
    main()