#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for summarize helpers (no live network/LLM)."""
import unittest
import summarize


class TestSafeUrl(unittest.TestCase):
    def test_https_ok(self):
        self.assertTrue(summarize.is_safe_url("https://example.com/a"))

    def test_http_ok(self):
        self.assertTrue(summarize.is_safe_url("http://example.com/a"))

    def test_reject_localhost(self):
        self.assertFalse(summarize.is_safe_url("http://127.0.0.1/x"))
        self.assertFalse(summarize.is_safe_url("http://localhost/x"))

    def test_reject_private(self):
        self.assertFalse(summarize.is_safe_url("http://192.168.1.1/x"))
        self.assertFalse(summarize.is_safe_url("http://10.0.0.2/x"))

    def test_reject_file(self):
        self.assertFalse(summarize.is_safe_url("file:///etc/passwd"))

    def test_reject_empty(self):
        self.assertFalse(summarize.is_safe_url(""))
        self.assertFalse(summarize.is_safe_url("not-a-url"))


class TestExtract(unittest.TestCase):
    def test_strips_script_and_keeps_article(self):
        html = "<html><script>bad()</script><article><p>Hello world news.</p></article></html>"
        t = summarize.extract_text(html)
        self.assertIn("Hello world news", t)
        self.assertNotIn("bad", t)

    def test_truncates(self):
        html = "<article>" + ("字" * 5000) + "</article>"
        t = summarize.extract_text(html, limit=100)
        self.assertLessEqual(len(t), 100)


if __name__ == "__main__":
    unittest.main()
