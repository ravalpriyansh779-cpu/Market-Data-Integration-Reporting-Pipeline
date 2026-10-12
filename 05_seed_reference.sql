INSERT INTO ref.commodity (symbol, name, unit, currency) VALUES
    ('WTI',    'Crude Oil WTI',     'bbl',   'USD'),
    ('BRENT',  'Crude Oil Brent',   'bbl',   'USD'),
    ('NG',     'Natural Gas',       'MMBtu', 'USD'),
    ('GOLD',   'Gold',              'oz',    'USD'),
    ('SILVER', 'Silver',            'oz',    'USD'),
    ('COPPER', 'Copper',            'lb',    'USD'),
    ('CORN',   'Corn',              'bu',    'USD'),
    ('WHEAT',  'Wheat',             'bu',    'USD'),
    ('SOY',    'Soybeans',          'bu',    'USD'),
    ('SUGAR',  'Sugar #11',         'lb',    'USD')
ON CONFLICT (symbol) DO NOTHING;

INSERT INTO etl.error_code (error_code, description, suggested_resolution) VALUES
    ('MISSING_SYMBOL',      'Symbol is blank or missing',                          'Ask the provider to resend the record with a symbol'),
    ('UNKNOWN_SYMBOL',      'Symbol not found in ref.commodity',                   'Add the commodity to ref.commodity or fix the provider mapping, then re-ingest'),
    ('BAD_DATE',            'Price date is not a valid YYYY-MM-DD date',           'Fix date format at the provider and re-ingest'),
    ('FUTURE_DATE',         'Price date is in the future',                         'Check provider clock / timezone handling'),
    ('BAD_PRICE',           'Price is missing or not numeric',                     'Ask the provider for a corrected value'),
    ('NON_POSITIVE_PRICE',  'Price is zero or negative',                           'Confirm with provider; commodity spot/futures prices here must be > 0'),
    ('PRICE_OUT_OF_RANGE',  'Price exceeds the sanity ceiling',                    'Likely unit or scaling error at the provider'),
    ('CURRENCY_MISMATCH',   'Currency differs from ref.commodity currency',        'Confirm quote currency; add FX conversion if intended'),
    ('DUPLICATE_IN_BATCH',  'Superseded by a later record for the same key',       'No action needed unless the earlier value was the correct one'),
    ('MISSING_POSITION_ID', 'Position id is blank or missing',                     'Fix the position extract'),
    ('MISSING_BOOK',        'Book is blank or missing',                            'Fix the position extract'),
    ('BAD_QUANTITY',        'Quantity is missing or not numeric',                  'Fix the position extract'),
    ('BAD_AVG_COST',        'Average cost is missing, non-numeric or not positive', 'Fix the position extract')
ON CONFLICT (error_code) DO NOTHING;
