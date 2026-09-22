"""Buggy code samples with ground truth, for measuring review quality by language.

Each sample is realistic code with issues planted in it. Ground truth is stated
as "the line containing THIS text should be flagged, as one of THESE
categories", so line numbers are computed, never hand-counted (hand-counting
is how ground truth silently goes wrong).

The code itself deliberately contains no hints ("BUG here" comments would leak
the answer to the model and invalidate the test).

`cats` is the set of categories that count as a *correct* label. Where a defect
is genuinely both (e.g. use-after-free is a bug and a vulnerability), both are
accepted; where the defect is unambiguous, only one is. Detection (right line)
and labelling (right category) are scored separately.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Expected:
    id: str
    find: str  # unique substring of the line that should be flagged
    cats: frozenset[str]
    alt: str = ""  # optional second line that is an equally reasonable place to flag it


@dataclass(frozen=True)
class Sample:
    id: str
    language: str
    code: str
    expected: list[Expected] = field(default_factory=list)

    def lines_of(self, expected: "Expected") -> set[int]:
        """Every line on which flagging `expected` counts as detecting it."""
        lines = {self.line_of(expected.find)}
        if expected.alt:
            lines.add(self.line_of(expected.alt))
        return lines

    def line_of(self, needle: str) -> int:
        """1-based line number of the line containing `needle`.

        `needle` must match exactly one line, unless it ends in "@N", which
        picks the Nth match (for a statement that legitimately appears twice).
        """
        occurrence = None
        if "@" in needle and needle.rsplit("@", 1)[1].isdigit():
            needle, n = needle.rsplit("@", 1)
            occurrence = int(n)
        hits = [i for i, line in enumerate(self.code.split("\n"), 1) if needle in line]
        if occurrence is not None:
            return hits[occurrence - 1]
        assert len(hits) == 1, f"{self.id}: {needle!r} matched {len(hits)} lines"
        return hits[0]


def E(id: str, find: str, *cats: str, alt: str = "") -> Expected:  # noqa: N802
    return Expected(id, find, frozenset(cats), alt)


PY_SERVICE = Sample(
    id="py-service",
    language="python",
    code='''import os
import pickle
import sqlite3

SECRET_KEY = "hunter2-prod-key"


def get_user(conn, user_id):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = %s" % user_id)
    return cur.fetchone()


def add_tag(user, tag, tags=[]):
    tags.append(tag)
    user["tags"] = tags
    return user


def load_session(blob):
    return pickle.loads(blob)


def find_duplicates(items):
    dupes = []
    for i in range(len(items)):
        for j in range(len(items)):
            if i != j and items[i] == items[j]:
                dupes.append(items[i])
    return dupes
''',
    expected=[
        E("sql-injection", "% user_id", "security"),
        E("hardcoded-secret", "SECRET_KEY =", "security"),
        E("mutable-default", "tags=[]", "bug"),
        E("pickle", "pickle.loads", "security"),
        E("quadratic", "for j in range", "performance", alt="for i in range(len(items))"),
    ],
)

PY_PITFALLS = Sample(
    id="py-pitfalls",
    language="python",
    code='''import requests


def fetch_all(urls):
    results = []
    for url in urls:
        try:
            r = requests.get(url)
            results.append(r.json())
        except:
            pass
    return results


def average(values):
    return sum(values) / len(values)


def is_admin(role):
    return role is "admin"


def clamp(value, low, high):
    if low > high:
        raise ValueError("low must not exceed high")
    return max(low, min(value, high))
''',
    expected=[
        E("no-timeout", "requests.get(url)", "bug", "performance"),
        E("bare-except", "except:", "bug", "style"),
        E("empty-division", "/ len(values)", "bug"),
        E("is-literal", 'role is "admin"', "bug"),
    ],
)

JS_EXPRESS = Sample(
    id="js-express",
    language="javascript",
    code='''const express = require('express');
const mysql = require('mysql');

const app = express();
const db = mysql.createConnection({
  host: 'localhost',
  user: 'root',
  password: 'admin123',
  database: 'shop',
});

app.get('/user', (req, res) => {
  const q = "SELECT * FROM users WHERE name = '" + req.query.name + "'";
  db.query(q, (err, rows) => {
    res.send(rows);
  });
});

app.get('/greet', (req, res) => {
  res.send('<h1>Hello ' + req.query.name + '</h1>');
});

async function loadAll(ids) {
  const out = [];
  ids.forEach(async (id) => {
    out.push(await fetchItem(id));
  });
  return out;
}
''',
    expected=[
        E("hardcoded-password", "password: 'admin123'", "security"),
        E("sql-injection", "SELECT * FROM users", "security"),
        E("xss", "'<h1>Hello '", "security"),
        E("async-foreach", "ids.forEach(async", "bug"),
    ],
)

JS_PITFALLS = Sample(
    id="js-pitfalls",
    language="javascript",
    code='''function paginate(items, page, size) {
  const start = page * size;
  return items.slice(start, start + size + 1);
}

function parseAge(s) {
  return parseInt(s);
}

var total = 0;

function addToTotal(list) {
  for (var i = 0; i <= list.length; i++) {
    total += list[i].price;
  }
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}
''',
    expected=[
        E("slice-off-by-one", "start + size + 1", "bug"),
        E("loop-off-by-one", "i <= list.length", "bug"),
        E("parseint", "parseInt(s)", "bug", "style"),
        E("global-var", "var total", "style", "bug"),
    ],
)

JAVA_REPO = Sample(
    id="java-repo",
    language="java",
    code='''import java.io.*;
import java.sql.*;

public class UserRepository {
    private static final String DB_PASSWORD = "P@ssw0rd!";

    public String findEmail(Connection conn, String username) throws SQLException {
        Statement st = conn.createStatement();
        ResultSet rs = st.executeQuery("SELECT email FROM users WHERE name = '" + username + "'");
        if (rs.next()) {
            return rs.getString("email");
        }
        return null;
    }

    public String readFirstLine(String path) throws IOException {
        BufferedReader reader = new BufferedReader(new FileReader(path));
        String line = reader.readLine();
        return line;
    }

    public boolean isAdmin(String role) {
        return role == "admin";
    }
}
''',
    expected=[
        E("hardcoded-password", "DB_PASSWORD =", "security"),
        E("sql-injection", "executeQuery(", "security"),
        E("unclosed-statement", "conn.createStatement()", "bug", "performance"),
        E("unclosed-reader", "new FileReader(path)", "bug", "security", "performance", alt="reader.readLine()"),
        E("string-equality", 'role == "admin"', "bug"),
    ],
)

JAVA_ORDERS = Sample(
    id="java-orders",
    language="java",
    code='''import java.util.*;

public class OrderService {
    private final Map<String, Integer> stock = new HashMap<>();

    public int totalQuantity(List<Integer> quantities) {
        int total = 0;
        for (int i = 0; i <= quantities.size(); i++) {
            total += quantities.get(i);
        }
        return total;
    }

    public void reserve(String sku, int qty) {
        try {
            int available = stock.get(sku);
            stock.put(sku, available - qty);
        } catch (Exception e) {
        }
    }

    public String join(List<String> names) {
        String joined = "";
        for (String n : names) {
            joined += n + ",";
        }
        return joined;
    }
}
''',
    expected=[
        E("off-by-one", "i <= quantities.size()", "bug"),
        E("unboxing-npe", "int available = stock.get(sku)", "bug"),
        E("swallowed-exception", "catch (Exception e)", "bug", "style"),
        E("string-concat-loop", 'joined += n + ","', "performance", alt='String joined = ""'),
    ],
)

GO_HANDLERS = Sample(
    id="go-handlers",
    language="go",
    code='''package main

import (
	"database/sql"
	"fmt"
	"net/http"
	"os"
)

func getUser(db *sql.DB, name string) (string, error) {
	row := db.QueryRow("SELECT email FROM users WHERE name = '" + name + "'")
	var email string
	row.Scan(&email)
	return email, nil
}

func readConfig(path string) []byte {
	f, _ := os.Open(path)
	defer f.Close()
	buf := make([]byte, 1024)
	f.Read(buf)
	return buf
}

func handler(w http.ResponseWriter, r *http.Request) {
	fmt.Fprintf(w, r.URL.Query().Get("msg"))
}
''',
    expected=[
        E("sql-injection", "db.QueryRow(", "security"),
        E("unchecked-scan", "row.Scan(&email)", "bug"),
        E("ignored-open-error", "f, _ := os.Open", "bug"),
        E("format-string", "fmt.Fprintf(w,", "security"),
    ],
)

GO_CONCURRENCY = Sample(
    id="go-concurrency",
    language="go",
    code='''package main

import (
	"os"
	"sync"
)

func processAll(items []int) []int {
	var results []int
	var wg sync.WaitGroup
	for _, it := range items {
		wg.Add(1)
		go func(n int) {
			defer wg.Done()
			results = append(results, n*2)
		}(it)
	}
	wg.Wait()
	return results
}

var counts map[string]int

func record(key string) {
	counts[key]++
}

func readAll(files []string) {
	for _, name := range files {
		f, err := os.Open(name)
		if err != nil {
			continue
		}
		defer f.Close()
	}
}
''',
    expected=[
        E("data-race", "results = append(results", "bug", alt="go func(n int)"),
        E("nil-map", "counts[key]++", "bug", alt="var counts map[string]int"),
        E("defer-in-loop", "defer f.Close()", "bug", "performance", alt="for _, name := range files"),
    ],
)

C_MEMORY = Sample(
    id="c-memory",
    language="c",
    code='''#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void greet(const char *name) {
    char buf[16];
    strcpy(buf, name);
    printf("Hello, %s\\n", buf);
}

char *read_line(FILE *fp) {
    char *line = malloc(128);
    fgets(line, 256, fp);
    return line;
}

void log_message(const char *msg) {
    printf(msg);
}

int *make_array(int n) {
    int *a = malloc(n * sizeof(int));
    a[0] = 1;
    return a;
}

void cleanup(char *p) {
    free(p);
    printf("%s\\n", p);
}
''',
    expected=[
        E("strcpy-overflow", "strcpy(buf, name)", "security"),
        E("fgets-overflow", "fgets(line, 256, fp)", "security", "bug"),
        E("format-string", "printf(msg)", "security"),
        E("unchecked-malloc", "a[0] = 1", "bug", alt="malloc(n * sizeof(int))"),
        E("use-after-free", 'printf("%s\\n", p)', "security", "bug", alt="free(p);"),
    ],
)

C_ARRAYS = Sample(
    id="c-arrays",
    language="c",
    code='''#include <stdlib.h>
#include <string.h>

int sum_array(const int *arr, int n) {
    int total = 0;
    for (int i = 0; i <= n; i++) {
        total += arr[i];
    }
    return total;
}

char *copy_str(const char *src) {
    char *dst = malloc(strlen(src));
    strcpy(dst, src);
    return dst;
}

void remember(const char *s) {
    char *p = malloc(64);
    if (!p) return;
    strncpy(p, s, 63);
    p[63] = 0;
}
''',
    expected=[
        E("off-by-one", "i <= n", "bug", "security"),
        E("missing-nul-byte", "malloc(strlen(src))", "bug", "security", alt="strcpy(dst, src)"),
        E("memory-leak", "char *p = malloc(64)", "bug", "performance"),
    ],
)

SAMPLES: list[Sample] = [
    PY_SERVICE,
    PY_PITFALLS,
    JS_EXPRESS,
    JS_PITFALLS,
    JAVA_REPO,
    JAVA_ORDERS,
    GO_HANDLERS,
    GO_CONCURRENCY,
    C_MEMORY,
    C_ARRAYS,
]


# --------------------------------------------------------------------------- #
# Held-out set. Written AFTER the first evaluation, with different bugs, and
# used to judge any prompt change designed by looking at the main set above.
# A change that only helps the samples it was designed on has overfit; one
# that also helps here is more likely a real improvement.
# --------------------------------------------------------------------------- #

H_PY = Sample(
    id="h-py-reports",
    language="python",
    code='''import subprocess
import yaml


def run_report(name):
    subprocess.call("generate_report.sh " + name, shell=True)


def load_config(path):
    f = open(path)
    return yaml.load(f.read())


def word_counts(text):
    counts = {}
    for word in text.split():
        counts[word] = counts.get(word, 0) + 1
    return counts


def is_valid_port(port):
    return port > 0 and port < 65535
''',
    expected=[
        E("command-injection", "shell=True", "security"),
        E("unclosed-file", "f = open(path)", "bug", "performance"),
        E("unsafe-yaml", "yaml.load(f.read())", "security"),
        E("port-off-by-one", "port < 65535", "bug"),
    ],
)

H_JS = Sample(
    id="h-js-profile",
    language="javascript",
    code='''const API_KEY = 'sk_live_51H8xQ2eZvKYlo2C';

function renderProfile(user) {
  document.getElementById('bio').innerHTML = user.bio;
}

async function saveAll(users) {
  for (const u of users) {
    db.save(u);
  }
  console.log('saved');
}

function mergeDeep(target, source) {
  for (const key in source) {
    if (typeof source[key] === 'object') {
      target[key] = mergeDeep(target[key] || {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
}

function isAdult(age) {
  return age == '18' || age > 18;
}
''',
    expected=[
        E("hardcoded-key", "const API_KEY", "security"),
        E("inner-html-xss", "innerHTML", "security"),
        E("missing-await", "db.save(u)", "bug"),
        E("prototype-pollution", "target[key] = mergeDeep", "security", alt="for (const key in source)"),
        E("loose-equality", "age == '18'", "bug", "style"),
    ],
)

H_JAVA = Sample(
    id="h-java-tokens",
    language="java",
    code='''import java.text.SimpleDateFormat;
import java.util.*;

public class TokenService {
    private final Random random = new Random();
    private final SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd");

    public String newToken() {
        return Long.toHexString(random.nextLong());
    }

    public String today() {
        return fmt.format(new Date());
    }

    public int parse(String s) {
        try {
            return Integer.parseInt(s);
        } catch (Throwable t) {
            return -1;
        }
    }

    public List<String> active(Map<String, Long> sessions, long now) {
        List<String> out = new ArrayList<>();
        for (String id : sessions.keySet()) {
            if (sessions.get(id) > now) {
                out.add(id);
            }
        }
        return out;
    }
}
''',
    expected=[
        E("insecure-random", "new Random()", "security", alt="random.nextLong()"),
        E("shared-dateformat", "fmt.format(new Date())", "bug", alt="new SimpleDateFormat"),
        E("catch-throwable", "catch (Throwable t)", "bug", "style"),
        E("keyset-get", "sessions.get(id) > now", "performance", alt="for (String id : sessions.keySet())"),
    ],
)

H_GO = Sample(
    id="h-go-client",
    language="go",
    code='''package main

import (
	"encoding/json"
	"io"
	"math/rand"
	"net/http"
)

func fetchUser(url string) (map[string]any, error) {
	resp, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	body, _ := io.ReadAll(resp.Body)
	var out map[string]any
	json.Unmarshal(body, &out)
	return out, nil
}

func newSessionID() int {
	return rand.Int()
}

func startWorkers(jobs []int) {
	ch := make(chan int)
	for _, j := range jobs {
		go func(j int) { ch <- j }(j)
	}
}
''',
    expected=[
        E("body-not-closed", "io.ReadAll(resp.Body)", "bug", alt="resp, err := http.Get(url)"),
        E("unmarshal-error-ignored", "json.Unmarshal(body, &out)", "bug"),
        E("weak-random", "rand.Int()", "security"),
        E("goroutine-leak", "go func(j int)", "bug", "performance", alt="ch := make(chan int)"),
    ],
)

H_C = Sample(
    id="h-c-buffers",
    language="c",
    code='''#include <stdio.h>
#include <stdlib.h>
#include <string.h>

void read_name(char *out) {
    gets(out);
}

char *join(const char *a, const char *b) {
    char *r = malloc(strlen(a) + strlen(b) + 2);
    if (!r) return NULL;
    sprintf(r, "%s-%s", a, b);
    return r;
}

int *alloc_matrix(int rows, int cols) {
    return malloc(rows * cols * sizeof(int));
}

void release(char *p) {
    free(p);
    free(p);
}

int average(const int *v, int n) {
    int sum;
    for (int i = 0; i < n; i++) {
        sum += v[i];
    }
    return sum / n;
}
''',
    expected=[
        E("gets", "gets(out)", "security"),
        E("size-overflow", "rows * cols * sizeof(int)", "security", "bug"),
        E("double-free", "free(p);@2", "security", "bug", alt="free(p);@1"),
        E("uninitialized", "int sum;", "bug", alt="sum += v[i]"),
    ],
)

HELDOUT_SAMPLES: list[Sample] = [H_PY, H_JS, H_JAVA, H_GO, H_C]
