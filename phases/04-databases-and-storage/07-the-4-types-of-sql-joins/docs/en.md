# The 4 Types of SQL Joins

> Joining tables wrong doesn't throw an error — it silently returns the wrong data.

**Type:** Learn
**Prerequisites:** Relational Database Basics, Primary and Foreign Keys, SQL SELECT Fundamentals
**Time:** ~25 minutes

---

## The Problem

You're building an e-commerce reporting dashboard. The `orders` table holds every purchase, and the `users` table holds every registered account. You need to answer two different questions: "Which users placed orders last month?" and "Which users have *never* placed an order?" These sound similar, but they require completely different joins — and picking the wrong one silently returns a wrong answer with no error.

Without a solid mental model of joins, you write one pattern for every query and end up either dropping rows you need or inventing NULLs where there should be data. In production, that means underreported revenue, ghost customers, and dashboards that look plausible but are wrong.

Understanding the four join types — INNER, LEFT, RIGHT, FULL OUTER — lets you express exactly what you want: keep only matched rows, keep all rows from one side, or keep every row from both sides regardless of match. Each maps to a precise relationship between tables.

---

## The Concept

### The Mental Model: Overlapping Sets

Think of two tables as two sets. The join type controls which portion of the overlap you keep.

```
Table A (users)         Table B (orders)
  ┌─────────┐             ┌─────────┐
  │  A only │  A ∩ B │  B only │
  └─────────┴─────────────┴─────────┘

INNER JOIN   → A ∩ B           (matched rows only)
LEFT JOIN    → A + (A ∩ B)     (all of A, NULLs for B non-matches)
RIGHT JOIN   → B + (A ∩ B)     (all of B, NULLs for A non-matches)
FULL OUTER   → A + (A ∩ B) + B (everything, NULLs both sides)
```

### The Four Types

| Join Type      | Rows Returned                                                   | NULL Columns       |
|----------------|-----------------------------------------------------------------|--------------------|
| INNER JOIN     | Only rows with a matching key in both tables                    | None               |
| LEFT JOIN      | All rows from the left table; matched rows from the right       | Right-side columns |
| RIGHT JOIN     | All rows from the right table; matched rows from the left       | Left-side columns  |
| FULL OUTER JOIN| All rows from both tables                                       | Both sides         |

### How Joins Execute Under the Hood

The SQL engine evaluates joins in three main strategies. Understanding them matters for performance at scale.

**Nested Loop Join** — for each row in the outer table, scan the inner table for matches. Simple but O(n × m). Works fine when one table is small or an index exists on the join column.

**Hash Join** — build a hash table from the smaller table keyed on the join column, then probe it for every row in the larger table. O(n + m). The default for large unindexed joins in most engines (PostgreSQL, MySQL, SQL Server).

**Merge Join** — both inputs are sorted on the join key, then advanced in lockstep. O(n log n + m log m). Efficient when data is already sorted or indexed, common in analytical databases and when joining on primary keys.

The join *type* (INNER, LEFT, etc.) only controls which non-matching rows are retained after the matching phase. The algorithm above applies to all four types.

### ON vs USING vs NATURAL JOIN

- `ON a.id = b.user_id` — explicit, preferred, handles column name mismatches
- `USING (id)` — shorthand when both tables share the same column name; produces a single output column
- `NATURAL JOIN` — auto-joins on all identically-named columns; dangerous in production (schema changes silently break queries)

---

## Build It

### Sample Schema

```sql
CREATE TABLE users (
  id   INT PRIMARY KEY,
  name TEXT NOT NULL
);

CREATE TABLE orders (
  id      INT PRIMARY KEY,
  user_id INT REFERENCES users(id),
  total   NUMERIC(10,2)
);

INSERT INTO users VALUES (1, 'Alice'), (2, 'Bob'), (3, 'Carol');
INSERT INTO orders VALUES (101, 1, 49.99), (102, 1, 19.99), (103, 2, 89.00);
-- Carol (id=3) has no orders. No order exists for user id=4 (non-existent user).
```

### INNER JOIN — Matched rows only

```sql
SELECT u.name, o.total
FROM   users u
INNER JOIN orders o ON u.id = o.user_id;
```

```
name   | total
-------+-------
Alice  | 49.99
Alice  | 19.99
Bob    | 89.00
```

Carol is excluded — she has no orders. Use INNER JOIN when you only want data that exists on both sides.

### LEFT JOIN — All users, even those without orders

```sql
SELECT u.name, o.total
FROM   users u
LEFT JOIN orders o ON u.id = o.user_id;
```

```
name   | total
-------+-------
Alice  | 49.99
Alice  | 19.99
Bob    | 89.00
Carol  | NULL
```

Carol appears with `NULL` for total. This is the correct join when the left table is your "source of truth" and the right table is optional context.

**Finding users with no orders** — filter on the NULL after a LEFT JOIN:

```sql
SELECT u.name
FROM   users u
LEFT JOIN orders o ON u.id = o.user_id
WHERE  o.id IS NULL;
```

```
name
-----
Carol
```

### RIGHT JOIN — All orders, even orphaned ones

RIGHT JOIN is the mirror of LEFT JOIN. In practice, most engineers rewrite it as a LEFT JOIN with tables swapped — it's easier to read.

```sql
-- Equivalent queries
SELECT u.name, o.total
FROM   users u RIGHT JOIN orders o ON u.id = o.user_id;

-- Cleaner equivalent (preferred):
SELECT u.name, o.total
FROM   orders o LEFT JOIN users u ON o.user_id = u.id;
```

Use RIGHT JOIN when you can't change the table order (e.g., inside a framework-generated query) or when the right table is the one you must retain completely.

### FULL OUTER JOIN — Everything from both sides

```sql
SELECT u.name, o.total
FROM   users u
FULL OUTER JOIN orders o ON u.id = o.user_id;
```

```
name   | total
-------+-------
Alice  | 49.99
Alice  | 19.99
Bob    | 89.00
Carol  | NULL
NULL   | 89.00   -- if an order existed with a deleted user_id
```

FULL OUTER JOIN is the right choice for data reconciliation — comparing two datasets and finding rows present in one but not the other (diff/sync jobs, ETL validation, matching payment records to invoices).

> **Note:** MySQL does not support FULL OUTER JOIN syntax directly. Emulate it with `LEFT JOIN UNION ALL RIGHT JOIN WHERE left.id IS NULL`.

```sql
-- MySQL workaround for FULL OUTER JOIN
SELECT u.name, o.total FROM users u LEFT JOIN orders o ON u.id = o.user_id
UNION ALL
SELECT u.name, o.total FROM users u RIGHT JOIN orders o ON u.id = o.user_id
WHERE u.id IS NULL;
```

---

## Use It

### Choosing the Right Join

| Situation                                              | Join to Use      |
|--------------------------------------------------------|------------------|
| Fetch users and their orders (only users with orders)  | INNER JOIN       |
| Fetch all users, show order count (zero if none)       | LEFT JOIN + GROUP BY |
| Find records in A with no match in B                   | LEFT JOIN + WHERE B.id IS NULL |
| Reconcile two tables, find rows unique to either side  | FULL OUTER JOIN  |
| Two tables, same structure, want all rows from both    | UNION ALL (not a join) |

### Where You'll See This in Production

**PostgreSQL / MySQL / SQL Server** — all four types are standard; prefer LEFT JOIN over RIGHT JOIN for readability. PostgreSQL's query planner picks the physical join algorithm automatically; add indexes on join columns to push it toward an index-nested-loop rather than a sequential hash join.

**Analytical databases (BigQuery, Redshift, Snowflake)** — FULL OUTER JOIN is common in ETL pipelines for CDC (Change Data Capture) reconciliation. These engines handle massive datasets via distributed hash joins; partition join tables on the join key to avoid broadcast shuffles.

**ORMs (ActiveRecord, SQLAlchemy, Prisma)** — most default to INNER JOIN on associations. LEFT JOIN requires an explicit option (e.g., `includes` vs `joins` in ActiveRecord, `leftJoin` in Prisma). Forgetting this causes "missing" records that are simply unmatched.

**Reporting / BI tools (Metabase, Looker, dbt)** — dbt model relationships are defined with ref(); the generated SQL almost always uses LEFT JOIN to preserve the grain of the primary model.

---

## Common Pitfalls

- **Using INNER JOIN when you need LEFT JOIN.** If a user has no orders and you INNER JOIN, they vanish silently. Your COUNT will be wrong and no error will tell you. Default to LEFT JOIN when in doubt; switch to INNER only when you're sure both sides must match.

- **Filtering on a right-table column in WHERE, negating a LEFT JOIN.** `WHERE o.status = 'shipped'` after a LEFT JOIN turns it into an implicit INNER JOIN — NULLs are excluded by the filter. Move that condition into the `ON` clause instead: `ON u.id = o.user_id AND o.status = 'shipped'`.

- **Joining on nullable foreign keys without handling NULL.** If `user_id` can be NULL, `ON u.id = o.user_id` never matches NULL = NULL (SQL NULL semantics). Add a `WHERE o.user_id IS NOT NULL` guard before joining if NULLs in the FK are meaningful.

- **Multiplying rows with many-to-many joins.** Joining `orders` to `order_items` without aggregation first produces one row per item per order. Aggregate first in a subquery or CTE; then join the summary.

- **Assuming RIGHT JOIN and LEFT JOIN are symmetric in all tools.** MySQL supports RIGHT JOIN; SQLite has limited support. More importantly, RIGHT JOIN confuses readers. Standardize on LEFT JOIN in your codebase — it reads left-to-right like natural language.

---

## Exercises

1. **Easy** — Given a `products` table and a `reviews` table, write a query that returns every product along with the count of its reviews. Products with no reviews should show a count of 0, not be omitted.

2. **Medium** — You have a `payments` table and an `invoices` table, both containing a `reference_id`. Write a query that returns all references that appear in *one* table but *not* the other — i.e., the symmetric difference. Use a FULL OUTER JOIN approach.

3. **Hard** — You have three tables: `employees`, `departments`, and `projects`. An employee belongs to one department; a project belongs to one department but may be unassigned. Write a single query that returns every department, the number of employees in it, and the number of active projects, ensuring departments with zero employees or zero projects still appear. Explain your choice of join type for each join.

---

## Key Terms

| Term               | What people think                                      | What it actually means                                                                                  |
|--------------------|--------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| JOIN               | Merging two tables into one                            | Combining rows from two relations based on a predicate; the result is a new relation, not a merge       |
| NULL (in joins)    | An error or missing value to fix                       | A deliberate marker meaning "no match existed on this side"; expected and correct in outer joins        |
| Cartesian Product  | Something that only happens with mistakes              | The default behavior when no ON clause is provided (CROSS JOIN); produces n × m rows                   |
| ON clause          | The same as WHERE                                      | Evaluated during the join phase, before rows are filtered; WHERE runs after; critical for outer joins   |
| Cardinality        | Number of rows in a table                              | The relationship multiplicity between joined tables (1:1, 1:many, many:many); determines row fanout     |
| Left / Right       | The physical left or right side of the screen          | The order the tables are listed in the FROM / JOIN clause; left = first table, right = second table     |
| Equi-join          | Just another word for JOIN                             | A join where the predicate is equality (`=`); most joins are equi-joins; non-equi joins use `<`, `>`, BETWEEN |

---

## Further Reading

- [PostgreSQL Docs — Joins Between Tables](https://www.postgresql.org/docs/current/tutorial-join.html)
- [Use The Index, Luke — Joins and Execution Plans](https://use-the-index-luke.com/sql/join)
- [SQL for Data Analysis — O'Reilly (Cathy Tanimura), Chapter 3](https://www.oreilly.com/library/view/sql-for-data/9781492088776/)
- [MySQL 8.0 Docs — JOIN Syntax](https://dev.mysql.com/doc/refman/8.0/en/join.html)
- [dbt Discourse — Understanding LEFT JOIN vs INNER JOIN in data modeling](https://discourse.getdbt.com/t/understanding-left-join-vs-inner-join-in-data-modeling/2040)
