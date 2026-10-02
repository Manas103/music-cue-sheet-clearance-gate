import sqlite3

import pytest

from cue_sheet_gate import db, generator


@pytest.fixture
def dataset():
    """A fresh, fully-built 60-episode synthetic dataset in an in-memory DB.

    One build per test that needs it; the dataset is small (240 rows) and
    the fixed seed makes every test run see byte-identical data.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    summary = generator.build_dataset(conn)
    yield conn, summary
    conn.close()
