import os
import re
import io
import urllib.request
import pandas as pd
from datetime import datetime

# Configuration
CSV_FILE = 'sp_500_historical_components.csv'
BACKUP_FILE = 'sp_500_historical_components_backup.csv'
WIKI_URL = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
TICKER_REGEX = r'^[A-Za-z]{1,5}([\.\-][A-Za-z]{1,3})?$'

def fetch_wikipedia_changes_table(url):
    """
    Fetches the S&P 500 changes table from Wikipedia using a standard User-Agent.
    """
    print(f"Fetching S&P 500 changes from Wikipedia ({url})...")
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    html_content = urllib.request.urlopen(req).read()
    tables = pd.read_html(io.BytesIO(html_content))
    
    # Identify the changes table by looking for 'added' or 'removed' in column names
    changes_df = None
    for tbl in tables:
        cols_str = " ".join([str(c).lower() for c in tbl.columns])
        if 'added' in cols_str or 'removed' in cols_str:
            changes_df = tbl
            break
            
    if changes_df is None:
        raise ValueError("Could not locate the S&P 500 changes table on Wikipedia.")
        
    return changes_df

def parse_changes_table(df_raw):
    """
    Cleans MultiIndex or flat column headers and extracts parsed date, added, and removed tickers.
    """
    df = df_raw.copy()
    
    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        new_cols = []
        for col in df.columns:
            parts = [str(p).strip() for p in col if str(p).strip() and 'unnamed' not in str(p).lower()]
            if len(parts) > 1 and parts[0] == parts[1]:
                new_cols.append(parts[0])
            else:
                new_cols.append(" ".join(parts))
        df.columns = new_cols

    # Detect Date, Added, and Removed ticker columns dynamically
    date_col = next((c for c in df.columns if 'date' in c.lower()), None)
    added_col = next((c for c in df.columns if 'added' in c.lower() and 'ticker' in c.lower()), None)
    if not added_col:
        added_col = next((c for c in df.columns if 'added' in c.lower()), None)
        
    removed_col = next((c for c in df.columns if 'removed' in c.lower() and 'ticker' in c.lower()), None)
    if not removed_col:
        removed_col = next((c for c in df.columns if 'removed' in c.lower()), None)

    if not date_col:
        raise KeyError("Could not identify the Date column in the Wikipedia table.")

    records = []
    for _, row in df.iterrows():
        raw_date = row[date_col]
        if pd.isna(raw_date):
            continue
            
        try:
            parsed_date = pd.to_datetime(raw_date)
        except Exception:
            continue
            
        added_raw = str(row[added_col]) if added_col and pd.notna(row[added_col]) else ""
        removed_raw = str(row[removed_col]) if removed_col and pd.notna(row[removed_col]) else ""
        
        # Strip footnote brackets like [1] or [note 1] and extra whitespace
        added_ticker = re.sub(r'\[.*?\]', '', added_raw).strip()
        removed_ticker = re.sub(r'\[.*?\]', '', removed_raw).strip()
        
        # Validate that extracted values match ticker symbol format (and aren't dates)
        added_clean = added_ticker if re.match(TICKER_REGEX, added_ticker) else None
        removed_clean = removed_ticker if re.match(TICKER_REGEX, removed_ticker) else None
        
        records.append({
            'date': parsed_date,
            'added': added_clean,
            'removed': removed_clean
        })

    return pd.DataFrame(records)

def update_historical_components():
    if not os.path.exists(CSV_FILE):
        raise FileNotFoundError(f"Could not find {CSV_FILE} in current directory.")

    # 1. Load existing historical CSV
    df_hist = pd.read_csv(CSV_FILE)
    df_hist['date'] = pd.to_datetime(df_hist['date'])
    df_hist = df_hist.sort_values('date').reset_index(drop=True)

    last_csv_date = df_hist['date'].max()
    
    # Filter out any date strings that already snuck into the CSV tickers column
    raw_latest = df_hist.iloc[-1]['tickers'].split(',')
    latest_tickers = {t.strip() for t in raw_latest if re.match(TICKER_REGEX, t.strip())}
    
    print(f"Latest record in CSV: {last_csv_date.strftime('%Y-%m-%d')} ({len(latest_tickers)} tickers)")

    # 2. Fetch and parse Wikipedia changes
    changes_raw = fetch_wikipedia_changes_table(WIKI_URL)
    changes_df = parse_changes_table(changes_raw)

    # 3. Filter changes that occurred after the last CSV date
    new_changes = changes_df[changes_df['date'] > last_csv_date].sort_values('date')

    if new_changes.empty:
        print("No new changes found beyond the latest CSV date.")
        return

    print(f"Found {len(new_changes)} change record(s) on Wikipedia after {last_csv_date.strftime('%Y-%m-%d')}.")

    # 4. Group changes by date
    grouped_changes = {}
    for _, row in new_changes.iterrows():
        d_str = row['date'].strftime('%Y-%m-%d')
        if d_str not in grouped_changes:
            grouped_changes[d_str] = {'added': set(), 'removed': set()}
        if row['added']:
            grouped_changes[d_str]['added'].add(row['added'])
        if row['removed']:
            grouped_changes[d_str]['removed'].add(row['removed'])

    # 5. Build records ONLY on dates when changes occur
    current_tickers = set(latest_tickers)
    new_rows = []

    # Iterate through the change dates in chronological order
    for d_str in sorted(grouped_changes.keys()):
        adds = grouped_changes[d_str]['added']
        removes = grouped_changes[d_str]['removed']
        
        # Update ticker set
        current_tickers.update(adds)
        current_tickers.difference_update(removes)
        print(f"Applied changes on {d_str}: +{list(adds)} -{list(removes)}")

        # Format sorted comma-separated string matching existing CSV format
        sorted_tickers_str = ",".join(sorted(list(current_tickers)))
        new_rows.append({'date': d_str, 'tickers': sorted_tickers_str})

    df_new = pd.DataFrame(new_rows)
    df_new['date'] = pd.to_datetime(df_new['date'])

    # 6. Combine and save
    df_updated = pd.concat([df_hist, df_new], ignore_index=True)
    df_updated['date'] = df_updated['date'].dt.strftime('%Y-%m-%d')

    # Backup original CSV
    df_hist['date'] = df_hist['date'].dt.strftime('%Y-%m-%d')
    df_hist.to_csv(BACKUP_FILE, index=False)
    print(f"Backup created: {BACKUP_FILE}")

    # Overwrite main CSV
    df_updated.to_csv(CSV_FILE, index=False)
    print(f"Successfully updated {CSV_FILE}! Total rows: {len(df_updated)}.")

if __name__ == '__main__':
    update_historical_components()