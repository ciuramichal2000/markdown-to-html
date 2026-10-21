import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import io
import subprocess

import pytest

from mdhtml.__main__ import main

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")


def run_main(argv, stdin=b""):
    stdout, stderr = io.BytesIO(), io.StringIO()
    status = main(argv, stdin=io.BytesIO(stdin), stdout=stdout, stderr=stderr)
    return status, stdout.getvalue(), stderr.getvalue()


def test_converts_a_file_to_html_on_stdout(tmp_path):
    source = tmp_path / "note.md"
    source.write_text("# Hi\n\ntext *x*\n", encoding="utf-8")
    status, out, err = run_main([str(source)])
    assert (status, out, err) == (0, b"<h1>Hi</h1>\n<p>text <em>x</em></p>\n", "")


def test_reads_standard_input_when_the_argument_is_a_dash():
    status, out, _ = run_main(["-"], stdin=b"**x**")
    assert status == 0
    assert out == b"<p><strong>x</strong></p>\n"


def test_non_ascii_text_is_written_as_utf_8(tmp_path):
    source = tmp_path / "pl.md"
    source.write_text("# Zażółć gęślą jaźń\n", encoding="utf-8")
    status, out, _ = run_main([str(source)])
    assert status == 0
    assert out == "<h1>Zażółć gęślą jaźń</h1>\n".encode("utf-8")


def test_byte_order_mark_does_not_end_up_in_the_output(tmp_path):
    source = tmp_path / "bom.md"
    source.write_bytes(b"\xef\xbb\xbf# Title")
    status, out, _ = run_main([str(source)])
    assert (status, out) == (0, b"<h1>Title</h1>\n")


def test_missing_file_reports_an_error_and_prints_nothing(tmp_path):
    missing = str(tmp_path / "nope.md")
    status, out, err = run_main([missing])
    assert status == 1
    assert out == b""
    assert err.startswith("mdhtml: ")
    assert "nope.md" in err


def test_directory_instead_of_file_is_an_error(tmp_path):
    status, out, err = run_main([str(tmp_path)])
    assert (status, out) == (1, b"")
    assert err.startswith("mdhtml: ")


def test_invalid_utf_8_is_reported_with_the_file_name(tmp_path):
    source = tmp_path / "latin1.md"
    source.write_bytes("caf\xe9".encode("latin-1"))
    status, out, err = run_main([str(source)])
    assert (status, out) == (1, b"")
    assert err == f"mdhtml: {source} is not valid UTF-8 text\n"


def test_invalid_utf_8_on_stdin_names_standard_input():
    status, _, err = run_main(["-"], stdin=b"\xff\xfe\x00")
    assert status == 1
    assert "standard input is not valid UTF-8 text" in err


def test_over_nested_input_is_an_error_not_a_crash(tmp_path):
    source = tmp_path / "deep.md"
    source.write_text(">" * 200 + " x", encoding="utf-8")
    status, out, err = run_main([str(source)])
    assert (status, out) == (1, b"")
    assert "nested deeper" in err


def test_missing_argument_is_a_usage_error():
    with pytest.raises(SystemExit) as stopped:
        main([])
    assert stopped.value.code == 2


def test_module_runs_as_a_real_subprocess(tmp_path):
    source = tmp_path / "doc.md"
    source.write_text("- one\n- two\n\n<b>raw</b>\n", encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-m", "mdhtml", str(source)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        timeout=60,
    )
    assert done.returncode == 0
    assert done.stderr == b""
    assert done.stdout == b"<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n<p>&lt;b&gt;raw&lt;/b&gt;</p>\n"
