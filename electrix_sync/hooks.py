app_name = "electrix_sync"
app_title = "Electrix Sync"
app_publisher = "Electrix"
app_description = "Sync STEL Order customers and leads into ERPNext"
app_email = "admin@example.com"
app_license = "MIT"

after_install = "electrix_sync.install.after_install"

scheduler_events = {
    "hourly": [
        "electrix_sync.api.sync.sync_all",
    ]
}

