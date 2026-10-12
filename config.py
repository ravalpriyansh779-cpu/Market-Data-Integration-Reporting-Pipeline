import os

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/marketdata")
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/marketdata_test")
API_BASE_URL = os.getenv("MARKET_API_URL", "http://127.0.0.1:8765")
API_KEY = os.getenv("MARKET_API_KEY", "")
API_LOOKBACK_DAYS = int(os.getenv("API_LOOKBACK_DAYS", "20"))
PRICES_CSV = os.getenv("PRICES_CSV", "data/sample_prices.csv")
POSITIONS_CSV = os.getenv("POSITIONS_CSV", "data/sample_positions.csv")
OUTPUT_DIR = os.getenv("OUTPUT_DIR", "output")
