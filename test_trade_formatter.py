import unittest
from trade_log_formatter.py import consolidate_trades, match_trades_fifo
import pandas as pd

class TestTradeFormatter(unittest.TestCase):
    def setUp(self):
        # Sample test trades
        self.test_trades = [
            {
                "Symbol": "IONQ",
                "Date": "2025-05-02",
                "Time": "09:46:11",
                "Quantity": 60,
                "Price": 28.5,
                "Side": "BUY"
            },
            {
                "Symbol": "IONQ",
                "Date": "2025-05-02",
                "Time": "15:59:16",
                "Quantity": 125,
                "Price": 30.905,
                "Side": "SELL"
            },
            {
                "Symbol": "CRWD",
                "Date": "2025-05-05",
                "Time": "10:48:57",
                "Quantity": 5,
                "Price": 449.8,
                "Side": "BUY"
            },
            {
                "Symbol": "IONQ",
                "Date": "2025-05-05",
                "Time": "10:06:17",
                "Quantity": 100,
                "Price": 30.4,
                "Side": "BUY"
            }
        ]

    def test_consolidate_trades(self):
        consolidated = consolidate_trades(self.test_trades)
        
        # Test IONQ BUY consolidation
        ionq_buys = [t for t in consolidated if t['Symbol'] == 'IONQ' and t['Side'] == 'LONG']
        self.assertEqual(len(ionq_buys), 2)
        self.assertEqual(ionq_buys[0]['Quantity'], 60)
        self.assertEqual(ionq_buys[0]['Price'], 28.5)
        
        # Test CRWD BUY
        crwd_buys = [t for t in consolidated if t['Symbol'] == 'CRWD']
        self.assertEqual(len(crwd_buys), 1)
        self.assertEqual(crwd_buys[0]['Quantity'], 5)
        self.assertEqual(crwd_buys[0]['Price'], 449.8)

    def test_match_trades_fifo(self):
        # Create empty master DataFrame
        df_master = pd.DataFrame(columns=[
            "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
            "Entry Date", "Notes", "Exit Qty", "Exit Price", 
            "Exit Time", "Exit Date"
        ])
        
        # Test matching
        result = match_trades_fifo(df_master, self.test_trades)
        
        # Verify IONQ positions
        ionq_trades = result[result['Symbol'] == 'IONQ']
        self.assertEqual(len(ionq_trades), 2)  # Should have 2 IONQ trades
        
        # First IONQ trade should be fully closed
        first_ionq = ionq_trades.iloc[0]
        self.assertEqual(first_ionq['Qty'], 60)
        self.assertEqual(first_ionq['Exit Qty'], -60)
        self.assertEqual(first_ionq['Exit Price'], 30.905)
        
        # Second IONQ trade should be partially closed
        second_ionq = ionq_trades.iloc[1]
        self.assertEqual(second_ionq['Qty'], -65)
        self.assertEqual(second_ionq['Exit Qty'], 65)
        self.assertEqual(second_ionq['Exit Price'], 30.4)

    def test_balance_calculation(self):
        df_master = pd.DataFrame(columns=[
            "Symbol", "Qty", "Side", "Entry Price", "Entry Time", 
            "Entry Date", "Notes", "Exit Qty", "Exit Price", 
            "Exit Time", "Exit Date"
        ])
        
        result = match_trades_fifo(df_master, self.test_trades)
        
        # Get final balances for each symbol
        balances = {}
        for _, row in result.iterrows():
            symbol = row['Symbol']
            qty = row['Qty']
            exit_qty = row['Exit Qty'] if pd.notna(row['Exit Qty']) else 0
            
            if symbol not in balances:
                balances[symbol] = 0
            balances[symbol] += qty + (exit_qty if exit_qty else 0)
        
        # Test final balances
        self.assertEqual(balances['IONQ'], 35)  # Should have 35 shares remaining
        self.assertEqual(balances['CRWD'], 5)   # Should have 5 shares remaining

if __name__ == '__main__':
    unittest.main(verbosity=2)