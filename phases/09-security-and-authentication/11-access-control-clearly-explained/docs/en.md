# Access Control Clearly Explained

> Access control is not one thing — it is a family of models, and picking the wrong one will either cripple your flexibility or destroy your ability to audit it.

**Type:** Learn
**Prerequisites:** Authentication fundamentals, JWT and session tokens, API gateway patterns
**Time:** ~25 minutes

---

## The Problem

You built authentication. Users can log in. Now comes the harder question: once a user is inside, what are they allowed to do?

Without a deliberate access control model, systems default to one of two failure modes. The first is "allow everything": a newly onboarded support agent can export your entire customer database, cancel subscriptions, and modify billing records because there was never a clear boundary between roles. The second is "hard-code everything": every permission check is a one-off `if user.id == ADMIN_ID` buried somewhere in service code, meaning you can never answer the question "who can delete an invoice?" without grepping the entire codebase.

The concrete damage surfaces during an audit or incident. A SaaS company reports a breach: a compromised customer support account accessed records belonging to a different tenant. Investigation reveals the support role had no scope restrictions — it was granted at the account level, not the tenant level. There was no access control model, only wishful thinking dressed up as business logic.

Access control answers a single structural question: **is subject S allowed to perform action A on resource R?** The three dominant models — ACL, RBAC, and ABAC — answer that question differently, and the right one depends on how your authorization dimensions grow over time.

---

## The Concept

### The Core Request Flow

Every access decision passes through two logical components, regardless of which model you use:

```
 ┌──────────────┐      ┌─────────────────────┐      ┌────────────┐
 │   Subject    │──────▶  Policy Enforcement  │──────▶  Resource  │
 │  (user/svc)  │      │     Point (PEP)      │      │  (API,DB)  │
 └──────────────┘      └──────────┬──────────┘      └────────────┘
                                  │ asks
                                  ▼
                       ┌─────────────────────┐
                       │  Policy Decision    │
                       │     Point (PDP)     │
                       │                     │
                       │  [ACL / RBAC / ABAC │
                       │   policy engine]    │
                       └─────────────────────┘
```

The **PEP** sits at the entry point of every protected operation (an API gateway, a middleware function, a database row-security policy). When a request arrives, it calls the **PDP** — the component that holds and evaluates rules. The PDP returns `PERMIT` or `DENY`. The PEP enforces the decision and never lets business logic re-litigate it.

---

### Model 1: Access Control List (ACL)

An ACL is the simplest possible representation: a list attached to a resource enumerating exactly which subjects can do what.

```
Resource: /reports/q4-financials.pdf
  alice  → READ
  bob    → READ, WRITE
  carol  → READ, WRITE, DELETE
```

A Unix file permission string (`rwxr-xr--`) is an ACL. AWS S3 bucket policies started as ACLs. The mental model is a door with a literal guest list.

**When ACLs work well:** small, stable systems where the set of users is known, bounded, and changes infrequently. A shared network drive for a five-person team, a GitHub repository with explicit collaborator grants.

**When ACLs collapse:** at a thousand users and ten thousand resources, you now have a matrix of a million cells to maintain. Adding a new employee means touching every resource they need. Auditing "what can alice do?" requires scanning every resource. Revoking access on offboarding is catastrophically error-prone.

---

### Model 2: Role-Based Access Control (RBAC)

RBAC decouples the subject from the resource by introducing a **role** as an intermediate concept. Permissions are assigned to roles; users are assigned to roles.

```
Roles and permissions:
  viewer    → reports:read
  editor    → reports:read, reports:write
  admin     → reports:read, reports:write, reports:delete, users:manage

User assignments:
  alice  → viewer
  bob    → editor
  carol  → admin
```

The evaluation path is: `user → roles → permissions → decision`. To check if bob can write a report, the PDP looks up bob's roles (editor), looks up editor's permissions (read, write), and checks whether `reports:write` is in that set.

RBAC's signature property is **manageability at scale**. A 500-person company with 8 roles is far easier to govern than 500 individual ACL grant lists. Onboarding assigns a role; offboarding removes it; auditors can inspect what any role entails without scanning individual user records.

**Hierarchy.** Many RBAC implementations add role inheritance. `super-admin` inherits all permissions of `admin`, which inherits all of `editor`. This mirrors org-chart thinking but introduces a subtlety: if you grant `super-admin` access to a sensitive action by accident, every parent role inherits it silently.

**Where RBAC falls short.** Roles are coarse-grained. The rule "editors can write to their own department's reports, but not other departments'" cannot be expressed in pure RBAC without creating a role per department. If your authorization requirements have many intersecting dimensions (user attributes, resource attributes, time, location), role counts explode and RBAC becomes ACL in disguise.

---

### Model 3: Attribute-Based Access Control (ABAC)

ABAC evaluates policies that reference arbitrary **attributes** of three entities:

| Attribute type | Examples |
|---|---|
| **Subject attributes** | `user.department = "finance"`, `user.clearance = "SECRET"`, `user.mfa_verified = true` |
| **Resource attributes** | `document.classification = "CONFIDENTIAL"`, `document.owner_dept = "finance"` |
| **Environment attributes** | `request.time < 18:00`, `request.ip_in_corp_network = true`, `request.geo = "US"` |

A policy is a logical predicate over these attributes:

```
PERMIT  if  user.department == resource.owner_dept
        AND user.clearance >= resource.classification
        AND request.time BETWEEN 08:00 AND 20:00
        AND request.mfa_verified == true
```

The flexibility is enormous: the "can edit their own department's reports" rule that broke RBAC is trivial here. ABAC is the foundation of AWS IAM condition keys, Google Cloud IAM conditions, and XACML-based enterprise authorization systems.

**The cost:** ABAC policies are harder to reason about, test, and audit. When a user is denied access, diagnosing which condition failed requires tooling. Policy authoring requires discipline — wildcard attributes and nested logical conditions grow into an unmaintainable tangle. ABAC without a policy engine that supports simulation and testing is dangerous.

---

### Comparison at a Glance

| Dimension | ACL | RBAC | ABAC |
|---|---|---|---|
| Authorization unit | (subject, resource) pair | Role | Policy predicate |
| Scalability | Poor — O(users × resources) | Good — O(users + resources) | Good — O(policies) |
| Expressiveness | Low | Medium | Very high |
| Operational complexity | Low | Medium | High |
| Audit friendliness | Poor at scale | Good | Requires tooling |
| Best fit | Small teams, file systems | SaaS with stable roles | Regulatory, fine-grained, multi-dim |

---

### Least Privilege

Orthogonal to the model choice: every subject should receive exactly the minimum permissions required to do its job and nothing more. This principle limits blast radius when any account is compromised or behaves incorrectly. It is a design constraint, not a model.

---

## Build It / In Depth

### Implementing RBAC: From Schema to Check

**Step 1 — Schema (relational)**

```sql
CREATE TABLE roles (
    id   SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE permissions (
    id       SERIAL PRIMARY KEY,
    resource TEXT NOT NULL,
    action   TEXT NOT NULL,
    UNIQUE (resource, action)
);

CREATE TABLE role_permissions (
    role_id       INT REFERENCES roles(id),
    permission_id INT REFERENCES permissions(id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE user_roles (
    user_id INT NOT NULL,
    role_id INT REFERENCES roles(id),
    PRIMARY KEY (user_id, role_id)
);
```

**Step 2 — Seed data**

```sql
INSERT INTO roles (name) VALUES ('viewer'), ('editor'), ('admin');

INSERT INTO permissions (resource, action) VALUES
    ('reports', 'read'),
    ('reports', 'write'),
    ('reports', 'delete'),
    ('users',   'manage');

-- editor can read + write
INSERT INTO role_permissions
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'editor' AND p.resource = 'reports' AND p.action IN ('read', 'write');

-- admin gets everything
INSERT INTO role_permissions
SELECT r.id, p.id FROM roles r, permissions p
WHERE r.name = 'admin';
```

**Step 3 — The authorization check (Python / FastAPI style)**

```python
from functools import wraps
from db import get_user_permissions  # returns set[str] like {"reports:read", "reports:write"}

def require_permission(resource: str, action: str):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, request, **kwargs):
            user_id = request.state.user_id
            perms = await get_user_permissions(user_id)
            required = f"{resource}:{action}"
            if required not in perms:
                raise HTTPException(status_code=403, detail="Forbidden")
            return await fn(*args, request=request, **kwargs)
        return wrapper
    return decorator

# Usage
@router.delete("/reports/{report_id}")
@require_permission("reports", "delete")
async def delete_report(report_id: int, request: Request):
    ...
```

The `get_user_permissions` query joins `user_roles → role_permissions → permissions` — one round-trip to the database, result cacheable per user session.

---

### Adding a Tenant Dimension (RBAC → Scoped RBAC)

The moment you have a multi-tenant SaaS, pure RBAC needs a scope column:

```sql
CREATE TABLE user_roles (
    user_id   INT NOT NULL,
    role_id   INT REFERENCES roles(id),
    tenant_id INT NOT NULL,           -- scope
    PRIMARY KEY (user_id, role_id, tenant_id)
);
```

Now `alice` can be `editor` in tenant 42 and `viewer` in tenant 99. The check becomes:

```python
perms = await get_user_permissions(user_id, tenant_id=request.state.tenant_id)
```

This is sometimes called **organization-scoped RBAC** and is the model used by GitHub (org member vs. repo collaborator), Slack (workspace admin vs. channel member), and most enterprise SaaS products.

---

### ABAC Policy: OPA (Open Policy Agent)

For ABAC-style enforcement, Open Policy Agent evaluates Rego policies as a sidecar or library:

```rego
# policy.rego
package authz

default allow = false

allow {
    input.user.department == input.resource.owner_dept
    input.user.clearance >= input.resource.classification
    time.clock(input.now)[0] >= 8          # hour >= 8
    time.clock(input.now)[0] < 20          # hour < 20
}
```

Query from Python:

```python
import requests

def is_allowed(user, resource, now_iso):
    response = requests.post("http://opa:8181/v1/data/authz/allow", json={
        "input": {
            "user": user,
            "resource": resource,
            "now": now_iso,
        }
    })
    return response.json().get("result", False)
```

OPA decouples policy from code — the application does not change when business rules change, only the `.rego` file does.

---

## Use It

| Technology | Model used | Notes |
|---|---|---|
| **AWS IAM** | Hybrid RBAC + ABAC | IAM roles map to RBAC; condition keys (`aws:RequestedRegion`, `s3:prefix`) add ABAC dimensions |
| **Kubernetes RBAC** | Pure RBAC | `ClusterRole` / `Role` grant verbs (get, list, delete) on API resources; bound to subjects via `RoleBinding` |
| **Google Cloud IAM** | RBAC + ABAC conditions | Predefined roles are RBAC; IAM Conditions add time/resource-attribute policies |
| **PostgreSQL RLS** | ACL / ABAC hybrid | Row-Level Security policies are per-table predicates; use `current_user` and `app.current_tenant` GUC variables |
| **Open Policy Agent** | ABAC / custom | General-purpose policy engine; integrates with Kubernetes admission, Envoy, microservices |
| **Casbin** | Pluggable | Supports ACL, RBAC, ABAC via model files; embeds in Go, Java, Python, Node |
| **Auth0 / Okta FGA** | RBAC + ReBAC | Fine-Grained Authorization adds relationship-based access (Google Zanzibar model) |

**When to reach for each:**

- **ACL** — protecting individual files, S3 objects, or Git branches with explicit collaborators.
- **RBAC** — SaaS products with well-defined user tiers (free / pro / admin). Start here.
- **ABAC** — healthcare (HIPAA data access based on provider–patient relationship), financial data classification, government clearance systems, or any case where role count would exceed ~50 to stay manageable.
- **ReBAC (Relationship-Based AC)** — when authorization depends on graph relationships, e.g. "user can edit document if they are in the same team as the document owner." Google's Zanzibar paper is the canonical reference; Authzed/SpiceDB is a hosted implementation.

---

## Common Pitfalls

- **Privilege creep.** Users accumulate permissions over time as they change teams or temporarily need access to a project. No one revokes the old grants. Schedule quarterly access reviews and automate offboarding to strip roles immediately on departure.

- **Roles as users in disguise.** If you create a role per user (`alice_role`, `bob_role`) to work around RBAC's coarseness, you have re-invented ACL with extra steps. When roles approach user count, the model has collapsed — switch to ABAC or scoped RBAC.

- **Missing resource-level scoping.** RBAC at the action level (`can_read_invoices`) without restricting which invoices means a support agent can read any customer's invoice. Always pair action-level grants with resource ownership or tenant scoping.

- **Checking authorization in business logic instead of a PEP.** When every service method contains `if not user.has_permission(...)` scattered inline, authorization is untestable, inconsistent, and often wrong. Centralize into a middleware or decorator layer; the check should be invisible to business code.

- **Not logging denied access.** Every `DENY` decision is a security signal. A user hitting a 403 once is noise; the same user hitting it a hundred times across different tenant IDs in one minute is an enumeration attack. Structured logs of denied access feed anomaly detection — emit them with the subject, resource, action, and reason.

---

## Exercises

1. **Easy.** You are building a blogging platform. Users can be `author`, `editor`, or `admin`. Draw an RBAC permission matrix: list at least five actions (publish, draft, delete, manage-users, view-analytics) and mark which roles can perform each.

2. **Medium.** Your RBAC system has 30 roles. A new requirement arrives: "senior engineers in the EU region should be able to read audit logs only during business hours and only from corporate IPs." Model this. Explain why pure RBAC cannot express it efficiently and write an OPA Rego snippet that can.

3. **Hard.** Design the access control layer for a multi-tenant document-management service (similar to Google Docs) where: (a) users can share individual documents with specific other users at varying permission levels, (b) entire folders can be shared with a team, and (c) organization admins can see all documents in their org but not in other orgs. Identify which model(s) you would combine, sketch the data schema, and describe how the PDP would evaluate a request.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| **Authentication** | Same as authorization | Proves *who* you are (identity). Authorization proves *what* you can do. Conflating them is the single most common access control bug. |
| **RBAC** | A complex enterprise thing | Roles are just named groups of permissions. Users are assigned roles. The PDP checks if the user's roles grant the requested permission. |
| **ABAC** | A replacement for RBAC | A policy model that adds arbitrary attribute conditions on top of subject/resource/environment. Often layered *on top of* RBAC, not instead of it. |
| **ACL** | A modern access control model | One of the oldest models, predating RBAC. Scales poorly but is the right tool for direct per-object grants (e.g., S3 object ACLs, Unix file permissions). |
| **PDP / PEP** | An implementation detail | Fundamental architecture. The PEP intercepts requests; the PDP makes decisions. Splitting them is what makes access control auditable and testable. |
| **Least Privilege** | "Give users fewer permissions to be safe" | A design constraint: every identity (user, service account, IAM role) receives *exactly* the permissions required — no more, no less. Applied at provisioning time, not as an afterthought. |
| **Permission** | Same as a role | An atomic capability: `(resource, action)` pair such as `("invoices", "delete")`. Roles are *collections* of permissions. The distinction matters when you need fine-grained audit trails. |

---

## Further Reading

- [NIST RBAC Standard (SP 800-162)](https://csrc.nist.gov/publications/detail/sp/800-162/final) — The authoritative specification for RBAC, including hierarchical roles and the administrative model.
- [Google Zanzibar Paper (2019)](https://research.google/pubs/pub48190/) — The design behind Google's global authorization system; introduces the relationship-based model powering Google Drive, YouTube, and Maps sharing.
- [Open Policy Agent Documentation](https://www.openpolicyagent.org/docs/latest/) — The de-facto standard for ABAC in cloud-native systems; covers Rego language, Kubernetes admission, and Envoy integration.
- [OWASP Access Control Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Access_Control_Cheat_Sheet.html) — Practical checklist covering common misconfigurations, testing approaches, and enforcement patterns.
- [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html) — Concrete guidance on applying least privilege, role design, and SCPs in a production AWS environment; the patterns generalize to other cloud providers.
