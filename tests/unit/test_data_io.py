"""Unit tests for postmule.data._io."""

from datetime import date

import pytest

from postmule.data._io import atomic_write, recent_years, year_from


class TestAtomicWrite:
    def test_creates_file(self, tmp_path):
        path = tmp_path / "out.json"
        atomic_write(path, '{"x": 1}')
        assert path.exists()

    def test_content_matches(self, tmp_path):
        path = tmp_path / "out.txt"
        atomic_write(path, "hello world")
        assert path.read_text(encoding="utf-8") == "hello world"

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "out.txt"
        atomic_write(path, "first")
        atomic_write(path, "second")
        assert path.read_text(encoding="utf-8") == "second"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "a" / "b" / "c" / "out.txt"
        atomic_write(path, "content")
        assert path.exists()

    def test_unicode_content_preserved(self, tmp_path):
        path = tmp_path / "unicode.txt"
        content = "café — naïve • résumé"
        atomic_write(path, content)
        assert path.read_text(encoding="utf-8") == content


class TestYearFrom:
    def test_extracts_year_from_valid_date(self):
        assert year_from("2023-06-15") == 2023

    def test_extracts_year_from_year_only(self):
        assert year_from("2021-01-01") == 2021

    def test_returns_today_year_for_empty_string(self):
        assert year_from("") == date.today().year

    def test_returns_today_year_for_invalid_string(self):
        assert year_from("not-a-date") == date.today().year

    def test_returns_today_year_for_short_string(self):
        assert year_from("202") == date.today().year

    def test_returns_today_year_for_none(self):
        assert year_from(None) == date.today().year


class TestRecentYears:
    def test_returns_n_years(self):
        years = recent_years(3)
        assert len(years) == 3

    def test_most_recent_first(self):
        years = recent_years(3)
        assert years[0] > years[1] > years[2]

    def test_includes_current_year(self):
        years = recent_years(3)
        assert date.today().year in years

    def test_default_is_three(self):
        assert len(recent_years()) == 3

    def test_custom_n(self):
        assert len(recent_years(5)) == 5
