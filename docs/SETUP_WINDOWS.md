# Setup guide (Windows)

This takes about 30–45 minutes the first time. You only do it once.

---

## 1. Where the project lives

The project is already on your laptop at:

```
C:\Users\cac8p\OneDrive\Documents\Projects\database-to-dashboard\
```

Because it's in OneDrive, your code is backed up automatically. One rule comes with that: **anything big or "busy" stays outside OneDrive.** OneDrive tries to sync every tiny file and can lock files while you're using them. So this guide puts two things outside OneDrive:

- the Python virtual environment (step 4)
- later on, the DuckDB database file

GitHub becomes your real, versioned backup in step 7.

## 2. Install the three tools

| Tool | Where | Notes |
|---|---|---|
| **Python 3.12** | python.org → Downloads → Windows | On the **first installer screen, tick "Add python.exe to PATH"** before clicking Install. This is the #1 setup mistake. |
| **Git** | git-scm.com → Download for Windows | Click Next through all the defaults. |
| **VS Code** | code.visualstudio.com | Your code editor. After installing, open it, go to Extensions (left sidebar, four squares icon) and install **"Python"** by Microsoft. |

Check that Python worked: open **PowerShell** (Start menu → type PowerShell) and run:

```powershell
python --version
git --version
```

You should see `Python 3.12.x` and a git version. If `python` opens the Microsoft Store instead, try `py --version`. If that works, use `py` wherever this guide says `python`.

## 3. Open the project in VS Code

VS Code → **File → Open Folder** → pick `database-to-dashboard`. If it asks "Do you trust the authors?", click Yes (it's your folder).

Open a terminal inside VS Code: **Terminal → New Terminal**. A PowerShell panel opens at the bottom, already in your project folder.

## 4. Create a virtual environment

A virtual environment is a private, project-only copy of Python, so libraries for this project never clash with anything else on your computer. Industry standard.

We'll create it **outside OneDrive**, in a `.venvs` folder in your user profile:

```powershell
python -m venv $env:USERPROFILE\.venvs\database-to-dashboard
& $env:USERPROFILE\.venvs\database-to-dashboard\Scripts\Activate.ps1
```

Your prompt should now start with `(database-to-dashboard)`. You'll run that second line every time you open a new terminal for this project.

Then point VS Code at it so it remembers: press **Ctrl+Shift+P**, type **Python: Select Interpreter**, choose **Enter interpreter path...**, and paste:

```
C:\Users\cac8p\.venvs\database-to-dashboard\Scripts\python.exe
```

After this, VS Code usually activates the environment for you automatically in new terminals.

> **If you get a red error about "running scripts is disabled":** run this once, then retry the activate line:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
> ```
> It lets your own user account run local scripts like this one. It's a common one-time Windows setting for Python work.

## 5. Install the libraries and generate the data

```powershell
pip install -r requirements.txt
python generator\generate_saas_data.py
```

After about 30 seconds you'll see a summary like:

```
=== Ridgeline Intelligence: what was generated ===
  accounts            2,050 rows
  users              24,704 rows
  subscriptions       4,460 rows
  invoices            7,376 rows
  events            389,208 rows
  ...
```

Your raw "source systems" are now in `data\raw\saas\`.

## 6. Look around, but don't touch

Open a few CSVs (`crm\accounts.csv`, `billing\invoices.csv`, a couple of the `usage_events` files). Use VS Code's file preview, or Excel in read-only mode.

**Rule #1 of bronze data: never edit or re-save raw files.** Excel especially will silently change things (dates, leading zeros, `NA` values) if you save. All cleaning happens later, in SQL, where it's repeatable.

**Homework:** jot down every data problem you notice. Compare your list with `docs\DATA_QUALITY_ANSWER_KEY.md` afterwards. Interviewers love asking "what data quality issues did you find, and how did you handle them?"

## 7. Put it on GitHub

First, tell Git who you are (once per computer). In the VS Code terminal:

```powershell
git config --global user.name "Chris Cole"
git config --global user.email "you@example.com"
```

For the email, use the one on your GitHub account. Or, for privacy, use the `...@users.noreply.github.com` address shown at GitHub → Settings → Emails.

Then publish:

1. Click the **Source Control** icon in VS Code's left sidebar (the branching icon).
2. Click **Publish to GitHub**. If you see "Initialize Repository" instead, click that first, then the publish button.
3. Sign in to GitHub in the browser window that opens and allow VS Code.
4. Choose **Publish to GitHub public repository** and keep the name `database-to-dashboard`.
5. When it asks which files to include, keep everything selected. The `.gitignore` file already keeps the big CSVs and your virtual environment out.

Go to github.com/<your-username>/database-to-dashboard. You should see the README rendered nicely and **no CSV data files**. That's correct: anyone can regenerate the data with the script.

### The everyday Git loop (you'll do this a lot)

After you change files:
1. Source Control panel → type a short message describing what you did (e.g. `Add bronze load script`)
2. Click **Commit** (say Yes if it asks to stage all changes)
3. Click **Sync Changes** to push it to GitHub

A steady trail of small, clear commits is something hiring managers actually look at.

---

✅ **Done with setup?** Next step: load these files into a DuckDB database as your bronze layer.
