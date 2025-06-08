# Trade Log Formatter

A Python script that processes PDF trade reports and creates consolidated Excel spreadsheets for trade tracking and analysis.

## Features

- 📄 **PDF Processing**: Extracts trades from DailyTradeReport PDF files
- 📊 **Multi-Sheet Excel Output**: Creates organized spreadsheets with different views
- 🔄 **FIFO Matching**: Automatically matches buy/sell orders using First-In-First-Out
- 📈 **Position Tracking**: Tracks open positions and portfolio value
- 🔍 **Duplicate Prevention**: Prevents reprocessing of already handled files
- 🗂️ **Organized Structure**: Processes trades by month/year folders

## Requirements

Install the required Python packages:

```bash
pip install requirements.txt
```

## Folder Structure

Your trades folder should be organized like this:

```
/Desktop/trades/
├── 01.2025/
│   ├── DailyTradeReport.20250102.pdf
│   ├── DailyTradeReport.20250103.pdf
│   └── processed_files.json (auto-generated)
├── 02.2025/
│   ├── DailyTradeReport.20250201.pdf
│   └── processed_files.json (auto-generated)
├── master-trades.xlsx (auto-generated)
└── master-copy-backup.xlsx (auto-generated)
```

## How to Use

### 1. Setup
- Place your PDF trade reports in month folders (format: `MM.YYYY`)
- PDF files should be named: `DailyTradeReport.YYYYMMDD.pdf`
- Run the script from your terminal

### 2. Processing Trades

```bash
python trade-log-formatter.py
```

You'll see this menu:
```
'RESET' or enter a date (e.g. 01.2025):
```

**Options:**
- Enter a date like `05.2025` to process that specific month
- Enter `RESET` to clear all data and start fresh

### 3. Understanding the Output

The script creates a master Excel file with 3 sheets:

#### **Trades Sheet** (Position Tracking)
- Tracks individual positions (LONG only)
- Shows entry/exit prices and dates
- Used for P&L calculation

| Symbol | Qty | Side | Entry Price | Entry Time | Entry Date | Exit Qty | Exit Price | Exit Time | Exit Date |
|--------|-----|------|-------------|------------|------------|----------|------------|-----------|-----------|
| AAPL   | 100 | LONG | 150.50      | 09:30:00   | 2025-05-02 | -100     | 155.25     | 15:45:00  | 2025-05-03 |

#### **Raw Trades Sheet** (All Individual Trades)
- Every single trade from PDFs
- Both BUY and SELL orders
- Unfiltered transaction history

| Symbol | Date       | Time     | Side  | Quantity | Price  |
|--------|------------|----------|-------|----------|--------|
| AAPL   | 2025-05-02 | 09:30:00 | LONG  | 100      | 150.50 |
| AAPL   | 2025-05-02 | 10:15:00 | LONG  | 50       | 151.00 |

#### **Consolidated Trades Sheet** (Daily Summary)
- Trades grouped by symbol, date, and side
- Shows average prices and total quantities
- Useful for daily trading analysis

| Symbol | Date       | Time     | Side  | Quantity | Avg_Price | Total_Value |
|--------|------------|----------|-------|----------|-----------|-------------|
| AAPL   | 2025-05-02 | 09:30:00 | LONG  | 150      | 150.67    | 22,600.00   |

### 4. Key Features Explained

#### **FIFO Matching**
- Automatically matches SELL orders to oldest BUY positions
- Handles partial fills and position tracking
- Shows profit/loss for closed positions

#### **Options Support**
- Recognizes options symbols (e.g., "AAPL 16JAN26 150 C")
- Automatically adjusts option prices (multiplies by 100)
- Treats options same as stocks for tracking

#### **Duplicate Prevention**
- Tracks processed files in `processed_files.json`
- Only processes new PDF files
- Safe to run multiple times

#### **Position Summary**
After processing, you'll see:
```
📊 Open Positions Summary:
Symbol  Shares    Avg Price    Total Value    Since
-------------------------------------------------------
AAPL       100 @ $  150.50 = $  15,050.00  2025-05-02
TSLA       200 @ $  220.75 = $  44,150.00  2025-05-01
-------------------------------------------------------
Total Portfolio Value: $59,200.00
```

## Configuration Options

Edit these variables at the top of the script:

```python
DEBUG = True           # Enable detailed logging
TEST_MODE = True       # Use test files (master-copy-test.xlsx)
```

## Troubleshooting

### Common Issues

1. **"No folder found for month-year"**
   - Check folder naming: must be `MM.YYYY` format
   - Ensure folder exists in `/Desktop/trades/`

2. **"No new trades found"**
   - PDFs already processed (check `processed_files.json`)
   - PDF format not recognized

3. **"Error parsing trade"**
   - PDF structure changed
   - Missing required fields in PDF

### Debug Mode

Enable debug mode for detailed logging:
```python
DEBUG = True
```

This shows:
- Individual trade parsing
- FIFO matching logic
- Detailed summaries

## Reset Function

Use `RESET` to clear all data:
- Backs up current data with timestamp
- Clears all 3 spreadsheet tabs
- Resets all `processed_files.json` files
- Allows complete reprocessing

**⚠️ Warning**: This deletes all trade data. A backup is created automatically.

## File Locations

- **Input**: `/Desktop/trades/MM.YYYY/DailyTradeReport.*.pdf`
- **Output**: `/Desktop/trades/master-trades.xlsx`
- **Backup**: `/Desktop/trades/master-copy-backup.xlsx`
- **Tracking**: `/Desktop/trades/MM.YYYY/processed_files.json`

## Tips

1. **Monthly Processing**: Process one month at a time for better organization
2. **Backup Important**: Keep backups of your master file
3. **PDF Naming**: Ensure consistent PDF naming for automatic detection
4. **Regular Processing**: Process trades regularly to avoid large backlogs

## Support

If you encounter issues:
1. Enable `DEBUG = True` for detailed logs
2. Check PDF format matches expected structure
3. Verify folder and file naming conventions
4. Use `RESET` to start fresh if needed