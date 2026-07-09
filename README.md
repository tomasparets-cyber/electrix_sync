# Electrix Sync

Custom Frappe/ERPNext v15 app to sync STEL Order clients into ERPNext `Customer`, potential clients into ERPNext `Lead`, and STEL employees into ERPNext `Employee`/`User`.

## Scope

- Creates STEL custom fields on `Customer` and `Lead`.
- Creates STEL custom fields on `Address`.
- Creates STEL custom fields on `Employee` and `User`.
- Avoids duplicates by `custom_stel_id`.
- Reads STEL Order API data from configurable endpoints.
- Creates or updates ERPNext `Customer` records.
- Creates or updates ERPNext `Lead` records.
- Creates or updates the STEL `main-address` as an ERPNext billing `Address` linked to the `Customer`.
- Creates or updates secondary STEL addresses as custom ERPNext `Lugar` records, without linking them to `Customer`.
- Creates or updates STEL employees as ERPNext `Employee` records.
- Creates or updates ERPNext `User` records for STEL employees with a valid email, and links them from `Employee.user_id`.
- Stores sync errors and payloads in `Electrix Sync Log`.
- Does not sync contacts, incidents, events, quotations, invoices, or accounting documents.
- Does not copy STEL passwords into ERPNext. Users should set/reset their ERPNext password through ERPNext.

## STEL API Defaults

The defaults are based on STEL Order's OpenAPI document at:

`https://app.stelorder.com/app/api/openapi.json`

Use these values in `Electrix Sync Settings`:

- STEL Base URL: `https://app.stelorder.com`
- Auth Header Name: `APIKEY`
- Auth Header Prefix: leave empty
- Customers Endpoint: `/app/clients`
- Leads Endpoint: `/app/potentialClients`
- Addresses Endpoint: `/app/addresses`
- Employees Endpoint: `/app/employees`
- Page Limit: `500`
- Default Employee Date of Birth: `1900-01-01` unless you prefer another placeholder.

The OpenAPI document says list requests are limited to 100 records by default and can be increased to 500 using `limit`. This app paginates with `start` and `limit`.

## ERPNext Fields

The installer creates these custom fields on `Customer`, `Lead`, `Address`, `Employee`, `User`, and `Lugar` when that custom DocType exists:

- `custom_stel_id`: Data, unique
- `custom_stel_last_sync`: Datetime
- `custom_stel_sync_status`: Select (`Pending`, `Synced`, `Error`, `Skipped`)

## Local Bench Install

```bash
bench get-app /path/to/electrix_sync
bench --site your-site install-app electrix_sync
bench --site your-site migrate
```

Then open **Electrix Sync Settings**, enter the STEL API token, confirm the defaults, choose ERPNext defaults, and enable sync.

## Manual Sync

```bash
bench --site your-site execute electrix_sync.api.sync.sync_customers
bench --site your-site execute electrix_sync.api.sync.sync_leads
bench --site your-site execute electrix_sync.api.sync.sync_places
bench --site your-site execute electrix_sync.api.sync.sync_employees
bench --site your-site execute electrix_sync.api.sync.sync_all
```

## Frappe Cloud Install

1. Push this app to a Git repository.
2. In Frappe Cloud, open your bench.
3. Go to **Apps** and add a custom app from the Git repository URL.
4. Select the branch to install, normally `main`.
5. Deploy the bench.
6. Open the site, go to **Apps**, and install `electrix_sync` on the ERPNext site.
7. After install, open **Electrix Sync Settings** and configure the STEL token and ERPNext defaults.
8. Keep `Enabled` off until the first manual sync test succeeds.

## Git Repository Setup

From the app folder:

```bash
git init
git add .
git commit -m "Initial Electrix Sync app"
git branch -M main
git remote add origin git@github.com:YOUR_ORG/electrix_sync.git
git push -u origin main
```

For Frappe Cloud, make sure the repository is accessible to the Frappe Cloud GitHub app or use the repository URL method supported by your Frappe Cloud account.
