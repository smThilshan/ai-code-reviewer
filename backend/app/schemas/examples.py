"""Sample requests shown in the /docs "Examples" dropdown for POST /review.

Each one is deliberately flawed in a known way, so you can confirm the
reviewer catches real problems (and stays quiet on clean code). They are API
documentation as much as test data, so they live with the schemas.
"""

from typing import Any

REVIEW_REQUEST_EXAMPLES: dict[str, dict[str, Any]] = {
    "sql_injection": {
        "summary": "SQL injection (expect: high / security, line 4)",
        "value": {
            "language": "python",
            "code": (
                "import sqlite3\n"
                "\n"
                "def get_user(conn, username):\n"
                "    query = \"SELECT * FROM users WHERE name = '\" + username + \"'\"\n"
                "    cursor = conn.cursor()\n"
                "    cursor.execute(query)\n"
                "    return cursor.fetchone()\n"
            ),
        },
    },
    "poor_naming": {
        "summary": "Poor naming (expect: low / style, lines 1-2)",
        "value": {
            "language": "python",
            "code": (
                "def f(a, b):\n"
                "    x = 0\n"
                "    for i in a:\n"
                "        if i > b:\n"
                "            x = x + 1\n"
                "    return x\n"
            ),
        },
    },
    "off_by_one": {
        "summary": "Off-by-one bug (expect: bug, line 3)",
        "value": {
            "language": "python",
            "code": (
                "def sum_first_n(items, n):\n"
                "    total = 0\n"
                "    for i in range(n + 1):\n"
                "        total += items[i]\n"
                "    return total\n"
            ),
        },
    },
    "javascript_sqli_async": {
        "summary": "JavaScript (expect: SQL injection on line 4, forEach(async) bug on line 10)",
        "value": {
            "language": "javascript",
            "code": (
                "const express = require('express');\n"
                "const app = express();\n"
                "app.get('/user', (req, res) => {\n"
                "  const q = \"SELECT * FROM users WHERE name = '\" + req.query.name + \"'\";\n"
                "  db.query(q, (err, rows) => res.send(rows));\n"
                "});\n"
                "\n"
                "async function loadAll(ids) {\n"
                "  const out = [];\n"
                "  ids.forEach(async (id) => {\n"
                "    out.push(await fetchItem(id));\n"
                "  });\n"
                "  return out;\n"
                "}\n"
            ),
        },
    },
    "go_ignored_errors": {
        "summary": "Go (expect: unchecked Scan on line 6, ignored os.Open error on line 12, both bug)",
        "value": {
            "language": "go",
            "code": (
                "package main\n"
                "\n"
                "func getEmail(db *sql.DB, id int) string {\n"
                "    row := db.QueryRow(\"SELECT email FROM users WHERE id = ?\", id)\n"
                "    var email string\n"
                "    row.Scan(&email)\n"
                "    return email\n"
                "}\n"
                "\n"
                "func readConfig(path string) []byte {\n"
                "    buf := make([]byte, 1024)\n"
                "    f, _ := os.Open(path)\n"
                "    f.Read(buf)\n"
                "    return buf\n"
                "}\n"
            ),
        },
    },
    "c_memory_safety": {
        "summary": "C (expect: strcpy overflow on line 3 and printf(msg) format-string bug on line 8, both security)",
        "value": {
            "language": "c",
            "code": (
                "void greet(const char *name) {\n"
                "    char buf[16];\n"
                "    strcpy(buf, name);\n"
                "    printf(\"Hello, %s\\n\", buf);\n"
                "}\n"
                "\n"
                "void log_message(const char *msg) {\n"
                "    printf(msg);\n"
                "}\n"
            ),
        },
    },
    "language_from_filename": {
        "summary": "No `language`, only `filename` (expect: Java inferred; string == on line 3)",
        "value": {
            "filename": "src/main/java/AuthService.java",
            "code": (
                "public class AuthService {\n"
                "    public boolean isAdmin(String role) {\n"
                "        return role == \"admin\";\n"
                "    }\n"
                "}\n"
            ),
        },
    },
    "language_unknown": {
        "summary": "Neither `language` nor `filename` (the model identifies the language itself)",
        "value": {
            "code": (
                "def average(values):\n"
                "    return sum(values) / len(values)\n"
            ),
        },
    },
    "clean_code": {
        "summary": "Control: clean code (expect: no issues, or only trivial ones)",
        "value": {
            "language": "python",
            "code": (
                "def clamp(value: float, low: float, high: float) -> float:\n"
                "    \"\"\"Return `value` limited to the inclusive range [low, high].\"\"\"\n"
                "    if low > high:\n"
                "        raise ValueError(\"low must not exceed high\")\n"
                "    return max(low, min(value, high))\n"
            ),
        },
    },
}


# Real, public, merged pull requests (a merged PR's diff never changes, so
# these keep working). They exercise the success path and each error path.
PR_REVIEW_REQUEST_EXAMPLES: dict[str, dict[str, Any]] = {
    "code_pr": {
        "summary": "Real PR: code + tests + changelog (expect: 2 files reviewed, CHANGES.rst skipped)",
        "value": {"pr_url": "https://github.com/pallets/click/pull/3493"},
    },
    "multi_language_pr": {
        "summary": "Real PR touching Python + TypeScript + JSON (expect: .py/.ts reviewed in their own language, .json skipped)",
        "value": {"pr_url": "https://github.com/microsoft/vscode-python/pull/26134"},
    },
    "docs_only_pr": {
        "summary": "Docs-only PR (expect: 422, no code changes to review)",
        "value": {"pr_url": "https://github.com/psf/requests/pull/7576"},
    },
    "not_found": {
        "summary": "PR that doesn't exist (expect: 404)",
        "value": {"pr_url": "https://github.com/pallets/click/pull/99999999"},
    },
    "invalid_url": {
        "summary": "Not a GitHub PR URL (expect: 422)",
        "value": {"pr_url": "https://example.com/pallets/click/pull/3493"},
    },
}
