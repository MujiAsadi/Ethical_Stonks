import os
import re
import pandas as pd
import ollama
from tqdm import tqdm

# Configuration
INPUT_CSV = 'sp_500_historical_components.csv'
OUTPUT_CSV = 'sp_500_ethical_graded.csv'
MODEL_NAME = 'llama3.1'  # Options: 'llama3.1', 'qwen2.5', 'mistral'
SAVE_EVERY_N_ROWS = 10   # Checkpoint frequency

def evaluate_ticker_ethics(ticker: str) -> str:
    """
    Queries local Ollama model to evaluate a stock ticker on ESG and ethical metrics.
    """
    prompt = f"""
    Act as a corporate ethics and ESG analyst. Evaluate the company represented by ticker symbol: '{ticker}'.

    Provide:
    1. An involvement/support grade: [0,1,2]. This is based solely on the involvement the company has with Israel. 0 is none to little, 1 is moderate, 2 is major.
    2. A brief 1-sentence justification focusing on corporate governance involvement, social involvement, or stances taken publicly.

    Output format MUST be strictly:
    Grade: [GRADE] | Reason: [1-sentence rationale]
    """
    
    try:
        response = ollama.chat(
            model=MODEL_NAME,
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.2}  # Low temperature for consistent, objective answers
        )
        return response['message']['content'].replace('\n', ' ').strip()
    except Exception as e:
        return f"Error: {e}"

def extract_unique_tickers(df: pd.DataFrame) -> set:
    """
    Extracts all individual ticker symbols from the comma-separated 'tickers' column.
    """
    ticker_pattern = r'^[A-Za-z]{1,5}([\.\-][A-Za-z]{1,3})?$'
    all_tickers = set()
    
    for row in df['tickers'].dropna():
        symbols = [t.strip() for t in row.split(',')]
        valid_symbols = [t for t in symbols if re.match(ticker_pattern, t)]
        all_tickers.update(valid_symbols)
        
    return all_tickers

def main():
    if not os.path.exists(INPUT_CSV):
        raise FileNotFoundError(f"Could not find {INPUT_CSV}")

    df = pd.read_csv(INPUT_CSV)

    # Step 1: Collect unique tickers across all historical dates
    print("Extracting unique tickers...")
    unique_tickers = sorted(list(extract_unique_tickers(df)))
    print(f"Found {len(unique_tickers)} unique stock tickers to evaluate.")

    # Step 2: Load existing progress if script was paused/restarted
    graded_map = {}
    if os.path.exists('ticker_grades_cache.csv'):
        cache_df = pd.read_csv('ticker_grades_cache.csv')
        graded_map = dict(zip(cache_df['ticker'], cache_df['ethical_grade']))
        print(f"Loaded {len(graded_map)} previously evaluated tickers from cache.")

    # Step 3: Grade tickers via Ollama
    print(f"Starting ethical evaluations using local model '{MODEL_NAME}'...")
    processed_count = 0

    for ticker in tqdm(unique_tickers, desc="Grading Stocks"):
        if ticker in graded_map and not str(graded_map[ticker]).startswith("Error"):
            continue  # Skip already processed tickers

        grade_result = evaluate_ticker_ethics(ticker)
        graded_map[ticker] = grade_result
        processed_count += 1

        # Periodic checkpointing
        if processed_count % SAVE_EVERY_N_ROWS == 0:
            cache_df = pd.DataFrame(list(graded_map.items()), columns=['ticker', 'ethical_grade'])
            cache_df.to_csv('ticker_grades_cache.csv', index=False)

    # Save final cache
    cache_df = pd.DataFrame(list(graded_map.items()), columns=['ticker', 'ethical_grade'])
    cache_df.to_csv('ticker_grades_cache.csv', index=False)

    # Step 4: Map evaluated grades back to the full dataset (summary string per date)
    def map_grades_to_row(ticker_str):
        if pd.isna(ticker_str):
            return ""
        tickers = [t.strip() for t in ticker_str.split(',')]
        # Extract just the letter grade (A-F) for compact display per row
        row_grades = []
        for t in tickers:
            full_evaluation = graded_map.get(t, "")
            grade_match = re.search(r'Grade:\s*([A-F])', full_evaluation)
            letter = grade_match.group(1) if grade_match else "?"
            row_grades.append(f"{t}:{letter}")
        return ", ".join(row_grades)

    print("Mapping ethical grades into output CSV...")
    df['ethical_grades_summary'] = df['tickers'].apply(map_grades_to_row)

    # Save final updated dataframe
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"Complete! Saved ethical stock evaluations to '{OUTPUT_CSV}'.")

if __name__ == '__main__':
    main()