import csv
import io
import json
import os
import subprocess
import sys

from ekstre.cli import main


def write(tmp_path, data, name="ekstre.csv"):
    path = tmp_path / name
    path.write_bytes(data)
    return path


def test_csv_to_stdout(tmp_path, csv_cp1254, capsys):
    assert main([str(write(tmp_path, csv_cp1254))]) == 0
    rows = list(csv.DictReader(io.StringIO(capsys.readouterr().out)))
    assert [r["type"] for r in rows] == ["bill", "eft", "fee"]
    assert rows[1]["counterparty"] == "ÖRNEK ŞİRKET A.Ş."
    assert rows[0]["amount"] == "-845.30"


def test_json_with_type_filter(tmp_path, csv_cp1254, capsys):
    assert main([str(write(tmp_path, csv_cp1254)), "-f", "json", "-t", "eft"]) == 0
    items = json.loads(capsys.readouterr().out)
    assert [i["amount"] for i in items] == ["2000.00"]


def test_summary_text(tmp_path, single_amount_xlsx, capsys):
    assert main([str(write(tmp_path, single_amount_xlsx, "e.xlsx")), "--summary"]) == 0
    out = capsys.readouterr().out
    assert "3 transactions, 2026-11-03 to 2026-11-05" in out
    assert "45,000.00" in out
    assert "salary" in out


def test_table(tmp_path, single_amount_xlsx, capsys):
    assert main([str(write(tmp_path, single_amount_xlsx, "e.xlsx")), "-f", "table"]) == 0
    assert "ÖRNEK İŞLETME LTD" in capsys.readouterr().out


def test_output_file_is_excel_friendly(tmp_path, csv_cp1254):
    out = tmp_path / "temiz.csv"
    assert main([str(write(tmp_path, csv_cp1254)), "-o", str(out)]) == 0
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw


def test_error_exit_code(tmp_path, capsys):
    assert main([str(tmp_path / "yok.xlsx")]) == 1
    assert "not found" in capsys.readouterr().err


def test_subprocess_prints_utf8(tmp_path, csv_cp1254):
    """The installed command must not mangle Turkish letters on a cp1254 console."""
    env = {**os.environ, "PYTHONIOENCODING": "cp1254"}
    env.pop("PYTHONUTF8", None)
    result = subprocess.run(
        [sys.executable, "-m", "ekstre", str(write(tmp_path, csv_cp1254)), "-f", "json"],
        capture_output=True,
        env=env,
        check=True,
    )
    assert "ÖRNEK ŞİRKET A.Ş." in result.stdout.decode("utf-8")
