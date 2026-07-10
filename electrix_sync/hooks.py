app_name = "electrix_sync"
app_title = "Electrix Sync"
app_publisher = "Electrix"
app_description = "Sync STEL Order customers and leads into ERPNext"
app_email = "admin@example.com"
app_license = "MIT"

# Hide the comments composer and activity timeline in Desk forms while keeping
# the underlying audit history intact.
app_include_css = "/assets/electrix_sync/css/desk.css"

after_install = "electrix_sync.install.after_install"

scheduler_events = {
    "hourly": [
        "electrix_sync.api.sync.sync_all",
    ]
}
