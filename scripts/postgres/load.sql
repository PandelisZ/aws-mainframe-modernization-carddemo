-- psql helper script to load CardDemo data into PostgreSQL
-- after running scripts/postgres/export_to_csv.py.
--
-- Usage (from the repository root):
--   psql -d your_database -f scripts/postgres/schema.sql
--   psql -d your_database -f scripts/postgres/load.sql
--
-- This assumes the CSV files were written to ./postgres_export
-- relative to the directory where psql is executed.

SET search_path TO carddemo;

\copy customer                      FROM 'postgres_export/customer.csv'                     WITH (FORMAT csv, HEADER true);
\copy account                       FROM 'postgres_export/account.csv'                      WITH (FORMAT csv, HEADER true);
\copy card                          FROM 'postgres_export/card.csv'                         WITH (FORMAT csv, HEADER true);
\copy card_xref                     FROM 'postgres_export/card_xref.csv'                    WITH (FORMAT csv, HEADER true);
\copy user_security                 FROM 'postgres_export/user_security.csv'                WITH (FORMAT csv, HEADER true);
\copy transaction_type              FROM 'postgres_export/transaction_type.csv'             WITH (FORMAT csv, HEADER true);
\copy transaction_type_category     FROM 'postgres_export/transaction_type_category.csv'    WITH (FORMAT csv, HEADER true);
\copy disclosure_group              FROM 'postgres_export/disclosure_group.csv'             WITH (FORMAT csv, HEADER true);
\copy transaction_category_balance  FROM 'postgres_export/transaction_category_balance.csv' WITH (FORMAT csv, HEADER true);
\copy card_transaction              FROM 'postgres_export/card_transaction.csv'             WITH (FORMAT csv, HEADER true);
