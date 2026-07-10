frappe.ui.form.on("STEL Bulk Sync Run", {
	refresh(frm) {
		if (["Queued", "Running"].includes(frm.doc.status)) {
			const total = frm.doc.resources_total || 1;
			const completed = frm.doc.resources_completed || 0;
			frm.dashboard.show_progress(
				__("Lectura de STEL"),
				Math.round((completed / total) * 100),
				`${completed}/${total} · ${frm.doc.current_resource || __("Preparando")}`
			);
			clearTimeout(frm.__bulk_refresh);
			frm.__bulk_refresh = setTimeout(() => frm.reload_doc(), 5000);
		}
	},

	onload(frm) {
		frappe.realtime.on("stel_bulk_progress", (data) => {
			if (data.run === frm.doc.name) frm.reload_doc();
		});
		frappe.realtime.on("stel_bulk_complete", (data) => {
			if (data.run === frm.doc.name) frm.reload_doc();
		});
	},
});
