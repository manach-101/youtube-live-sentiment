from pathlib import Path

import pandas as pd


def write_parquet(records: list[dict], output_path: str) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(records)

    df.to_parquet(path, index=False)