"""
Ridgeline Intelligence: synthetic SaaS data generator
======================================================

Ridgeline Intelligence is a FICTIONAL company that sells market-intelligence
subscriptions (research portals, data feeds, APIs) to banks, asset managers,
corporates and consultancies. Every name, number and record produced by this
script is made up.

The script writes raw CSV files as if they were exported from three source
systems:

    data/raw/saas/
        crm/            accounts.csv, sales_reps.csv          (the CRM, e.g. Salesforce)
        billing/        products.csv, subscriptions.csv,
                        invoices.csv                          (the billing system)
        product_app/    users.csv,
                        usage_events/usage_events_YYYY_MM.csv (the product's event logs)
        reference/      fx_rates_monthly.csv                  (currency rates)

The business behaves realistically: accounts renew, expand, contract or churn
depending on a hidden "health" score; usage drops off before an account churns;
there is a price increase, a new product launch and Q4 sales seasonality.

The data is also messy ON PURPOSE, because cleaning it is the job of the
silver layer. See docs/DATA_QUALITY_ANSWER_KEY.md, but try to find the
problems yourself first.

Run it from the project root:
    python generator/generate_saas_data.py
Optional:
    python generator/generate_saas_data.py --seed 7 --accounts 3000
"""

from __future__ import annotations

import argparse
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

# ---------------------------------------------------------------------------
# 1. SETTINGS: change these to shape the business
# ---------------------------------------------------------------------------
CONFIG = {
    "seed": 42,
    "start_date": date(2023, 1, 1),      # first day of history
    "end_date": date(2026, 10, 31),      # "today" for the fictional company
    "n_accounts": 2000,                  # total real customer/prospect accounts
    "legacy_share": 0.22,                # share already customers before start_date
    "price_increase_date": date(2025, 1, 1),
    "price_increase_pct": 0.06,          # list prices rise 6% on that date
    "billing_migration_date": date(2025, 4, 1),   # new billing system goes live
    "platform_column_start": date(2025, 9, 1),    # event logs gain a new column
    "casing_bug": (date(2024, 6, 10), date(2024, 7, 22)),  # app release bug window
    "duplicate_account_rate": 0.025,     # CRM duplicate records
    "duplicate_event_rate": 0.012,       # events sent twice
    "late_event_rate": 0.03,             # events that arrive days late
    "usage_scale": 1.0,                  # turn usage volume up or down
}

PRODUCTS = [
    # id,       name,                      list $/seat/yr, launch date,       events/seat-wk, share of new deals
    ("PRD-01", "Market Research Portal",   2400, date(2016, 3, 1), 1.00, 0.45),
    ("PRD-02", "Company Data Feed",        6000, date(2017, 9, 1), 0.70, 0.20),
    ("PRD-03", "Credit Risk Analytics",    4800, date(2019, 1, 15), 0.85, 0.15),
    ("PRD-04", "Supply Chain Monitor",     3600, date(2024, 5, 1), 0.95, 0.00),  # new launch, cross-sell only
    ("PRD-05", "Pricing Benchmark API",    9000, date(2020, 6, 1), 1.40, 0.10),
    ("PRD-06", "Analyst Advisory Add-on",  1500, date(2018, 2, 1), 0.30, 0.10),
]

EVENT_TYPES = {
    "PRD-01": {"login": 0.30, "search": 0.35, "report_download": 0.20, "dashboard_view": 0.15},
    "PRD-02": {"login": 0.15, "api_call": 0.55, "export": 0.30},
    "PRD-03": {"login": 0.25, "search": 0.25, "dashboard_view": 0.30, "export": 0.20},
    "PRD-04": {"login": 0.25, "dashboard_view": 0.45, "search": 0.20, "export": 0.10},
    "PRD-05": {"api_call": 0.90, "login": 0.10},
    "PRD-06": {"login": 0.40, "report_download": 0.60},
}

REGIONS = {
    # region: (weight, [(country, currency), ...])
    "North America": (0.50, [("United States", "USD")] * 5 + [("Canada", "USD")]),
    "EMEA": (0.30, [("United Kingdom", "GBP")] * 3 + [("Germany", "EUR"), ("France", "EUR"), ("Netherlands", "EUR")]),
    "APAC": (0.14, [("Japan", "USD"), ("Singapore", "USD"), ("Australia", "USD")]),
    "LATAM": (0.06, [("Brazil", "USD"), ("Mexico", "USD")]),
}

INDUSTRIES = ["Banking", "Asset Management", "Insurance", "Private Equity", "Consulting",
              "Corporate - Manufacturing", "Corporate - Energy", "Technology", "Government", "Healthcare"]

SIZE_BANDS = {
    # band: (weight, typical starting seats low, high)
    "1-50": (0.18, 1, 4),
    "51-200": (0.27, 2, 8),
    "201-1000": (0.27, 4, 15),
    "1001-5000": (0.18, 8, 30),
    "5000+": (0.10, 15, 60),
}

JOB_TITLES = ["Analyst", "Senior Analyst", "Associate", "Vice President", "Director", "Portfolio Manager",
              "Credit Analyst", "Research Associate", "Data Engineer", "Procurement Manager",
              "Strategy Manager", "Economist", "Risk Manager", "Managing Director"]

FX_BASE = {"USD": 1.0, "GBP": 0.79, "EUR": 0.92}   # local currency per 1 USD (rough starting points)


# ---------------------------------------------------------------------------
# 2. Small helpers
# ---------------------------------------------------------------------------
def add_months(d: date, months: int) -> date:
    """Add calendar months to a date, clamping to the end of the month."""
    m = d.month - 1 + months
    y = d.year + m // 12
    m = m % 12 + 1
    last_day = [31, 29 if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)) else 28,
                31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last_day))


def list_price(product_row, on_date: date) -> float:
    price = product_row[2]
    if on_date >= CONFIG["price_increase_date"]:
        price *= 1 + CONFIG["price_increase_pct"]
    return price


def month_seasonality(month: int) -> float:
    """Usage is lighter in August and late December, a bit heavier in January."""
    return {1: 1.05, 8: 0.85, 12: 0.78}.get(month, 1.0)


def weighted_choice(rng: random.Random, options: dict):
    keys = list(options)
    return rng.choices(keys, weights=[options[k] for k in keys])[0]


# ---------------------------------------------------------------------------
# 3. The generator
# ---------------------------------------------------------------------------
class RidgelineGenerator:
    def __init__(self, seed: int, n_accounts: int):
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)
        self.fake = Faker(["en_US", "en_GB", "de_DE", "fr_FR"])
        Faker.seed(seed)
        self.n_accounts = n_accounts
        self.start = CONFIG["start_date"]
        self.end = CONFIG["end_date"]
        self.products = {p[0]: p for p in PRODUCTS}

        self.reps, self.accounts, self.users = [], [], []
        self.users_by_account: dict[str, list] = {}
        self.subscriptions, self.invoices = [], []
        self.usage_intervals = []   # (account_id, product_id, start, end, seats, health, churn_flag)
        self.events = []

        self._sub_counter = 0
        self._inv_counter = 0
        self._user_counter = 0

    # -- reference data -----------------------------------------------------
    def make_sales_reps(self):
        teams = ["New Business"] * 6 + ["Account Management"] * 6
        regions = ["North America", "North America", "EMEA", "EMEA", "APAC", "LATAM"] * 2
        for i in range(12):
            self.reps.append({
                "rep_id": f"REP-{i + 1:03d}",
                "rep_name": self.fake["en_US"].name(),
                "team": teams[i],
                "region": regions[i],
                "hire_date": self.fake.date_between(date(2016, 1, 1), date(2022, 6, 30)).isoformat(),
            })

    def rep_for(self, region: str, team: str) -> str:
        options = [r["rep_id"] for r in self.reps if r["region"] == region and r["team"] == team]
        return self.rng.choice(options or [r["rep_id"] for r in self.reps if r["team"] == team])

    # -- accounts -----------------------------------------------------------
    def _new_account_dates(self, n: int) -> list[date]:
        """Sample sign-up dates with growth over time and Q4 / quarter-end sales pushes."""
        days = (self.end - self.start).days
        candidates = [self.start + timedelta(days=d) for d in range(days)]
        weights = []
        for d in candidates:
            t = (d - self.start).days / days
            w = 1 + 0.35 * t                              # business is growing
            if d.month in (10, 11, 12):
                w *= 1.35                                  # Q4 budget flush
            if d.month in (3, 6, 9, 12) and d.day >= 15:
                w *= 1.25                                  # quarter-end push
            if d.weekday() >= 5:
                w *= 0.15                                  # few weekend sign-ups
            weights.append(w)
        return sorted(self.rng.choices(candidates, weights=weights, k=n))

    def make_accounts(self):
        n_legacy = int(self.n_accounts * CONFIG["legacy_share"])
        new_dates = self._new_account_dates(self.n_accounts - n_legacy)
        region_names = list(REGIONS)
        region_weights = [REGIONS[r][0] for r in region_names]
        used_names = set()

        for i in range(self.n_accounts):
            region = self.rng.choices(region_names, weights=region_weights)[0]
            country, currency = self.rng.choice(REGIONS[region][1])
            band = self.rng.choices(list(SIZE_BANDS), weights=[v[0] for v in SIZE_BANDS.values()])[0]

            name = self.fake.company()
            while name in used_names:
                name = self.fake.company()
            used_names.add(name)
            domain = "".join(ch for ch in name.lower() if ch.isalnum())[:22] + self.rng.choice([".com", ".com", ".io", ".co"])

            legacy = i < n_legacy
            created = (self.fake.date_between(date(2018, 1, 1), date(2022, 10, 31)) if legacy
                       else new_dates[i - n_legacy])

            self.accounts.append({
                "account_id": f"ACC-{i + 1:05d}",
                "company_name": name,
                "website": domain,
                "industry": self.rng.choice(INDUSTRIES),
                "region": region,
                "country": country,
                "employee_band": band,
                "created_at": created,
                "account_owner_rep_id": self.rep_for(region, "Account Management" if legacy else "New Business"),
                "acquisition_channel": self.rng.choices(
                    ["Outbound", "Inbound - Website", "Partner Referral", "Conference", "Free Trial"],
                    weights=[0.35, 0.25, 0.15, 0.10, 0.15])[0],
                # hidden attributes used for simulation only (not exported)
                "_legacy": legacy,
                "_currency": currency,
                "_health": float(self.np_rng.beta(4, 2)),
            })

    # -- users ----------------------------------------------------------------
    def ensure_users(self, account: dict, n_needed: int, as_of: date):
        """Make sure an account has at least n_needed active users by as_of."""
        acct_users = self.users_by_account.setdefault(account["account_id"], [])
        existing = [u for u in acct_users if u["_deactivated"] is None]
        domain = account["website"]
        for _ in range(max(0, n_needed - len(existing))):
            self._user_counter += 1
            first, last = self.fake.first_name(), self.fake.last_name()
            user = {
                "user_id": f"USR-{self._user_counter:06d}",
                "account_id": account["account_id"],
                "email": f"{first}.{last}@{domain}".lower().replace(" ", "").replace("'", ""),
                "first_name": first,
                "last_name": last,
                "job_title": self.rng.choice(JOB_TITLES),
                "created_at": as_of + timedelta(days=self.rng.randint(0, 20)),
                "_deactivated": None,
            }
            self.users.append(user)
            acct_users.append(user)

    def deactivate_users(self, account_id: str, on: date):
        for u in self.users_by_account.get(account_id, []):
            if u["_deactivated"] is None:
                u["_deactivated"] = on

    # -- subscriptions, invoices, usage intervals -----------------------------
    def _new_sub_id(self) -> str:
        self._sub_counter += 1
        return f"SUB-{self._sub_counter:06d}"

    def _invoice(self, sub: dict, account: dict, inv_date: date, amount: float):
        self._inv_counter += 1
        health = account["_health"]
        due = inv_date + timedelta(days=30)
        # unhealthy accounts pay later; a few invoices near "today" are still open
        delay = int(self.np_rng.gamma(2, 6 + 25 * (1 - health)))
        paid = inv_date + timedelta(days=delay)
        if paid > self.end:
            status, paid_date = ("overdue" if due < self.end else "open"), None
        else:
            status, paid_date = "paid", paid
        self.invoices.append({
            "invoice_id": self._inv_counter,             # formatted later (format changes at migration)
            "subscription_id": sub["subscription_id"],
            "account_id": account["account_id"],
            "invoice_date": inv_date,
            "due_date": due,
            "amount": round(amount, 2),
            "currency": sub["currency"],
            "status": status,
            "paid_date": paid_date,
        })

    def simulate_account(self, account: dict):
        rng = self.rng
        health = account["_health"]
        band = account["employee_band"]
        currency = account["_currency"]
        fx = FX_BASE[currency]
        quarterly_billing = rng.random() < 0.2

        # When does the first contract in our window start?
        if account["_legacy"]:
            start = self.fake.date_between(date(2022, 1, 3), date(2022, 12, 30))
        else:
            start = account["created_at"] + timedelta(days=rng.randint(14, 110))   # sales cycle
            if rng.random() < 0.12 or start > self.end:
                return   # stays a prospect in the CRM: no subscription ever signed

        # Initial product and seats
        launched = [p for p in PRODUCTS if p[3] <= start and p[5] > 0]
        first_product = rng.choices([p[0] for p in launched], weights=[p[5] for p in launched])[0]
        lo, hi = SIZE_BANDS[band][1], SIZE_BANDS[band][2]
        seats = {first_product: rng.randint(lo, hi)}
        discount = round(rng.choice([0, 0, 0.05, 0.10, 0.15, 0.20]), 2)
        prev_sub_ids: dict[str, str] = {}
        signed_by = account["account_owner_rep_id"]
        first_term = True

        while start <= self.end:
            term_months = 24 if (rng.random() < 0.15) else 12
            end = add_months(start, term_months) - timedelta(days=1)
            self.ensure_users(account, max(seats.values()) + rng.randint(0, 2), start)

            current_subs = {}
            for pid, n_seats in seats.items():
                acv = list_price(self.products[pid], start) * n_seats * (1 - discount) * fx
                sub = {
                    "subscription_id": self._new_sub_id(),
                    "account_id": account["account_id"],
                    "product_id": pid,
                    "contract_start_date": start,
                    "contract_end_date": end,
                    "term_months": term_months,
                    "seats": n_seats,
                    "discount_pct": discount,
                    "annual_contract_value": round(acv, 2),
                    "currency": currency,
                    "status": "active",
                    "previous_subscription_id": prev_sub_ids.get(pid),
                    "signed_by_rep_id": signed_by,
                    "booking_type": ("New" if first_term and pid == first_product
                                     else "Cross-sell" if pid not in prev_sub_ids else "Renewal"),
                }
                current_subs[pid] = sub
                self.subscriptions.append(sub)

                # invoices: annual upfront, or quarterly
                n_years = term_months // 12
                for y in range(n_years):
                    if quarterly_billing:
                        for q in range(4):
                            d = add_months(start, 12 * y + 3 * q)
                            if d <= self.end:
                                self._invoice(sub, account, d, acv / 4)
                    else:
                        d = add_months(start, 12 * y)
                        if d <= self.end:
                            self._invoice(sub, account, d, acv)

            # Contract still running at "today"? Then we're done.
            if end >= self.end:
                for pid, n in seats.items():
                    self.usage_intervals.append((account["account_id"], pid, start, self.end, n, health, False))
                break

            # Renewal decision. Health drifts a little each term.
            health = float(np.clip(health + self.np_rng.normal(0, 0.12), 0.02, 0.99))
            p_churn = 0.06 + 0.65 * (1 - health) ** 2.0
            churned = rng.random() < p_churn

            for pid, n in seats.items():
                self.usage_intervals.append((account["account_id"], pid, start, end, n, health, churned))

            if churned:
                for sub in current_subs.values():
                    sub["status"] = "churned"
                self.deactivate_users(account["account_id"], end)
                break

            # Renewed: adjust seats, maybe drop or add a product
            new_seats = {}
            for pid, n in seats.items():
                factor = math.exp(self.np_rng.normal(0.25 * (health - 0.55), 0.18))
                new_seats[pid] = max(1, round(n * factor))
            if len(new_seats) > 1 and rng.random() < 0.10 * (1 - health):
                dropped = rng.choice(list(new_seats))
                current_subs[dropped]["status"] = "cancelled"
                del new_seats[dropped]
            next_start = end + timedelta(days=1)
            if rng.random() < 0.28 * health:
                candidates = [p for p in PRODUCTS if p[0] not in new_seats and p[3] <= next_start]
                if candidates:
                    weights = [3 if p[0] == "PRD-04" else 1 for p in candidates]   # push the new product
                    add = rng.choices(candidates, weights=weights)[0][0]
                    new_seats[add] = max(1, round(max(new_seats.values()) * rng.uniform(0.3, 0.8)))

            for pid, sub in current_subs.items():
                if sub["status"] == "active":
                    sub["status"] = "renewed"
                    prev_sub_ids[pid] = sub["subscription_id"]
            if rng.random() < 0.15:
                discount = round(max(0, discount + rng.choice([-0.05, 0.05])), 2)
            seats = new_seats
            start = next_start
            first_term = False
            signed_by = account["account_owner_rep_id"] if account["_legacy"] else self.rep_for(account["region"], "Account Management")

    # -- usage events ----------------------------------------------------------
    def make_usage(self):
        users_by_account = self.users_by_account

        rows = []
        for account_id, pid, start, end, seats, health, churned in self.usage_intervals:
            # weekly buckets inside the window
            first = max(start, self.start)
            if first > end:
                continue
            n_weeks = (end - first).days // 7 + 1
            week_starts = [first + timedelta(weeks=w) for w in range(n_weeks)]
            lam = np.array([month_seasonality(d.month) for d in week_starts])
            lam *= self.products[pid][4] * (seats ** 0.65) * (0.25 + health) * CONFIG["usage_scale"] * 0.55

            # onboarding ramp for brand-new contracts
            ramp = min(6, n_weeks)
            if start >= self.start:
                lam[:ramp] *= np.linspace(0.35, 1.0, ramp)
            # usage fades in the last ~4 months before a churn
            if churned:
                fade = min(16, n_weeks)
                lam[-fade:] *= np.linspace(1.0, 0.15, fade)

            counts = self.np_rng.poisson(lam)
            candidate_users = users_by_account.get(account_id, [])
            event_types = EVENT_TYPES[pid]
            et_keys, et_w = list(event_types), list(event_types.values())

            for wk_start, c in zip(week_starts, counts):
                if c == 0:
                    continue
                active = [u for u in candidate_users if u["created_at"] <= wk_start + timedelta(days=6)
                          and (u["_deactivated"] is None or u["_deactivated"] >= wk_start)]
                if not active:
                    continue
                # a few "power users" generate most of the activity
                user_w = np.array([1.0 / (k + 1) ** 0.8 for k in range(len(active))])
                picks = self.np_rng.choice(len(active), size=c, p=user_w / user_w.sum())
                days = self.np_rng.choice(7, size=c, p=[0.19, 0.2, 0.2, 0.19, 0.16, 0.03, 0.03])
                hours = np.clip(self.np_rng.normal(13, 3, size=c), 0, 23.99)
                types = self.rng.choices(et_keys, weights=et_w, k=c)
                for k in range(c):
                    ts = datetime.combine(wk_start, datetime.min.time()) + timedelta(days=int(days[k]), hours=float(hours[k]))
                    if ts.date() > end or ts.date() > self.end:
                        continue
                    rows.append((account_id, active[picks[k]]["user_id"], pid, types[k], ts))

        self.events = pd.DataFrame(rows, columns=["account_id", "user_id", "product_id", "event_type", "event_ts"])
        self.events = self.events.sort_values("event_ts").reset_index(drop=True)
        self.events.insert(0, "event_id", [f"evt_{i:08d}" for i in range(1, len(self.events) + 1)])

    # -- run it all ------------------------------------------------------------
    def run(self):
        print("Creating sales reps and accounts...")
        self.make_sales_reps()
        self.make_accounts()
        print("Simulating contracts, renewals and churn...")
        for acc in self.accounts:
            self.simulate_account(acc)
        print("Generating product usage events (this takes a minute)...")
        self.make_usage()


# ---------------------------------------------------------------------------
# 4. Make the data messy (this is what real source systems look like)
# ---------------------------------------------------------------------------
def make_messy(gen: RidgelineGenerator):
    rng, np_rng, fake = gen.rng, gen.np_rng, gen.fake

    # ---- CRM accounts ------------------------------------------------------
    accounts = pd.DataFrame(gen.accounts)
    accounts = accounts[[c for c in accounts.columns if not c.startswith("_")]].copy()

    # Duplicate account records created by reps who didn't search first
    n_dupes = int(len(accounts) * CONFIG["duplicate_account_rate"])
    dupes = accounts.sample(n_dupes, random_state=CONFIG["seed"]).copy()
    def name_variant(n):
        return rng.choice([n.upper(), n + " Inc.", n + "  ", n.replace(" and ", " & "), n.replace(",", ""), n.lower()])
    def site_variant(s):
        return rng.choice(["www." + s, "https://" + s, "https://www." + s + "/", s.upper()])
    dupes["company_name"] = dupes["company_name"].map(name_variant)
    dupes["website"] = dupes["website"].map(site_variant)
    dupes["created_at"] = dupes["created_at"].map(lambda d: d + timedelta(days=rng.randint(30, 400)))
    dupes["account_id"] = [f"ACC-{len(accounts) + i + 1:05d}" for i in range(n_dupes)]
    accounts = pd.concat([accounts, dupes], ignore_index=True)

    region_variants = {"North America": ["NA", "N. America", "north america", "North America "],
                       "EMEA": ["Europe", "emea", "EMEA "], "APAC": ["Asia Pacific", "APAC "], "LATAM": ["Latin America"]}
    mask = np_rng.random(len(accounts)) < 0.08
    accounts.loc[mask, "region"] = accounts.loc[mask, "region"].map(lambda r: rng.choice(region_variants[r]))
    mask = (accounts["country"] == "United States") & (np_rng.random(len(accounts)) < 0.25)
    accounts.loc[mask, "country"] = [rng.choice(["USA", "US", "U.S."]) for _ in range(mask.sum())]
    accounts.loc[np_rng.random(len(accounts)) < 0.03, "industry"] = None
    accounts.loc[np_rng.random(len(accounts)) < 0.05, "employee_band"] = None
    accounts["created_at"] = pd.to_datetime(accounts["created_at"]) + pd.to_timedelta(
        np_rng.integers(8 * 3600, 19 * 3600, len(accounts)), unit="s")

    # ---- product app users ----------------------------------------------------
    users = pd.DataFrame(gen.users)
    users["status"] = np.where(users["_deactivated"].isna(), "active", "deactivated")
    users["deactivated_at"] = users["_deactivated"]
    users = users.drop(columns=["_deactivated"])
    mask = np_rng.random(len(users)) < 0.04
    users.loc[mask, "email"] = users.loc[mask, "email"].str.upper()
    users.loc[np_rng.random(len(users)) < 0.10, "job_title"] = None

    # ---- billing: products & subscriptions -----------------------------------
    products = pd.DataFrame([{
        "product_id": p[0], "product_name": p[1], "list_price_usd_per_seat": p[2],
        "launch_date": p[3].isoformat(),
    } for p in PRODUCTS])
    subs = pd.DataFrame(gen.subscriptions)

    # ---- billing: invoices (system migration changes the formats!) ------------
    inv = pd.DataFrame(gen.invoices).sort_values(["invoice_date", "invoice_id"]).reset_index(drop=True)
    migrated = inv["invoice_date"] >= CONFIG["billing_migration_date"]
    symbols = {"USD": "$", "GBP": "£", "EUR": "€"}

    # credit notes: ~1% of invoices get a partial refund line
    credits = inv[(inv["status"] == "paid") & (np_rng.random(len(inv)) < 0.01)].copy()
    credits["amount"] = -(credits["amount"] * np_rng.uniform(0.05, 0.3, len(credits))).round(2)
    credits["invoice_date"] = credits["invoice_date"].map(lambda d: d + timedelta(days=rng.randint(20, 90)))
    credits["status"] = "credit_note"
    credits["due_date"] = None
    credits["paid_date"] = credits["invoice_date"]
    credits = credits[credits["invoice_date"] <= gen.end]
    inv = pd.concat([inv, credits], ignore_index=True).sort_values("invoice_date").reset_index(drop=True)
    migrated = inv["invoice_date"] >= CONFIG["billing_migration_date"]

    def fmt_id(i, row_migrated, d):
        return f"inv-{d.year}-{i:06d}" if row_migrated else f"INV-{i:06d}"
    inv["invoice_id"] = [fmt_id(i + 1, m, d) for i, (m, d) in enumerate(zip(migrated, inv["invoice_date"]))]

    def fmt_date(d, m):
        if d is None or (isinstance(d, float) and math.isnan(d)) or pd.isna(d):
            return None
        return d.strftime("%m/%d/%Y") if m else d.isoformat()
    for col in ["invoice_date", "due_date", "paid_date"]:
        inv[col] = [fmt_date(d, m) for d, m in zip(inv[col], migrated)]
    inv["amount"] = [
        (f"{'-' if a < 0 else ''}{symbols[c]}{abs(a):,.2f}" if m else f"{a:.2f}")
        for a, c, m in zip(inv["amount"], inv["currency"], migrated)
    ]
    # the new system also resends a few invoices (exact duplicate rows)
    resend = inv[migrated & (np_rng.random(len(inv)) < 0.006)]
    inv = pd.concat([inv, resend], ignore_index=True)

    # ---- product app usage events --------------------------------------------
    ev = gen.events.copy()
    # API products are often called by service accounts: no user attached
    api_mask = (ev["product_id"] == "PRD-05") & (ev["event_type"] == "api_call") & (np_rng.random(len(ev)) < 0.35)
    ev.loc[api_mask, "user_id"] = None

    # an app release briefly logged event types in different casing
    lo, hi = CONFIG["casing_bug"]
    bug = (ev["event_ts"].dt.date >= lo) & (ev["event_ts"].dt.date <= hi)
    ev.loc[bug, "event_type"] = ev.loc[bug, "event_type"].map(
        lambda t: rng.choice([t.upper(), t.title(), t.replace("_", " ")]))

    # ingestion time: usually minutes later, sometimes days later (late-arriving data)
    lag_min = np_rng.exponential(4, len(ev))
    late = np_rng.random(len(ev)) < CONFIG["late_event_rate"]
    lag_min[late] = np_rng.uniform(2 * 1440, 10 * 1440, late.sum())
    ev["ingested_at"] = ev["event_ts"] + pd.to_timedelta(lag_min, unit="m")

    # events sent twice by the client
    dup = ev.sample(frac=CONFIG["duplicate_event_rate"], random_state=CONFIG["seed"])
    ev = pd.concat([ev, dup], ignore_index=True)

    # events that haven't arrived yet aren't in the logs
    ev = ev[ev["ingested_at"].dt.date <= gen.end].copy()

    # two timestamp styles depending on which service wrote the log
    iso_z = np_rng.random(len(ev)) < 0.4
    ev["event_timestamp"] = np.where(iso_z, ev["event_ts"].dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     ev["event_ts"].dt.strftime("%Y-%m-%d %H:%M:%S"))
    ev["ingested_at"] = ev["ingested_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    ev["platform"] = np.where(ev["event_type"].str.lower().str.contains("api"), "api",
                              np.where(np_rng.random(len(ev)) < 0.12, "mobile", "web"))
    ev = ev.drop(columns=["event_ts"])

    # ---- reference: monthly FX rates (replace with FRED data later!) ----------
    months = pd.date_range(gen.start.replace(day=1), gen.end, freq="MS")
    fx_rows = []
    for cur in ["GBP", "EUR"]:
        rate = FX_BASE[cur]
        for m in months:
            rate *= math.exp(np_rng.normal(0, 0.015))
            fx_rows.append({"month": m.date().isoformat(), "currency": cur, "units_per_usd": round(rate, 4)})
        # USD row for convenience
    for m in months:
        fx_rows.append({"month": m.date().isoformat(), "currency": "USD", "units_per_usd": 1.0})
    fx = pd.DataFrame(fx_rows)

    return {
        "accounts": accounts, "sales_reps": pd.DataFrame(gen.reps), "users": users,
        "products": products, "subscriptions": subs, "invoices": inv, "events": ev, "fx": fx,
    }


# ---------------------------------------------------------------------------
# 5. Write the files
# ---------------------------------------------------------------------------
def write_outputs(tables: dict, out_root: Path):
    crm, billing, app, ref = (out_root / "crm", out_root / "billing", out_root / "product_app", out_root / "reference")
    events_dir = app / "usage_events"
    for d in (crm, billing, app, events_dir, ref):
        d.mkdir(parents=True, exist_ok=True)
    for old in events_dir.glob("usage_events_*.csv"):
        old.unlink()

    tables["accounts"].to_csv(crm / "accounts.csv", index=False)
    tables["sales_reps"].to_csv(crm / "sales_reps.csv", index=False)
    tables["products"].to_csv(billing / "products.csv", index=False)
    tables["subscriptions"].to_csv(billing / "subscriptions.csv", index=False)
    tables["invoices"].to_csv(billing / "invoices.csv", index=False)
    tables["users"].to_csv(app / "users.csv", index=False)
    tables["fx"].to_csv(ref / "fx_rates_monthly.csv", index=False)

    # usage events land as one file per month, partitioned by when they ARRIVED
    ev = tables["events"]
    arrival_month = ev["ingested_at"].str[:7]
    cutoff = CONFIG["platform_column_start"].isoformat()[:7]
    base_cols = ["event_id", "account_id", "user_id", "product_id", "event_type", "event_timestamp", "ingested_at"]
    for month, chunk in ev.groupby(arrival_month):
        cols = base_cols + (["platform"] if month >= cutoff else [])   # schema change!
        chunk[cols].to_csv(events_dir / f"usage_events_{month.replace('-', '_')}.csv", index=False)


def print_summary(gen: RidgelineGenerator, tables: dict):
    subs = tables["subscriptions"]
    usd = {"USD": 1.0, "GBP": 1 / FX_BASE["GBP"], "EUR": 1 / FX_BASE["EUR"]}
    print("\n=== Ridgeline Intelligence: what was generated ===")
    for name in ["accounts", "sales_reps", "users", "products", "subscriptions", "invoices", "events"]:
        print(f"  {name:<14} {len(tables[name]):>10,} rows")
    print("\n  Approx. ARR (USD) at each year end, and logo churn that year:")
    for y in range(gen.start.year, gen.end.year + 1):
        snap = min(date(y, 12, 31), gen.end)
        live = subs[(subs["contract_start_date"] <= snap) & (subs["contract_end_date"] >= snap)]
        arr = (live["annual_contract_value"] * live["currency"].map(usd)).sum()
        ended = subs[(subs["status"] == "churned") & (pd.to_datetime(subs["contract_end_date"]).dt.year == y)]
        print(f"    {snap}  ARR ${arr / 1e6:6.1f}M   customers {live['account_id'].nunique():>5,}   churned logos {ended['account_id'].nunique():>4}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Generate Ridgeline Intelligence synthetic SaaS data.")
    parser.add_argument("--seed", type=int, default=CONFIG["seed"], help="random seed (same seed = same data)")
    parser.add_argument("--accounts", type=int, default=CONFIG["n_accounts"], help="number of accounts")
    parser.add_argument("--out", default=None, help="output folder (default: data/raw/saas)")
    args = parser.parse_args()
    CONFIG["seed"] = args.seed

    project_root = Path(__file__).resolve().parents[1]
    out_root = Path(args.out) if args.out else project_root / "data" / "raw" / "saas"

    gen = RidgelineGenerator(seed=args.seed, n_accounts=args.accounts)
    gen.run()
    print("Making the data realistically messy...")
    tables = make_messy(gen)
    write_outputs(tables, out_root)
    print_summary(gen, tables)
    print(f"Done. Raw files written to: {out_root}")


if __name__ == "__main__":
    main()
