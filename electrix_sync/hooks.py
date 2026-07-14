app_name = "electrix_sync"
app_title = "Electrix Sync"
app_publisher = "Electrix"
app_description = "Sync STEL Order customers and leads into ERPNext"
app_email = "admin@example.com"
app_license = "MIT"

# Hide the comments composer and activity timeline in Desk forms while keeping
# the underlying audit history intact.
app_include_css = [
    "/assets/electrix_sync/css/desk.css",
    "/assets/electrix_sync/css/planning.css",
    "/assets/electrix_sync/css/planning_calendar.css",
]

doctype_js = {
    "Event": "public/js/event.js",
}

doc_events = {
    "Lugar": {
        "validate": "electrix_sync.api.locations.validate_lugar",
    },
    "Task": {
        "on_update": "electrix_sync.api.outbound_sync.enqueue_task",
    },
    "Event": {
        "validate": "electrix_sync.api.outbound_sync.normalize_event",
        "on_update": "electrix_sync.api.outbound_sync.enqueue_event",
        "on_trash": "electrix_sync.api.outbound_sync.delete_event",
    },
}

# Frappe v16 phase 1 deliberately only imports an immutable STEL snapshot into
# staging.  The legacy v15 installer and scheduler create ERPNext documents and
# depend on DocTypes that are no longer present in v16 (for example Lead Source),
# so they must not run on this branch.
after_install = "electrix_sync.v16_setup.ensure_staging_doctypes"
after_migrate = "electrix_sync.v16_setup.ensure_staging_doctypes"

scheduler_events = {
    "hourly": ["electrix_sync.api.sidebar.maintain_projects_customizations"],
    "cron": {
        "*/5 * * * *": ["electrix_sync.api.realtime_sync.sync_event_calendars"],
    }
}
