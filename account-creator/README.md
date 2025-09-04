# Account Creator
Tooling to create Apple or Google accounts using Selenium browser automation.

> **Note**: The Google account creation flow is specifically tailored for the German UI. Adaptation will be needed for other languages. Manual account creation was sometimes required due to frequent account bans and additional CAPTCHAs encountered when creating accounts rapidly.

## Key Files
- `accounts.csv` - Account configuration file for `create_db_entries.py`
- `apple.py` - Apple account creation logic
- `create_db_entries.py` - Bulk account creation from CSV data
- `google_acc.py` - Google account creation logic (German UI)
- `main.py` - Primary execution script (`main.py -h` for usage)
- `sim_factor.py` - SIM-based 2FA code retrieval helper

## Setup
1. Create and activate Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage
1. Generate database entries:
   ```bash
   python create_db_entries.py
   ```
2. Execute account creation:
   ```bash
   python main.py
   ```
For detailed execution parameters, see:
```bash
python main.py -h
```
