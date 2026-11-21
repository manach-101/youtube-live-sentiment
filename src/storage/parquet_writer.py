import os
import tempfile
from pathlib import Path
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


def write_parquet(
    records: list[dict] | pd.DataFrame,
    output_path: str | Path,
    schema: Optional[pa.Schema] = None,
) -> None:
    """Writes records to Parquet atomically (temp file + rename).

    With ``schema`` the output has stable column names, order and types,
    even when ``records`` is empty.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df = records if isinstance(records, pd.DataFrame) else pd.DataFrame(records)

    if schema is not None:
        df = df.reindex(columns=schema.names)
        table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
    else:
        table = pa.Table.from_pandas(df, preserve_index=False)

    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)

    try:
        pq.write_table(table, tmp_name)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
