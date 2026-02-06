-- PostgreSQL schema for CardDemo data migrated from mainframe files.
-- Tables are derived from COBOL copybooks in app/cpy and Db2 DDL in
-- app/app-transaction-type-db2/ddl and app/app-authorization-ims-db2-mq/ddl.

CREATE SCHEMA IF NOT EXISTS carddemo;
SET search_path TO carddemo;

-- Drop in dependency order so the script is re-runnable.
DROP TABLE IF EXISTS card_transaction CASCADE;
DROP TABLE IF EXISTS transaction_category_balance CASCADE;
DROP TABLE IF EXISTS disclosure_group CASCADE;
DROP TABLE IF EXISTS transaction_type_category CASCADE;
DROP TABLE IF EXISTS transaction_type CASCADE;
DROP TABLE IF EXISTS card_xref CASCADE;
DROP TABLE IF EXISTS card CASCADE;
DROP TABLE IF EXISTS account CASCADE;
DROP TABLE IF EXISTS customer CASCADE;
DROP TABLE IF EXISTS user_security CASCADE;

-- Customers (CVCUS01Y.cpy)
CREATE TABLE customer (
    cust_id             bigint PRIMARY KEY,
    first_name          varchar(25),
    middle_name         varchar(25),
    last_name           varchar(25),
    addr_line1          varchar(50),
    addr_line2          varchar(50),
    addr_line3          varchar(50),
    addr_state_cd       char(2),
    addr_country_cd     char(3),
    addr_zip            char(10),
    phone_num1          char(15),
    phone_num2          char(15),
    ssn                 bigint,
    govt_issued_id      char(20),
    dob                 date,
    eft_account_id      char(10),
    pri_card_holder_ind char(1),
    fico_credit_score   smallint
);

-- Accounts (CVACT01Y.cpy)
CREATE TABLE account (
    acct_id              bigint PRIMARY KEY,
    active_status        char(1),
    curr_balance         numeric(12,2),
    credit_limit         numeric(12,2),
    cash_credit_limit    numeric(12,2),
    open_date            date,
    expiration_date      date,
    reissue_date         date,
    curr_cycle_credit    numeric(12,2),
    curr_cycle_debit     numeric(12,2),
    addr_zip             char(10),
    group_id             char(10)
);

-- Cards (CVACT02Y.cpy)
CREATE TABLE card (
    card_num        char(16) PRIMARY KEY,
    acct_id         bigint NOT NULL REFERENCES account(acct_id),
    cvv             smallint,
    embossed_name   varchar(50),
    expiration_date date,
    active_status   char(1)
);

-- Card/customer/account cross reference (CVACT03Y.cpy)
CREATE TABLE card_xref (
    card_num   char(16) PRIMARY KEY REFERENCES card(card_num),
    cust_id    bigint NOT NULL REFERENCES customer(cust_id),
    acct_id    bigint NOT NULL REFERENCES account(acct_id)
);

-- User security (CSUSR01Y.cpy)
CREATE TABLE user_security (
    user_id     char(8) PRIMARY KEY,
    first_name  varchar(20),
    last_name   varchar(20),
    password    char(8),
    user_type   char(1)
);

-- Transaction reference data (CVTRA03Y.cpy, CVTRA04Y.cpy, TRNTYPE.ddl, TRNTYCAT.ddl)
CREATE TABLE transaction_type (
    tr_type        char(2) PRIMARY KEY,
    tr_description varchar(50) NOT NULL
);

CREATE TABLE transaction_type_category (
    trc_type_code     char(2) NOT NULL,
    trc_type_category char(4) NOT NULL,
    trc_cat_data      varchar(50) NOT NULL,
    PRIMARY KEY (trc_type_code, trc_type_category),
    FOREIGN KEY (trc_type_code) REFERENCES transaction_type(tr_type)
);

-- Disclosure groups (CVTRA02Y.cpy)
CREATE TABLE disclosure_group (
    acct_group_id   char(10) NOT NULL,
    tran_type_cd    char(2) NOT NULL,
    tran_cat_cd     char(4) NOT NULL,
    int_rate        numeric(6,2),
    PRIMARY KEY (acct_group_id, tran_type_cd, tran_cat_cd),
    FOREIGN KEY (tran_type_cd, tran_cat_cd)
        REFERENCES transaction_type_category(trc_type_code, trc_type_category)
);

-- Transaction category balances by account (CVTRA01Y.cpy)
CREATE TABLE transaction_category_balance (
    acct_id      bigint NOT NULL REFERENCES account(acct_id),
    tran_type_cd char(2) NOT NULL,
    tran_cat_cd  char(4) NOT NULL,
    balance      numeric(11,2),
    PRIMARY KEY (acct_id, tran_type_cd, tran_cat_cd),
    FOREIGN KEY (tran_type_cd, tran_cat_cd)
        REFERENCES transaction_type_category(trc_type_code, trc_type_category)
);

-- Card transactions (daily transaction feed; CVTRA06Y.cpy)
CREATE TABLE card_transaction (
    tran_id        char(16) PRIMARY KEY,
    tran_type_cd   char(2) NOT NULL,
    tran_cat_cd    char(4) NOT NULL,
    source         char(10),
    description    varchar(100),
    amount         numeric(11,2),
    merchant_id    bigint,
    merchant_name  varchar(50),
    merchant_city  varchar(50),
    merchant_zip   char(10),
    card_num       char(16) NOT NULL,
    orig_ts        timestamp,
    proc_ts        timestamp,
    FOREIGN KEY (tran_type_cd, tran_cat_cd)
        REFERENCES transaction_type_category(trc_type_code, trc_type_category),
    FOREIGN KEY (card_num)
        REFERENCES card(card_num)
);
