import unittest

from scripts.glue_db2_schemas import (
    db2_type_to_hive,
    load_embedded_schemas,
    parse_db2_create_index,
    parse_db2_create_table,
    table_to_glue_table_input,
)


class TestDb2Schemas(unittest.TestCase):
    def test_parse_create_table_transaction_type(self) -> None:
        ddl = """CREATE TABLE CARDDEMO.TRANSACTION_TYPE
(   TR_TYPE                        CHAR(2) NOT NULL,
    TR_DESCRIPTION                 VARCHAR(50) NOT NULL,
    PRIMARY KEY(TR_TYPE));
"""
        t = parse_db2_create_table(ddl)
        self.assertEqual(t.full_name, "CARDDEMO.TRANSACTION_TYPE")
        self.assertEqual([c.name for c in t.columns], ["TR_TYPE", "TR_DESCRIPTION"])
        self.assertEqual(t.primary_key, ("TR_TYPE",))

    def test_parse_create_index(self) -> None:
        ddl = """CREATE UNIQUE INDEX CARDDEMO.XAUTHFRD
    ON CARDDEMO.AUTHFRDS
    (CARD_NUM ASC, AUTH_TS DESC)
    COPY YES;
"""
        idx = parse_db2_create_index(ddl)
        self.assertEqual(idx.name, "XAUTHFRD")
        self.assertTrue(idx.unique)
        self.assertEqual(idx.table, "CARDDEMO.AUTHFRDS")
        self.assertEqual(idx.columns, (("CARD_NUM", "ASC"), ("AUTH_TS", "DESC")))

    def test_load_embedded(self) -> None:
        schemas = load_embedded_schemas()
        self.assertIn("CARDDEMO.AUTHFRDS", schemas)
        self.assertIn("CARDDEMO.TRANSACTION_TYPE", schemas)
        self.assertIn("CARDDEMO.TRANSACTION_TYPE_CATEGORY", schemas)

        tcat = schemas["CARDDEMO.TRANSACTION_TYPE_CATEGORY"]
        self.assertEqual(tcat.primary_key, ("TRC_TYPE_CODE", "TRC_TYPE_CATEGORY"))
        self.assertEqual(len(tcat.foreign_keys), 1)

    def test_db2_to_hive_types(self) -> None:
        self.assertEqual(db2_type_to_hive("CHAR(2)"), "string")
        self.assertEqual(db2_type_to_hive("VARCHAR(50)"), "string")
        self.assertEqual(db2_type_to_hive("DECIMAL(12,2)"), "decimal(12,2)")
        self.assertEqual(db2_type_to_hive("DATE"), "date")

    def test_glue_table_input(self) -> None:
        schemas = load_embedded_schemas()
        t = schemas["CARDDEMO.TRANSACTION_TYPE"]
        table_input = table_to_glue_table_input(t, s3_location="s3://bucket/path/")
        self.assertEqual(table_input["Name"], "transaction_type")
        cols = table_input["StorageDescriptor"]["Columns"]
        self.assertEqual(cols[0]["Name"], "tr_type")
        self.assertEqual(cols[0]["Type"], "string")
        self.assertIn("db2.primary_key", table_input["Parameters"])


if __name__ == "__main__":
    unittest.main()
