# SQL Injection (SQLi)

> Never trust user input — the database will execute exactly what you hand it.

**Type:** Learn
**Prerequisites:** Relational Databases, HTTP Basics, Authentication Fundamentals
**Time:** ~35 minutes

---

## The Problem

Your login page looks correct. It queries the users table, checks the password hash, and redirects on success. But what happens when a user types `' OR '1'='1` into the username field? The SQL your code assembles becomes a tautology — it returns every row in the table, and the first one passes your "did we get a result?" check. The attacker is now logged in as your first user, usually an admin.

That is the entry-level version. In a fully exploited injection, an attacker can dump every table in the database, read arbitrary files from the server's filesystem, write files (and sometimes execute OS commands) using `INTO OUTFILE` or `xp_cmdshell`, and do all of this across multiple requests with no credentials whatsoever. Entire user bases, payment card numbers, PII, and session tokens have been exfiltrated this way. SQLi has been in the OWASP Top 10 continuously since 2003.

The root cause is always the same: user-supplied strings are concatenated directly into a SQL statement before being sent to the database engine. The database cannot distinguish between the developer's intended query structure and the attacker's injected payload, because by the time parsing happens, they are one string.

---

## The Concept

### Why Concatenation Is Dangerous

SQL is parsed as text. When you concatenate user input into a query string, you are mixing *code* with *data* in the same channel. The database parser sees one flat string; it has no idea which part you wrote and which part the user supplied.

```
Developer's intent:
  SELECT * FROM users WHERE name = '<user_input>'

User supplies:  admin' --
Resulting SQL:  SELECT * FROM users WHERE name = 'admin' --'
                                                         ^^
                                          everything after -- is a comment
```

The single quote closes the string literal the developer opened, the `--` comments out the rest of the line, and the attacker has reshaped the query without touching any source code.

### Attack Taxonomy

| Category | Technique | Data Returned |
|---|---|---|
| **Classic / Tautology** | `' OR 1=1 --` | All rows; used for auth bypass |
| **In-band — UNION** | `UNION SELECT username, password FROM users --` | Injected columns appended to result |
| **In-band — Error** | `EXTRACTVALUE(1, CONCAT(0x7e, (SELECT version())))` | DB version/data in error message |
| **Blind — Boolean** | `' AND SUBSTRING(password,1,1)='a' --` | True/false page difference |
| **Blind — Time** | `'; IF(1=1) WAITFOR DELAY '0:0:5' --` | Response delay encodes truth value |
| **Out-of-band** | `LOAD_FILE / INTO OUTFILE / DNS exfil` | Side channel (DNS, HTTP) |

### How Each Attack Works

**Tautology / Auth Bypass**

```
Input:  ' OR '1'='1
Query:  SELECT id FROM users WHERE user='' OR '1'='1' AND pass=''
```

`'1'='1'` is always true, so the WHERE clause matches every row. The application picks the first row and proceeds as if login succeeded.

**UNION-Based Extraction**

UNION requires the same number of columns and compatible types. The attacker first probes column count with `ORDER BY 1`, `ORDER BY 2`, … until an error appears, revealing the column count. Then:

```sql
-- Probe: find a column that renders on screen
' UNION SELECT NULL, NULL, NULL --

-- Extract data once column layout is known
' UNION SELECT username, password_hash, email FROM users --
```

The injected rows appear in the response body alongside the legitimate rows.

**Blind Boolean-Based**

No data appears in the response, but the page behaves differently for true vs. false conditions.

```
True  (page loads normally):  ' AND 1=1 --
False (page shows error/empty): ' AND 1=2 --

Extract a character:
  ' AND SUBSTRING((SELECT password FROM users WHERE id=1),1,1)='a' --
  ' AND SUBSTRING((SELECT password FROM users WHERE id=1),1,1)='b' --
  ... (binary search reduces this to ~7 requests per character)
```

**Blind Time-Based**

Used when the page renders identically regardless of truth value.

```sql
-- MySQL
' AND IF(SUBSTRING(password,1,1)='a', SLEEP(5), 0) --

-- MSSQL
'; IF SUBSTRING(password,1,1)='a' WAITFOR DELAY '0:0:5' --

-- PostgreSQL
'; SELECT CASE WHEN SUBSTRING(password,1,1)='a' THEN pg_sleep(5) ELSE pg_sleep(0) END --
```

A 5-second delay means the condition was true. Tools like sqlmap automate the binary search across all characters.

### ASCII Flow: Parameterized vs. Concatenated

```
VULNERABLE (string concatenation)
─────────────────────────────────
App Code          DB Driver         Parser
  │                   │                │
  │──"SELECT … '"+inp─▶               │
  │                   │──full string──▶│ (parses code + data as one unit)
  │                   │                │ ← INJECTION POSSIBLE

SAFE (parameterized query / prepared statement)
───────────────────────────────────────────────
App Code          DB Driver         Parser
  │                   │                │
  │──"SELECT … ?"─────▶               │
  │                   │──query only───▶│ ← structure compiled
  │──value "admin"────▶               │
  │                   │──bind value───▶│ ← value inserted as literal, never parsed
  │                   │                │ ← INJECTION IMPOSSIBLE
```

The driver sends the query template and the value in *separate protocol messages*. The DB engine compiles the execution plan before the value ever arrives, so the value can never alter the plan.

---

## Build It / In Depth

### Step 1 — Reproduce the Vulnerability

```python
# vulnerable.py — NEVER do this
import sqlite3

def login(username: str, password: str) -> bool:
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # String concatenation: attacker controls the query structure
    query = f"SELECT id FROM users WHERE username='{username}' AND password='{password}'"
    print("Executing:", query)
    cur.execute(query)
    return cur.fetchone() is not None

# Normal use
login("alice", "s3cr3t")
# → SELECT id FROM users WHERE username='alice' AND password='s3cr3t'

# Attack payload
login("admin' --", "anything")
# → SELECT id FROM users WHERE username='admin' --' AND password='anything'
# → The password check is commented out. Returns the admin row. login() returns True.
```

### Step 2 — Fix with Parameterized Queries

```python
# safe.py
import sqlite3

def login(username: str, password: str) -> bool:
    conn = sqlite3.connect("app.db")
    cur = conn.cursor()
    # Placeholders: the driver handles escaping, not you
    cur.execute(
        "SELECT id FROM users WHERE username = ? AND password = ?",
        (username, password),          # passed separately, never interpolated
    )
    return cur.fetchone() is not None

# Attack payload is now harmless
login("admin' --", "anything")
# The value "admin' --" is bound as a literal string.
# DB sees: WHERE username = 'admin'' --' AND password = 'anything'
# No rows match → returns False
```

### Step 3 — ORM Layer (SQLAlchemy)

```python
from sqlalchemy.orm import Session
from models import User

def login(session: Session, username: str, password: str) -> bool:
    user = (
        session.query(User)
        .filter(User.username == username, User.password == password)
        .first()
    )
    return user is not None
    # SQLAlchemy generates parameterized SQL automatically.
    # You never touch string interpolation.
```

### Step 4 — Detect with sqlmap (Audit Your Own App)

```bash
# Point sqlmap at a login form and let it enumerate the database
sqlmap -u "http://localhost:5000/login" \
       --data "username=test&password=test" \
       --level=3 \
       --risk=2 \
       --dbs          # list databases
       --tables       # list tables
       --dump         # dump table contents
```

Use `sqlmap` against your own staging environment during security testing. It tries every injection category automatically and produces a full vulnerability report.

### Step 5 — Input Validation as Defense-in-Depth

Parameterized queries are the primary control. Validation is an additional layer.

```python
import re

def validate_username(value: str) -> str:
    # Allow only alphanumeric + underscore, max 64 chars
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", value):
        raise ValueError("Invalid username format")
    return value
```

Validation narrows the attack surface but is **not** a substitute for parameterized queries. An attacker can often encode payloads to bypass naive filters.

---

## Use It

### Framework and Library Support

| Stack | Parameterized Query Mechanism | Notes |
|---|---|---|
| Python / psycopg2 | `%s` placeholders | Never use Python string `%` formatting with SQL |
| Python / SQLAlchemy | ORM `.filter()`, `text()` with `:param` | Raw `text()` still requires explicit `bindparams` |
| Node.js / pg | `$1, $2` positional params | Pool `.query(sql, [vals])` |
| Node.js / Prisma | ORM — all queries parameterized | Escape hatch `$queryRaw` still uses tagged templates |
| Java / JDBC | `PreparedStatement` | Never `Statement.execute(string)` |
| Go / database/sql | `db.Query(sql, args...)` | Placeholders are `$1` (postgres) or `?` (mysql) |
| PHP / PDO | `PDOStatement::bindParam` | `mysql_query()` is obsolete and unsafe |
| Ruby / ActiveRecord | `.where("name = ?", name)` | Never interpolate into `.where` string |

### Web Application Firewalls (WAF)

A WAF (AWS WAF, Cloudflare, ModSecurity) can detect and block common SQLi patterns as an additional layer. Configure managed rule sets like AWS's `AWSManagedRulesSQLiRuleSet`. WAFs catch known signatures but are not a substitute for parameterized queries — advanced obfuscation techniques routinely bypass them.

### Stored Procedures

Stored procedures with fixed SQL inside the procedure body are safe when the procedure itself does not use dynamic SQL. A procedure that builds and `EXEC`s a string internally is just as vulnerable as application-level concatenation.

```sql
-- SAFE: fixed SQL, bound parameter
CREATE PROCEDURE GetUser @Username NVARCHAR(50)
AS
  SELECT id, email FROM users WHERE username = @Username;

-- STILL VULNERABLE: dynamic SQL inside procedure
CREATE PROCEDURE SearchUser @Input NVARCHAR(200)
AS
  EXEC ('SELECT * FROM users WHERE name = ''' + @Input + '''');
```

---

## Common Pitfalls

- **Sanitizing instead of parameterizing.** Developers add `replace("'", "''")` or `addslashes()` and believe the problem is solved. Character-set exploits, multi-byte encodings, and less-obvious delimiters break these filters. Always parameterize; treat sanitization as defense-in-depth, not the primary fix.

- **Using parameterized queries for values but concatenating column or table names.** Placeholders only work for *data values*, not SQL identifiers (column names, table names, ORDER BY direction). If you must accept dynamic identifiers, validate them against a strict allowlist of known-good values before interpolating.

  ```python
  ALLOWED_COLUMNS = {"created_at", "username", "email"}
  if sort_by not in ALLOWED_COLUMNS:
      raise ValueError("Invalid sort column")
  query = f"SELECT * FROM users ORDER BY {sort_by}"  # safe because allowlisted
  ```

- **Trusting ORM "raw" escape hatches.** Every major ORM provides a way to drop down to raw SQL: `raw()`, `text()`, `$queryRaw`, `execute()`. Those interfaces bypass the ORM's parameterization. Always pass values as bind parameters even in raw SQL.

- **Forgetting second-order injection.** Data stored in the database (e.g., a username containing `'`) can itself be unsafe when retrieved and inserted into a *different* query later. Parameterize every query, not just the ones receiving direct user input.

- **Logging injected input and then querying logs.** If your SIEM or analytics pipeline queries over raw log lines using string concatenation, a payload in the original request can resurface as an injection in the logging layer.

---

## Exercises

1. **Easy** — Create a SQLite database with a `users` table. Write a Python function that takes a username and returns the user's email. Write the vulnerable version (string concatenation) and confirm that `' OR '1'='1` returns a row. Then fix it with a parameterized query and verify the attack no longer works.

2. **Medium** — Set up a local MySQL instance with two tables: `users` and `orders`. Write a search endpoint in Flask that accepts a `?q=` parameter and searches usernames. Use sqlmap to confirm the endpoint is vulnerable, then fix it. Verify sqlmap reports no injection after the fix.

3. **Hard** — Design a dynamic reporting API that allows callers to choose the sort column (`?sort=created_at`) and sort direction (`?dir=asc`). Implement it safely by combining a parameterized query for all data values with an allowlist check for the identifier. Add a test suite that submits a payload like `sort=created_at; DROP TABLE users --` and asserts the query is rejected before it reaches the database, and that `sort=created_at` returns correctly sorted results.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **SQL Injection** | Only a login-bypass trick | A full data-exfiltration and sometimes code-execution vulnerability class |
| **Parameterized Query** | A performance optimization | The primary security control — separates query structure from data so user input can never reshape the SQL |
| **Prepared Statement** | Same as parameterized query | Technically, a pre-compiled query plan that accepts bound parameters; in most drivers these are the same mechanism |
| **Blind SQLi** | Less severe because no data appears | Equally dangerous — full databases are dumped one bit at a time via boolean or timing side channels |
| **WAF** | Complete SQLi protection | A detection and filtering layer; does not eliminate the vulnerability; bypassable by obfuscation |
| **Stored Procedure** | Always safe from injection | Safe only when the procedure body uses fixed SQL; procedures that build dynamic SQL internally are still vulnerable |
| **ORM** | Immune to SQLi by design | Parameterizes standard queries; raw/escape-hatch APIs still require explicit bind parameters |

---

## Further Reading

- [OWASP SQL Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html) — The canonical reference for mitigations, with language-specific examples.
- [PortSwigger Web Security Academy — SQL Injection](https://portswigger.net/web-security/sql-injection) — Interactive labs covering every injection category; free and hands-on.
- [sqlmap Documentation](https://sqlmap.org/) — Official docs for the industry-standard automated SQLi scanner used in legitimate penetration testing.
- [NIST NVD — CWE-89: Improper Neutralization of Special Elements in SQL Commands](https://cwe.mitre.org/data/definitions/89.html) — Formal weakness classification and examples used in CVE reporting.
- [The Web Application Hacker's Handbook, 2nd Edition](https://www.wiley.com/en-us/The+Web+Application+Hacker%27s+Handbook%3A+Finding+and+Exploiting+Security+Flaws%2C+2nd+Edition-p-9781118026472) — Chapter 9 covers SQLi in depth with exploitation technique and defense guidance.
