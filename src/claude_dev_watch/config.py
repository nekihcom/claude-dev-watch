from __future__ import annotations

import os

from dotenv import dotenv_values, find_dotenv


def load_env() -> None:
    """カレントディレクトリから探した .env の値を環境変数に読み込む。

    設定済みの環境変数（GitHub Actions の Secrets など）は優先する。ただし空文字の変数は未設定とみなす。
    シェルで値を入れ損ねた空の変数が残っていると、.env の値が無視されてしまうため。
    """
    path = find_dotenv(usecwd=True)
    if not path:
        return
    for key, value in dotenv_values(path).items():
        if value and not os.environ.get(key):
            os.environ[key] = value
