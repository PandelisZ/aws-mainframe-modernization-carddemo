#!/usr/bin/env python3
"""Export CardDemo mainframe sample data to CSV for PostgreSQL loading.

The CSV files produced here are intended to be loaded with psql using
scripts/postgres/schema.sql and scripts/postgres/load.sql.

This script reads the fixed-width ASCII and EBCDIC sample files under
app/data and converts COBOL numeric formats (including signed zoned
decimal) into PostgreSQL-friendly numeric strings.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Callable, Iterable, List


ROOT = Path(__file__).resolve().parents[2]
DATA_ASCII = ROOT / "app" / "data" / "ASCII"
DATA_EBCDIC = ROOT / "app" / "data" / "EBCDIC"


# Zoned-decimal overpunch mapping used by COBOL
POSITIVE_ZONED = {
    "{": "0",
    "A": "1",
    "B": "2",
    "C": "3",
    "D": "4",
    "E": "5",
    "F": "6",
    "G": "7",
    "H": "8",
    "I": "9",
}

NEGATIVE_ZONED = {
    "}": "0",
    "J": "1",
    "K": "2",
    "L": "3",
    "M": "4",
    "N": "5",
    "O": "6",
    "P": "7",
    "Q": "8",
    "R": "9",
}


def decode_zoned_decimal(field: str, scale: int) -> Decimal:
    """Decode a COBOL signed zoned-decimal field into a Decimal.

    The field is expected to be an unsigned digit string except for the
    last character, which may carry the sign and final digit in EBCDIC
    overpunch form.
    """

    field = field.rstrip()
    if not field:
        return Decimal("0")

    last = field[-1]
    sign = 1

    if last in POSITIVE_ZONED:
        digit = POSITIVE_ZONED[last]
    elif last in NEGATIVE_ZONED:
        sign = -1
        digit = NEGATIVE_ZONED[last]
    elif last.isdigit():
        digit = last
    else:
        raise ValueError(f"Unexpected zoned-decimal last char {last!r} in {field!r}")

    num_str = field[:-1] + digit
    if not num_str:
        return Decimal("0")

    value = Decimal(num_str) / (Decimal(10) ** scale)
    return value * sign


def split_fixed(line: str, widths: List[int]) -> List[str]:
    parts: List[str] = []
    idx = 0
    for w in widths:
        parts.append(line[idx : idx + w])
        idx += w
    if idx != len(line):
        raise ValueError(f"Expected line length {idx}, got {len(line)}: {line!r}")
    return parts


@dataclass
class ExportSpec:
    name: str
    input_path: Path
    record_length: int
    widths: List[int]
    headers: List[str]
    row_builder: Callable[[List[str]], List[str]]
    encoding: str = "ascii"  # for ASCII fixed-width files


def write_csv(spec: ExportSpec, out_dir: Path) -> int:
    out_path = out_dir / f"{spec.name}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    if spec.encoding.lower() == "ebcdic-cp037":
        # Special handling for fixed-length EBCDIC records (no newlines).
        data = spec.input_path.read_bytes()
        if len(data) % spec.record_length != 0:
            raise ValueError(
                f"{spec.input_path} length {len(data)} is not a multiple of {spec.record_length}"
            )
        with out_path.open("w", newline="", encoding="utf-8") as out_f:
            writer = csv.writer(out_f)
            writer.writerow(spec.headers)
            for i in range(0, len(data), spec.record_length):
                chunk = data[i : i + spec.record_length]
                line = chunk.decode("cp037")
                fields = split_fixed(line, spec.widths)
                row = spec.row_builder(fields)
                writer.writerow(row)
                count += 1
    else:
        with spec.input_path.open("r", encoding=spec.encoding) as in_f, out_path.open(
            "w", newline="", encoding="utf-8"
        ) as out_f:
            writer = csv.writer(out_f)
            writer.writerow(spec.headers)
            for raw in in_f:
                line = raw.rstrip("\n")
                if not line:
                    continue
                if len(line) != spec.record_length:
                    raise ValueError(
                        f"{spec.input_path}: expected len {spec.record_length}, got {len(line)}"
                    )
                fields = split_fixed(line, spec.widths)
                row = spec.row_builder(fields)
                writer.writerow(row)
                count += 1

    print(f"Wrote {count} rows to {out_path}")
    return count


def build_specs() -> Iterable[ExportSpec]:
    # CUSTOMER (CVCUS01Y.cpy, RECLN 500)
    cust_widths = [
        9,  # CUST-ID
        25,  # FIRST
        25,  # MIDDLE
        25,  # LAST
        50,  # ADDR1
        50,  # ADDR2
        50,  # ADDR3
        2,  # STATE
        3,  # COUNTRY
        10,  # ZIP
        15,  # PHONE1
        15,  # PHONE2
        9,  # SSN
        20,  # GOVT ID
        10,  # DOB
        10,  # EFT ACCOUNT ID
        1,  # PRIMARY CARD HOLDER IND
        3,  # FICO SCORE
        168,  # FILLER
    ]

    def build_customer(fields: List[str]) -> List[str]:
        (
            cust_id,
            first,
            middle,
            last,
            addr1,
            addr2,
            addr3,
            state,
            country,
            zip_code,
            phone1,
            phone2,
            ssn,
            govt_id,
            dob,
            eft_acct,
            pri_ind,
            fico,
            _filler,
        ) = fields
        return [
            str(int(cust_id)),
            first.rstrip(),
            middle.rstrip(),
            last.rstrip(),
            addr1.rstrip(),
            addr2.rstrip(),
            addr3.rstrip(),
            state.rstrip(),
            country.rstrip(),
            zip_code.rstrip(),
            phone1.rstrip(),
            phone2.rstrip(),
            str(int(ssn)),
            govt_id.rstrip(),
            dob.rstrip(),
            eft_acct.rstrip(),
            pri_ind.rstrip(),
            str(int(fico)),
        ]

    yield ExportSpec(
        name="customer",
        input_path=DATA_ASCII / "custdata.txt",
        record_length=500,
        widths=cust_widths,
        headers=[
            "cust_id",
            "first_name",
            "middle_name",
            "last_name",
            "addr_line1",
            "addr_line2",
            "addr_line3",
            "addr_state_cd",
            "addr_country_cd",
            "addr_zip",
            "phone_num1",
            "phone_num2",
            "ssn",
            "govt_issued_id",
            "dob",
            "eft_account_id",
            "pri_card_holder_ind",
            "fico_credit_score",
        ],
        row_builder=build_customer,
    )

    # ACCOUNT (CVACT01Y.cpy, RECLN 300)
    acct_widths = [
        11,  # ACCT-ID
        1,  # STATUS
        12,  # CURR BAL (S9(10)V99)
        12,  # CREDIT LIMIT (S9(10)V99)
        12,  # CASH CREDIT LIMIT (S9(10)V99)
        10,  # OPEN DATE
        10,  # EXPIRATION DATE
        10,  # REISSUE DATE
        12,  # CURR CYCLE CREDIT (S9(10)V99)
        12,  # CURR CYCLE DEBIT  (S9(10)V99)
        10,  # ZIP
        10,  # GROUP ID
        178,  # FILLER
    ]

    def build_account(fields: List[str]) -> List[str]:
        (
            acct_id,
            status,
            curr_bal,
            credit_lim,
            cash_credit_lim,
            open_date,
            exp_date,
            reissue_date,
            cyc_credit,
            cyc_debit,
            zip_code,
            group_id,
            _filler,
        ) = fields
        return [
            str(int(acct_id)),
            status.rstrip(),
            str(decode_zoned_decimal(curr_bal, 2)),
            str(decode_zoned_decimal(credit_lim, 2)),
            str(decode_zoned_decimal(cash_credit_lim, 2)),
            open_date.rstrip(),
            exp_date.rstrip(),
            reissue_date.rstrip(),
            str(decode_zoned_decimal(cyc_credit, 2)),
            str(decode_zoned_decimal(cyc_debit, 2)),
            zip_code.rstrip(),
            group_id.rstrip(),
        ]

    yield ExportSpec(
        name="account",
        input_path=DATA_ASCII / "acctdata.txt",
        record_length=300,
        widths=acct_widths,
        headers=[
            "acct_id",
            "active_status",
            "curr_balance",
            "credit_limit",
            "cash_credit_limit",
            "open_date",
            "expiration_date",
            "reissue_date",
            "curr_cycle_credit",
            "curr_cycle_debit",
            "addr_zip",
            "group_id",
        ],
        row_builder=build_account,
    )

    # CARD (CVACT02Y.cpy, RECLN 150)
    card_widths = [
        16,  # CARD-NUM
        11,  # CARD-ACCT-ID
        3,  # CVV
        50,  # EMBOSSED NAME
        10,  # EXPIRATION DATE
        1,  # ACTIVE STATUS
        59,  # FILLER
    ]

    def build_card(fields: List[str]) -> List[str]:
        (
            card_num,
            acct_id,
            cvv,
            embossed,
            exp_date,
            status,
            _filler,
        ) = fields
        return [
            card_num.rstrip(),
            str(int(acct_id)),
            str(int(cvv)),
            embossed.rstrip(),
            exp_date.rstrip(),
            status.rstrip(),
        ]

    yield ExportSpec(
        name="card",
        input_path=DATA_ASCII / "carddata.txt",
        record_length=150,
        widths=card_widths,
        headers=[
            "card_num",
            "acct_id",
            "cvv",
            "embossed_name",
            "expiration_date",
            "active_status",
        ],
        row_builder=build_card,
    )

    # CARD XREF (CVACT03Y.cpy, ASCII version omits filler, RECLN 36)
    xref_widths = [
        16,  # XREF-CARD-NUM
        9,  # XREF-CUST-ID
        11,  # XREF-ACCT-ID
    ]

    def build_card_xref(fields: List[str]) -> List[str]:
        card_num, cust_id, acct_id = fields
        return [
            card_num.rstrip(),
            str(int(cust_id)),
            str(int(acct_id)),
        ]

    yield ExportSpec(
        name="card_xref",
        input_path=DATA_ASCII / "cardxref.txt",
        record_length=36,
        widths=xref_widths,
        headers=["card_num", "cust_id", "acct_id"],
        row_builder=build_card_xref,
    )

    # TRANSACTION TYPE (CVTRA03Y.cpy / TRNTYPE.ddl, RECLN 60)
    trantype_widths = [
        2,  # TRAN-TYPE
        50,  # TRAN-TYPE-DESC
        8,  # FILLER
    ]

    def build_tran_type(fields: List[str]) -> List[str]:
        tran_type, desc, _filler = fields
        return [tran_type.rstrip(), desc.rstrip()]

    yield ExportSpec(
        name="transaction_type",
        input_path=DATA_ASCII / "trantype.txt",
        record_length=60,
        widths=trantype_widths,
        headers=["tr_type", "tr_description"],
        row_builder=build_tran_type,
    )

    # TRANSACTION TYPE CATEGORY (CVTRA04Y.cpy / TRNTYCAT.ddl, RECLN 60)
    trancatg_widths = [
        2,  # TRAN-TYPE-CD
        4,  # TRAN-CAT-CD
        50,  # TRAN-CAT-TYPE-DESC
        4,  # FILLER
    ]

    def build_tran_cat(fields: List[str]) -> List[str]:
        tran_type_cd, tran_cat_cd, desc, _filler = fields
        return [
            tran_type_cd.rstrip(),
            tran_cat_cd.rstrip(),
            desc.rstrip(),
        ]

    yield ExportSpec(
        name="transaction_type_category",
        input_path=DATA_ASCII / "trancatg.txt",
        record_length=60,
        widths=trancatg_widths,
        headers=["trc_type_code", "trc_type_category", "trc_cat_data"],
        row_builder=build_tran_cat,
    )

    # TRANSACTION CATEGORY BALANCE (CVTRA01Y.cpy, RECLN 50)
    tcatbal_widths = [
        11,  # TRANCAT-ACCT-ID
        2,  # TRANCAT-TYPE-CD
        4,  # TRANCAT-CD
        11,  # TRAN-CAT-BAL (S9(9)V99)
        22,  # FILLER
    ]

    def build_tcatbal(fields: List[str]) -> List[str]:
        acct_id, tran_type_cd, tran_cat_cd, bal, _filler = fields
        return [
            str(int(acct_id)),
            tran_type_cd.rstrip(),
            tran_cat_cd.rstrip(),
            str(decode_zoned_decimal(bal, 2)),
        ]

    yield ExportSpec(
        name="transaction_category_balance",
        input_path=DATA_ASCII / "tcatbal.txt",
        record_length=50,
        widths=tcatbal_widths,
        headers=["acct_id", "tran_type_cd", "tran_cat_cd", "balance"],
        row_builder=build_tcatbal,
    )

    # DISCLOSURE GROUP (CVTRA02Y.cpy, RECLN 50)
    discgrp_widths = [
        10,  # DIS-ACCT-GROUP-ID
        2,  # DIS-TRAN-TYPE-CD
        4,  # DIS-TRAN-CAT-CD
        6,  # DIS-INT-RATE (S9(4)V99)
        28,  # FILLER
    ]

    def build_discgrp(fields: List[str]) -> List[str]:
        group_id, tran_type_cd, tran_cat_cd, rate, _filler = fields
        return [
            group_id.rstrip(),
            tran_type_cd.rstrip(),
            tran_cat_cd.rstrip(),
            str(decode_zoned_decimal(rate, 2)),
        ]

    yield ExportSpec(
        name="disclosure_group",
        input_path=DATA_ASCII / "discgrp.txt",
        record_length=50,
        widths=discgrp_widths,
        headers=["acct_group_id", "tran_type_cd", "tran_cat_cd", "int_rate"],
        row_builder=build_discgrp,
    )

    # DAILY TRANSACTION (CVTRA06Y.cpy, RECLN 350)
    daily_widths = [
        16,  # DALYTRAN-ID
        2,  # DALYTRAN-TYPE-CD
        4,  # DALYTRAN-CAT-CD
        10,  # DALYTRAN-SOURCE
        100,  # DALYTRAN-DESC
        11,  # DALYTRAN-AMT (S9(9)V99)
        9,  # DALYTRAN-MERCHANT-ID
        50,  # DALYTRAN-MERCHANT-NAME
        50,  # DALYTRAN-MERCHANT-CITY
        10,  # DALYTRAN-MERCHANT-ZIP
        16,  # DALYTRAN-CARD-NUM
        26,  # DALYTRAN-ORIG-TS
        26,  # DALYTRAN-PROC-TS
        20,  # FILLER
    ]

    def build_dailytran(fields: List[str]) -> List[str]:
        (
            tran_id,
            tran_type_cd,
            tran_cat_cd,
            source,
            desc,
            amt,
            merchant_id,
            merchant_name,
            merchant_city,
            merchant_zip,
            card_num,
            orig_ts,
            proc_ts,
            _filler,
        ) = fields
        return [
            tran_id.rstrip(),
            tran_type_cd.rstrip(),
            tran_cat_cd.rstrip(),
            source.rstrip(),
            desc.rstrip(),
            str(decode_zoned_decimal(amt, 2)),
            str(int(merchant_id)),
            merchant_name.rstrip(),
            merchant_city.rstrip(),
            merchant_zip.rstrip(),
            card_num.rstrip(),
            orig_ts.rstrip(),
            proc_ts.rstrip(),
        ]

    yield ExportSpec(
        name="card_transaction",
        input_path=DATA_ASCII / "dailytran.txt",
        record_length=350,
        widths=daily_widths,
        headers=[
            "tran_id",
            "tran_type_cd",
            "tran_cat_cd",
            "source",
            "description",
            "amount",
            "merchant_id",
            "merchant_name",
            "merchant_city",
            "merchant_zip",
            "card_num",
            "orig_ts",
            "proc_ts",
        ],
        row_builder=build_dailytran,
    )

    # USER SECURITY from EBCDIC (CSUSR01Y.cpy, RECLN 80)
    sec_widths = [
        8,  # SEC-USR-ID
        20,  # SEC-USR-FNAME
        20,  # SEC-USR-LNAME
        8,  # SEC-USR-PWD
        1,  # SEC-USR-TYPE
        23,  # SEC-USR-FILLER
    ]

    def build_user_sec(fields: List[str]) -> List[str]:
        user_id, fname, lname, pwd, user_type, _filler = fields
        return [
            user_id.rstrip(),
            fname.rstrip(),
            lname.rstrip(),
            pwd.rstrip(),
            user_type.rstrip(),
        ]

    yield ExportSpec(
        name="user_security",
        input_path=DATA_EBCDIC / "AWS.M2.CARDDEMO.USRSEC.PS",
        record_length=80,
        widths=sec_widths,
        headers=["user_id", "first_name", "last_name", "password", "user_type"],
        row_builder=build_user_sec,
        encoding="ebcdic-cp037",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export CardDemo data to CSV for PostgreSQL")
    parser.add_argument(
        "--output-dir",
        default="postgres_export",
        help="Directory where CSV files will be written (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    out_dir = (ROOT / args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    total_rows = 0
    for spec in build_specs():
        total_rows += write_csv(spec, out_dir)

    print(f"Total rows written across all CSVs: {total_rows}")


if __name__ == "__main__":
    main()
