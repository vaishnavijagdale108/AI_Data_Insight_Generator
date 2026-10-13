import pandas as pd

def load_data(file_path):
    """Load CSV data into a Pandas DataFrame."""
    return pd.read_csv(file_path)
