from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Column:
    name: str
    db2_type: str
    nullable: bool


@dataclass(frozen=True)
class ForeignKey:
    columns: Tuple[str, ...]
    ref_table: str  # DB2-style: SCHEMA.TABLE
    ref_columns: Tuple[str, ...]
    on_delete: Optional[str] = None


@dataclass(frozen=True)
class Index:
    name: str
    table: str  # DB2-style: SCHEMA.TABLE
    unique: bool
    columns: Tuple[Tuple[str, str], ...]  # (col, order)


@dataclass(frozen=True)
class TableSchema:
    full_name: str  # DB2-style: SCHEMA.TABLE
    columns: Tuple[Column, ...]
    primary_key: Tuple[str, ...] = ()
    foreign_keys: Tuple[ForeignKey, ...] = ()
    indexes: Tuple[Index, ...] = ()

    @property
    def db2_schema(self) -> str:
        return self.full_name.split(".", 1)[0]

    @property
    def db2_table(self) -> str:
        return self.full_name.split(".", 1)[1]


# Embedded DB2 DDLs found in this repo under app/**/ddl/*.ddl.
# These are included so this module can be imported in AWS Glue without needing
# the repo layout present on disk.
_EMBEDDED_TABLE_DDLS: Dict[str, str] = {
    "TRNTYPE": """CREATE TABLE CARDDEMO.TRANSACTION_TYPE
(   TR_TYPE                        CHAR(2) NOT NULL,
    TR_DESCRIPTION                 VARCHAR(50) NOT NULL,
    PRIMARY KEY(TR_TYPE));
""",
    "TRNTYCAT": """CREATE TABLE CARDDEMO.TRANSACTION_TYPE_CATEGORY
(   TRC_TYPE_CODE                  CHAR(2) NOT NULL,
    TRC_TYPE_CATEGORY              CHAR(4) NOT NULL,
    TRC_CAT_DATA                   VARCHAR(50) NOT NULL,
    PRIMARY KEY(TRC_TYPE_CODE,TRC_TYPE_CATEGORY),
    FOREIGN KEY TRC_TYPE_CODE (TRC_TYPE_CODE)
    REFERENCES CARDDEMO.TRANSACTION_TYPE (TR_TYPE) ON DELETE RESTRICT);

""",
    "AUTHFRDS": """CREATE TABLE CARDDEMO.AUTHFRDS
(CARD_NUM              CHAR(16)    NOT NULL,
    AUTH_TS                TIMESTAMP   NOT NULL,
    AUTH_TYPE              CHAR(4)             ,
    CARD_EXPIRY_DATE       CHAR(4)             ,
    MESSAGE_TYPE           CHAR(6)             ,
    MESSAGE_SOURCE         CHAR(6)             ,
    AUTH_ID_CODE           CHAR(6)             ,
    AUTH_RESP_CODE         CHAR(2)             ,
    AUTH_RESP_REASON       CHAR(4)             ,
    PROCESSING_CODE        CHAR(6)             ,
    TRANSACTION_AMT        DECIMAL(12,2)       ,
    APPROVED_AMT           DECIMAL(12,2)       ,
    MERCHANT_CATAGORY_CODE CHAR(4)             ,
    ACQR_COUNTRY_CODE      CHAR(3)             ,
    POS_ENTRY_MODE         SMALLINT            ,
    MERCHANT_ID            CHAR(15)            ,
    MERCHANT_NAME          VARCHAR(22)         ,
    MERCHANT_CITY          CHAR(13)            ,
    MERCHANT_STATE         CHAR(02)            ,
    MERCHANT_ZIP           CHAR(09)            ,
    TRANSACTION_ID         CHAR(15)            ,
    MATCH_STATUS           CHAR(1)             ,
    AUTH_FRAUD             CHAR(1)             ,
    FRAUD_RPT_DATE         DATE                ,
    ACCT_ID                DECIMAL(11)         ,
    CUST_ID                DECIMAL(9)          ,
    PRIMARY KEY(CARD_NUM,AUTH_TS )             );

""",
}

_EMBEDDED_INDEX_DDLS: Dict[str, str] = {
    "XTRNTYPE": """CREATE UNIQUE INDEX CARDDEMO.XTRAN_TYPE
    ON CARDDEMO.TRANSACTION_TYPE
        (TR_TYPE   ASC)
                    ERASE NO
                    CLOSE NO;

""",
    "XTRNTYCAT": """CREATE UNIQUE INDEX CARDDEMO.X_TRAN_TYPE_CATG
    ON CARDDEMO.TRANSACTION_TYPE_CATEGORY
        (TRC_TYPE_CODE    ASC, TRC_TYPE_CATEGORY ASC)
     ERASE NO
     CLOSE NO;

""",
    "XAUTHFRD": """CREATE UNIQUE INDEX CARDDEMO.XAUTHFRD
    ON CARDDEMO.AUTHFRDS
    (CARD_NUM ASC, AUTH_TS DESC)
    COPY YES;

""",
}


_CREATE_TABLE_RE = re.compile(
    r"CREATE\s+TABLE\s+(?P<full>[A-Z0-9_]+\.[A-Z0-9_]+)", re.IGNORECASE
)


def _find_balanced_parens_block(sql: str, start_idx: int) -> Tuple[str, int]:
    """Return the text inside the parentheses starting at start_idx.

    start_idx must point at the opening '('.
    """

    if sql[start_idx] != "(":
        raise ValueError("start_idx must point to an opening parenthesis")

    depth = 0
    for i in range(start_idx, len(sql)):
        ch = sql[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return sql[start_idx + 1 : i], i

    raise ValueError("Unbalanced parentheses in DDL")


def _split_top_level_commas(block: str) -> List[str]:
    parts: List[str] = []
    buf: List[str] = []
    depth = 0

    for ch in block:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1

        if ch == "," and depth == 0:
            part = "".join(buf).strip()
            if part:
                parts.append(part)
            buf = []
            continue

        buf.append(ch)

    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)

    return parts


def parse_db2_create_table(ddl: str) -> TableSchema:
    ddl_clean = ddl.strip().rstrip(";")

    m = _CREATE_TABLE_RE.search(ddl_clean)
    if not m:
        raise ValueError("Not a CREATE TABLE statement")

    full_name = m.group("full").upper()

    open_paren = ddl_clean.find("(", m.end())
    if open_paren < 0:
        raise ValueError("CREATE TABLE missing column list")

    block, _ = _find_balanced_parens_block(ddl_clean, open_paren)
    items = _split_top_level_commas(block)

    columns: List[Column] = []
    primary_key: Tuple[str, ...] = ()
    foreign_keys: List[ForeignKey] = []

    for raw in items:
        item = " ".join(raw.replace("\n", " ").split()).strip()
        upper = item.upper()

        if upper.startswith("PRIMARY KEY"):
            pk_cols = _parse_column_list(item)
            primary_key = tuple(c.upper() for c in pk_cols)
            continue

        if upper.startswith("FOREIGN KEY"):
            foreign_keys.append(_parse_foreign_key(item))
            continue

        col = _parse_column_definition(item)
        columns.append(col)

    return TableSchema(
        full_name=full_name,
        columns=tuple(columns),
        primary_key=primary_key,
        foreign_keys=tuple(foreign_keys),
        indexes=(),
    )


def _parse_column_list(fragment: str) -> List[str]:
    # Accept: PRIMARY KEY(col1,col2)
    m = re.search(r"\((?P<cols>[^)]*)\)", fragment)
    if not m:
        raise ValueError(f"Could not parse column list: {fragment}")
    cols = [c.strip() for c in m.group("cols").split(",") if c.strip()]
    return cols


_COLDEF_RE = re.compile(
    r"^(?P<name>[A-Z0-9_]+)\s+(?P<type>[A-Z]+(?:\([^)]*\))?)\s*(?P<rest>.*)$",
    re.IGNORECASE,
)


def _parse_column_definition(fragment: str) -> Column:
    m = _COLDEF_RE.match(fragment)
    if not m:
        raise ValueError(f"Could not parse column definition: {fragment}")

    name = m.group("name").upper()
    db2_type = m.group("type").upper()
    rest = m.group("rest").upper()

    nullable = "NOT NULL" not in rest

    return Column(name=name, db2_type=db2_type, nullable=nullable)


def _parse_foreign_key(fragment: str) -> ForeignKey:
    # Handles both:
    #   FOREIGN KEY (C1) REFERENCES S.T (R1) ON DELETE ...
    # and the repo's:
    #   FOREIGN KEY <constraint_name> (C1) REFERENCES ...

    norm = " ".join(fragment.replace("\n", " ").split())

    # Drop constraint name if present: FOREIGN KEY <name> ( ...
    norm = re.sub(r"(?i)^FOREIGN\s+KEY\s+[A-Z0-9_]+\s+\(", "FOREIGN KEY (", norm)

    m = re.search(
        r"(?i)^FOREIGN\s+KEY\s*\((?P<cols>[^)]*)\)\s*REFERENCES\s+(?P<table>[A-Z0-9_]+\.[A-Z0-9_]+)\s*\((?P<refcols>[^)]*)\)\s*(?P<tail>.*)$",
        norm,
    )
    if not m:
        raise ValueError(f"Could not parse foreign key: {fragment}")

    cols = tuple(c.strip().upper() for c in m.group("cols").split(",") if c.strip())
    ref_table = m.group("table").upper()
    ref_cols = tuple(
        c.strip().upper() for c in m.group("refcols").split(",") if c.strip()
    )

    tail = m.group("tail").upper()
    on_delete = None
    m_del = re.search(r"ON\s+DELETE\s+(RESTRICT|CASCADE|SET\s+NULL|NO\s+ACTION)", tail)
    if m_del:
        on_delete = m_del.group(1).replace(" ", " ")

    return ForeignKey(
        columns=cols,
        ref_table=ref_table,
        ref_columns=ref_cols,
        on_delete=on_delete,
    )


def parse_db2_create_index(ddl: str) -> Index:
    norm = " ".join(ddl.strip().rstrip(";").replace("\n", " ").split())

    m = re.search(
        r"(?i)^CREATE\s+(?P<unique>UNIQUE\s+)?INDEX\s+(?P<name>[A-Z0-9_]+\.[A-Z0-9_]+)\s+ON\s+(?P<table>[A-Z0-9_]+\.[A-Z0-9_]+)\s*\((?P<cols>[^)]*)\)",
        norm,
    )
    if not m:
        raise ValueError("Not a CREATE INDEX statement")

    full_index_name = m.group("name").upper()
    index_name = full_index_name.split(".", 1)[1]
    table = m.group("table").upper()
    unique = bool(m.group("unique"))

    cols: List[Tuple[str, str]] = []
    for part in m.group("cols").split(","):
        p = " ".join(part.strip().split())
        if not p:
            continue
        bits = p.split(" ")
        col = bits[0].upper()
        order = bits[1].upper() if len(bits) > 1 else "ASC"
        if order not in {"ASC", "DESC"}:
            order = "ASC"
        cols.append((col, order))

    return Index(name=index_name, table=table, unique=unique, columns=tuple(cols))


def load_embedded_schemas() -> Dict[str, TableSchema]:
    tables = [parse_db2_create_table(ddl) for ddl in _EMBEDDED_TABLE_DDLS.values()]
    indexes = [parse_db2_create_index(ddl) for ddl in _EMBEDDED_INDEX_DDLS.values()]

    by_full_name: Dict[str, TableSchema] = {t.full_name: t for t in tables}

    idx_by_table: Dict[str, List[Index]] = {}
    for idx in indexes:
        idx_by_table.setdefault(idx.table, []).append(idx)

    out: Dict[str, TableSchema] = {}
    for full_name, table in by_full_name.items():
        out[full_name] = TableSchema(
            full_name=table.full_name,
            columns=table.columns,
            primary_key=table.primary_key,
            foreign_keys=table.foreign_keys,
            indexes=tuple(idx_by_table.get(full_name, [])),
        )

    return out


def db2_type_to_hive(db2_type: str) -> str:
    t = db2_type.strip().upper()

    m = re.match(r"^(CHAR|VARCHAR)\s*\(\s*\d+\s*\)$", t)
    if m:
        return "string"

    m = re.match(r"^DECIMAL\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$", t)
    if m:
        return f"decimal({int(m.group(1))},{int(m.group(2))})"

    m = re.match(r"^DECIMAL\s*\(\s*(\d+)\s*\)$", t)
    if m:
        return f"decimal({int(m.group(1))},0)"

    if t in {"SMALLINT"}:
        return "smallint"
    if t in {"INTEGER", "INT"}:
        return "int"
    if t in {"BIGINT"}:
        return "bigint"
    if t in {"DATE"}:
        return "date"
    if t in {"TIMESTAMP"}:
        return "timestamp"

    raise ValueError(f"Unsupported DB2 type: {db2_type}")


def table_to_glue_table_input(
    table: TableSchema,
    *,
    glue_table_name: Optional[str] = None,
    s3_location: Optional[str] = None,
    storage_format: str = "parquet",
    parameters: Optional[Dict[str, str]] = None,
    include_constraints_as_params: bool = True,
) -> Dict[str, Any]:
    """Build a boto3 Glue create_table/update_table TableInput dict.

    Notes:
      - AWS Glue Data Catalog doesn't enforce PK/FK constraints; we optionally
        persist them in Parameters for lineage/documentation.
      - table names/columns in Glue are effectively case-insensitive, but many
        stacks prefer lowercase.
    """

    glue_table_name = glue_table_name or table.db2_table.lower()

    cols = [
        {
            "Name": c.name.lower(),
            "Type": db2_type_to_hive(c.db2_type),
            "Comment": f"db2:{c.db2_type}{'' if c.nullable else ' not null'}",
        }
        for c in table.columns
    ]

    storage_format = storage_format.lower()
    if storage_format == "parquet":
        input_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
        output_format = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
        serde_lib = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"
        serde_params: Dict[str, str] = {}
        classification = "parquet"
    elif storage_format == "csv":
        input_format = "org.apache.hadoop.mapred.TextInputFormat"
        output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"
        serde_lib = "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe"
        serde_params = {"serialization.format": ",", "field.delim": ","}
        classification = "csv"
    else:
        raise ValueError("storage_format must be 'parquet' or 'csv'")

    tbl_params: Dict[str, str] = {
        "classification": classification,
        "EXTERNAL": "TRUE",
    }
    if parameters:
        tbl_params.update(parameters)

    if include_constraints_as_params:
        if table.primary_key:
            tbl_params["db2.primary_key"] = ",".join(table.primary_key)
        if table.foreign_keys:
            # Compact and deterministic.
            fk_parts = []
            for fk in table.foreign_keys:
                fk_parts.append(
                    f"({','.join(fk.columns)})->{fk.ref_table}({','.join(fk.ref_columns)})"
                )
            tbl_params["db2.foreign_keys"] = ";".join(fk_parts)
        if table.indexes:
            idx_parts = []
            for idx in table.indexes:
                cols_s = ",".join([f"{c}:{o}" for c, o in idx.columns])
                idx_parts.append(f"{idx.name}[{'U' if idx.unique else 'N'}]({cols_s})")
            tbl_params["db2.indexes"] = ";".join(idx_parts)

    storage_descriptor: Dict[str, Any] = {
        "Columns": cols,
        "InputFormat": input_format,
        "OutputFormat": output_format,
        "SerdeInfo": {"SerializationLibrary": serde_lib, "Parameters": serde_params},
        "Location": s3_location,
        "Compressed": False,
        "NumberOfBuckets": -1,
        "StoredAsSubDirectories": False,
    }

    # Location is required for EXTERNAL_TABLEs; leaving it None is sometimes
    # useful when you only want the schema and will set location later.
    if s3_location is None:
        storage_descriptor.pop("Location")

    return {
        "Name": glue_table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": tbl_params,
        "StorageDescriptor": storage_descriptor,
    }


def ensure_glue_tables(
    glue_client: Any,
    *,
    glue_database: str,
    tables: Sequence[TableSchema],
    s3_base_location: Optional[str] = None,
    storage_format: str = "parquet",
    table_name_prefix: str = "",
) -> None:
    """Create or update tables in AWS Glue Data Catalog.

    glue_client: boto3.client('glue')

    If s3_base_location is provided, each table's location will be:
      <s3_base_location>/<table_name>/
    """

    for t in tables:
        glue_table_name = f"{table_name_prefix}{t.db2_table.lower()}"
        location = (
            None
            if s3_base_location is None
            else f"{s3_base_location.rstrip('/')}/{glue_table_name}/"
        )

        table_input = table_to_glue_table_input(
            t,
            glue_table_name=glue_table_name,
            s3_location=location,
            storage_format=storage_format,
        )

        try:
            glue_client.get_table(DatabaseName=glue_database, Name=glue_table_name)
        except glue_client.exceptions.EntityNotFoundException:
            glue_client.create_table(DatabaseName=glue_database, TableInput=table_input)
        else:
            glue_client.update_table(DatabaseName=glue_database, TableInput=table_input)


def to_spark_struct_type(table: TableSchema) -> Any:
    """Convert to pyspark.sql.types.StructType.

    Import is deferred so this module can be imported outside Spark/Glue.
    """

    from pyspark.sql import types as T  # type: ignore

    def _spark_type(db2_type: str) -> Any:
        t = db2_type.strip().upper()
        if re.match(r"^(CHAR|VARCHAR)\s*\(\s*\d+\s*\)$", t):
            return T.StringType()
        m = re.match(r"^DECIMAL\s*\(\s*(\d+)\s*,\s*(\d+)\s*\)$", t)
        if m:
            return T.DecimalType(int(m.group(1)), int(m.group(2)))
        m = re.match(r"^DECIMAL\s*\(\s*(\d+)\s*\)$", t)
        if m:
            return T.DecimalType(int(m.group(1)), 0)
        if t == "SMALLINT":
            return T.ShortType()
        if t in {"INTEGER", "INT"}:
            return T.IntegerType()
        if t == "BIGINT":
            return T.LongType()
        if t == "DATE":
            return T.DateType()
        if t == "TIMESTAMP":
            return T.TimestampType()
        raise ValueError(f"Unsupported DB2 type: {db2_type}")

    fields = [
        T.StructField(c.name.lower(), _spark_type(c.db2_type), nullable=c.nullable)
        for c in table.columns
    ]
    return T.StructType(fields)


def main() -> None:
    schemas = load_embedded_schemas()
    for full_name, t in sorted(schemas.items()):
        print(full_name)
        for c in t.columns:
            print(f"  - {c.name} {c.db2_type} {'NULL' if c.nullable else 'NOT NULL'}")
        if t.primary_key:
            print(f"  PK: {', '.join(t.primary_key)}")
        for fk in t.foreign_keys:
            print(
                f"  FK: ({', '.join(fk.columns)}) -> {fk.ref_table} ({', '.join(fk.ref_columns)})"
            )
        for idx in t.indexes:
            cols_s = ", ".join([f"{c} {o}" for c, o in idx.columns])
            print(f"  IDX: {idx.name} {'UNIQUE' if idx.unique else ''} ({cols_s})")


if __name__ == "__main__":
    main()
