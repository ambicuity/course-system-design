# The Linux Cron Cheatsheet

> The classic Unix scheduler, still the simplest way to automate recurring tasks. A reference for the format, examples, and special strings.

**Type:** Reference
**Prerequisites:** Linux command line basics
**Time:** ~10 minutes

---

## The Problem

Every system needs scheduled tasks — backups, log rotation, cleanup jobs, report generation, batch processing. The Linux scheduler `cron` has done this since the 1970s. It is simple, ubiquitous, and still the right tool for many jobs.

This lesson is a focused reference: the cron format, common examples, special strings, and the special characters that change the meaning of fields. By the end, you should be able to read and write cron expressions confidently.

---

## The Concept

### What cron is

**Cron** is a time-based job scheduler. It runs commands or scripts at specified intervals, configured via a `crontab` (cron table) file. A daemon (`crond` on most systems) reads the crontab and executes jobs at the right times.

**Common uses:**

- System maintenance (log rotation, temp file cleanup)
- Backups (nightly database dumps, weekly snapshots)
- Reports (daily sales reports, weekly metrics)
- Automation (send reminder emails, run batch jobs)

---

### The cron format

A cron line has five time fields followed by a command:

```
   ┌───────────── minute (0 - 59)
   │  ┌─────────── hour (0 - 23)
   │  │  ┌───────── day of month (1 - 31)
   │  │  │  ┌─────── month (1 - 12)
   │  │  │  │  ┌───── day of week (0 - 6, Sunday=0)
   │  │  │  │  │
   *  *  *  *  *  command-to-execute
```

```
   Field         Allowed values    Special
   ─────────     ──────────────    ──────────────
   minute        0-59
   hour          0-23
   day of month  1-31
   month         1-12
   day of week   0-6 (Sun=0)
```

A field can be:

- A specific value: `5`
- A list: `1,3,5`
- A range: `1-5`
- A step: `*/5` (every 5)
- A wildcard: `*` (every)

---

### Cron format examples

```
   * * * * * cmd          Every minute
   0 * * * * cmd          Every hour, on the hour
   0 0 * * * cmd          Every day at midnight
   0 9 * * * cmd          Every day at 9:00 AM
   0 9 * * 1 cmd          Every Monday at 9:00 AM
   0 0 1 * * cmd          First day of every month at midnight
   0 0 1 1 * cmd          New Year's Day at midnight
   30 14 * * 5 cmd        Every Friday at 2:30 PM
   0 */2 * * * cmd        Every 2 hours on the hour
   */15 * * * * cmd       Every 15 minutes
   0 9-17 * * * cmd       Every hour from 9 AM to 5 PM
   0 9,12,15 * * * cmd    At 9 AM, 12 PM, and 3 PM every day
   0 0 * * 1-5 cmd        Weekdays at midnight (Mon-Fri)
   0 0 * * 6,0 cmd        Weekends at midnight (Sat-Sun)
```

---

### Special cron strings

For common schedules, cron supports shortcuts:

```
   @reboot     Run once at startup
   @yearly     Run once a year      (0 0 1 1 *)
   @annually   Same as @yearly
   @monthly    Run once a month     (0 0 1 * *)
   @weekly     Run once a week      (0 0 * * 0)
   @daily      Run once a day       (0 0 * * *)
   @midnight   Same as @daily
   @hourly     Run once an hour     (0 * * * *)
```

Example:

```cron
   @daily    /usr/local/bin/backup.sh
   @hourly   /usr/local/bin/cleanup.sh
   @reboot   /usr/local/bin/warm-cache.sh
```

---

### Special characters

Five characters change the meaning of a field:

```
   *    Asterisk — every value
        "Run at every minute" / "Run every hour" / etc.

   ,    Comma — list separator
        1,3,5 means "1, 3, or 5"

   -    Hyphen — range
        1-5 means "1, 2, 3, 4, 5"

   /    Slash — step values
        */5 means "every 5"
        0-30/5 means "0, 5, 10, 15, 20, 25, 30"

   ?    Question mark — no specific value (some implementations)
        Like * but used in some tools (Spring, Quartz) to distinguish
        "no specific value" between day-of-month and day-of-week
```

The slash is especially useful. `*/15` in the minute field means every 15 minutes. `0-30/10` means 0, 10, 20, 30.

---

### How to edit crontabs

```bash
# Edit your user's crontab
crontab -e

# List your user's crontab
crontab -l

# Remove your user's crontab
crontab -r

# Edit another user's crontab (root only)
sudo crontab -u username -e
```

The default editor is determined by `EDITOR` environment variable. Set it to your preferred editor:

```bash
export EDITOR=vim
crontab -e
```

---

### Common patterns

**Backup a database nightly:**

```cron
   0 2 * * * /usr/local/bin/backup-db.sh >> /var/log/backup.log 2>&1
```

**Rotate logs weekly:**

```cron
   0 0 * * 0 /usr/sbin/logrotate /etc/logrotate.conf
```

**Clean up temp files hourly:**

```cron
   0 * * * * find /tmp -type f -mtime +1 -delete
```

**Send a daily metrics report at 9 AM:**

```cron
   0 9 * * * /usr/local/bin/send-metrics-report.sh
```

**Run a job every 5 minutes during business hours:**

```cron
   */5 9-17 * * 1-5 /usr/local/bin/sync-data.sh
```

---

### Common pitfalls

**Cron does not load your shell environment.**

Cron jobs run with a minimal environment (`PATH=/usr/bin:/bin`). Commands that work in your shell may fail in cron because of missing environment variables, missing PATH entries, or missing shell functions.

Fix: explicitly set what you need.

```cron
   PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
   0 2 * * * /usr/local/bin/backup-db.sh
```

**Cron does not handle interactive programs.**

Cron has no terminal; commands requiring input will fail.

**Cron does not send output by default.**

If the job produces output, cron emails it to the user. If the user has no mail configured, the output is lost.

Best practice: redirect output to a log file.

```cron
   0 2 * * * /usr/local/bin/backup-db.sh >> /var/log/backup.log 2>&1
```

**Day-of-week and day-of-month are OR, not AND.**

In most cron implementations, if both day-of-month and day-of-week are specified (not `*`), the job runs when either matches. This is rarely what you want.

**Cron does not run jobs that were missed while the system was off.**

A nightly backup that was missed because the server was down at 2 AM does not run when the server starts back up. For resilient scheduling, use `anacron` or a job scheduler with catch-up semantics.

---

### Logging and debugging

Cron logs to the system log (`/var/log/syslog` on Debian/Ubuntu, `/var/log/cron` on CentOS/RHEL). Check there for job execution and errors.

For more detail, redirect job output to a file:

```cron
   0 2 * * * /usr/local/bin/backup-db.sh >> /var/log/backup.log 2>&1
```

Test the command manually before adding it to cron:

```bash
/usr/local/bin/backup-db.sh
```

If it works manually but fails in cron, the issue is usually the environment (PATH, variables, working directory). Add explicit setup at the top of the crontab.

---

### Cron vs. alternatives

For simple recurring tasks, cron is fine. For anything more complex, consider:

| Need | Use |
|---|---|
| Simple recurring task | cron |
| Job needs catch-up semantics | anacron, or a job queue |
| Job dependencies (B after A) | cron + lockfiles, or a workflow orchestrator |
| Multi-step workflow | Airflow, Prefect, Dagster |
| Distributed scheduling | Kubernetes CronJob, AWS EventBridge |
| Sub-minute scheduling | systemd timers, or a continuous loop with sleep |

**Modern alternatives:**

- **systemd timers** — more reliable than cron; handles missed jobs; integrates with systemd's logging
- **Kubernetes CronJob** — for workloads in K8s
- **AWS EventBridge / CloudWatch Events** — for cloud-native scheduling
- **Airflow / Prefect / Dagster** — for complex workflows with dependencies

---

## Build It / In Depth

### A production crontab

```cron
# Environment
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
MAILTO=ops@example.com

# Backup database nightly at 2 AM
0 2 * * * /usr/local/bin/backup-postgres.sh >> /var/log/backup.log 2>&1

# Rotate logs daily at midnight
0 0 * * * /usr/sbin/logrotate /etc/logrotate.d/app

# Clean up old temp files hourly
0 * * * * find /var/tmp -type f -mtime +7 -delete >> /var/log/cleanup.log 2>&1

# Send daily report at 8 AM
0 8 * * 1-5 /usr/local/bin/send-report.sh

# Refresh SSL certificates weekly (Sunday 3 AM)
0 3 * * 0 /usr/local/bin/renew-certs.sh

# Run health check every 5 minutes during business hours
*/5 9-17 * * 1-5 /usr/local/bin/health-check.sh
```

This crontab has:

- Explicit environment (PATH, SHELL, MAILTO)
- Standard backup, log rotation, cleanup jobs
- Business-day-specific schedules using day-of-week and hour ranges
- Output redirected to logs

---

### Common debugging commands

```bash
# List all cron jobs
crontab -l

# Check system logs for cron errors
grep CRON /var/log/syslog          # Debian/Ubuntu
grep CRON /var/log/cron             # CentOS/RHEL
journalctl -u cron                  # systemd

# Run the cron command manually
/usr/local/bin/backup-db.sh

# Test cron timing
# https://crontab.guru — paste a cron expression and see when it runs

# Check the cron daemon is running
systemctl status cron
```

---

## Use It

### When to use cron

| Use cron when… | Don't use cron when… |
|---|---|
| Simple recurring task at a known time | Complex dependencies between jobs |
| System-level maintenance (backups, cleanup) | Jobs that need monitoring and retries |
| The host is always on | The job is critical (use a workflow orchestrator) |
| Sub-minute granularity is not needed | You need sub-second scheduling |

### Modern alternatives by use case

| Use case | Modern tool |
|---|---|
| Single recurring task | systemd timer |
| Cron job in K8s | Kubernetes CronJob |
| Cloud-native scheduling | AWS EventBridge, GCP Cloud Scheduler |
| Multi-step workflow | Airflow, Prefect, Dagster |
| Distributed job queue | Celery, Sidekiq, BullMQ |
| Resilient scheduling | anacron, dead man's switch (Dead Man’s Snitch) |

---

## Common Pitfalls

- **Assuming cron loads your environment.** It does not. Set PATH, SHELL, and any required variables explicitly.

- **Forgetting to redirect output.** Without redirection, cron emails output (and loses it if no MTA is configured).

- **Day-of-month OR day-of-week semantics.** Specifying both is rarely what you want.

- **No monitoring of cron itself.** A failed cron job can go unnoticed for weeks. Add alerting (Dead Man's Snitch, monitoring checks).

- **Storing state in crontab.** Crontab is for scheduling, not state. Use files or a database for state.

- **No idempotency.** A cron job that runs twice (after a missed run + catch-up) should produce the same result. Make jobs idempotent.

- **Hardcoding paths.** Use absolute paths in cron jobs. The current directory is the user's home (or `/`), which is rarely what you want.

---

## Exercises

1. **Easy** — Write a cron expression that runs a script every day at 3:30 AM. Then write one that runs every 15 minutes between 8 AM and 6 PM on weekdays.

2. **Medium** — A backup script has been failing silently in production for two weeks. Walk through how you would diagnose and fix it.

3. **Hard** — Design a cron-based job system for a small company: daily database backup, hourly temp cleanup, weekly report, monthly metrics aggregation. Specify each job, its schedule, its failure handling, and its alerting.

---

## Key Terms

| Term | What people think | What it actually means |
|---|---|---|
| Cron | A scheduler | The Linux time-based job scheduler; runs commands at specified times via crontab entries |
| Crontab | The scheduler | A configuration file that lists jobs to run at scheduled times; managed by the `crontab` command |
| Cron expression | A schedule | The five time fields (minute, hour, day, month, day-of-week) that define when a cron job runs |
| @daily | Daily | A shortcut for "every day at midnight" (0 0 * * *) |
| */5 | Every 5 | A step expression; "every 5 minutes" / "every 5 hours" / etc. |
| systemd timer | Modern cron | A more reliable alternative to cron, with native logging, dependencies, and missed-job catch-up |
| Cron daemon | The scheduler | The `crond` process that reads crontabs and executes scheduled jobs |

---

## Further Reading

- **crontab.guru** — the indispensable cron expression tester: https://crontab.guru/
- **Linux man page for cron / crontab** — `man cron` and `man 5 crontab` on any Linux system
- **systemd.timer documentation** — the modern alternative: https://www.freedesktop.org/software/systemd/man/systemd.timer.html
- **Anacron** — for laptops and machines that are not always on: https://linux.die.net/man/8/anacron
- **Dead Man's Snitch** — cron job monitoring service: https://deadmanssnitch.com/