app_name = "electrix_sync"
app_title = "Electrix Sync"
app_publisher = "Electrix"
app_description = "Sync STEL Order customers and leads into ERPNext"
app_email = "admin@example.com"
app_license = "MIT"

# Hide the comments composer and activity timeline in Desk forms while keeping
# the underlying audit history intact.
app_include_css = "/assets/electrix_sync/css/desk.css"

# Frappe v16 phase 1 deliberately only imports an immutable STEL snapshot into
# staging.  The legacy v15 installer and scheduler create ERPNext documents and
# depend on DocTypes that are no longer present in v16 (for example Lead Source),
# so they must not run on this branch.
after_install = "electrix_sync.v16_setup.ensure_staging_doctypes"
after_migrate = "electrix_sync.v16_setup.ensure_staging_doctypes"
