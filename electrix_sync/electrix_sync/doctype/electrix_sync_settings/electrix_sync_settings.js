frappe.ui.form.on("Electrix Sync Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Simular clientes, direcciones y contactos"), async () => {
			const response = await frappe.call({
				method: "electrix_sync.api.master_data.preview_customer_import",
				freeze: true,
				freeze_message: __("Analizando staging…"),
			});
			const r = response.message || {};
			const row = (label, x = {}) => `<tr><td>${__(label)}</td><td>${x.create || 0}</td><td>${x.update || 0}</td><td>${x.unchanged || 0}</td><td>${x.conflict || 0}</td><td>${x.unlinked || 0}</td></tr>`;
			frappe.msgprint({
				title: __("Simulación STEL → ERPNext"),
				wide: true,
				message: `<p>${__("Simulación únicamente: no se ha creado ni modificado ningún documento ERPNext.")}</p><table class="table table-bordered"><thead><tr><th>${__("Recurso")}</th><th>${__("Crear")}</th><th>${__("Actualizar")}</th><th>${__("Sin cambios")}</th><th>${__("Conflictos")}</th><th>${__("Sin cliente")}</th></tr></thead><tbody>${row("Clientes", r.clients)}${row("Direcciones", r.addresses)}${row("Contactos", r.contacts)}${row("Total", r.totals)}</tbody></table>`,
			});
		}, __("STEL → ERPNext"));

		frm.add_custom_button(__("Sincronizar cambios esenciales"), async () => {
			const response = await frappe.call({
				method: "electrix_sync.api.bulk_sync.start_incremental_sync",
				freeze: true,
				freeze_message: __("Preparando lectura incremental…"),
			});
			const result = response.message || {};
			frappe.show_alert({
				message: __(`Sincronización incremental ${result.run} encolada (${result.resources} colecciones)`),
				indicator: "green",
			}, 8);
			frappe.set_route("Form", "STEL Bulk Sync Run", result.run);
		}, __("STEL Incremental"));

		frm.add_custom_button(__("Leer todos los registros de STEL"), () => {
			frappe.confirm(
				__("Se leerán las 56 colecciones de STEL Order en segundo plano. No se modificará ningún dato en STEL ni se crearán documentos contables. ¿Continuar?"),
				async () => {
					const response = await frappe.call({
						method: "electrix_sync.api.bulk_sync.start_bulk_snapshot",
						freeze: true,
						freeze_message: __("Preparando lectura masiva…"),
					});
					const result = response.message || {};
					frappe.show_alert({
						message: __(`Sincronización ${result.run} encolada (${result.resources} colecciones)`),
						indicator: "green",
					}, 8);
					frappe.set_route("Form", "STEL Bulk Sync Run", result.run);
				}
			);
		}, __("STEL Bulk Sync"));

		frm.add_custom_button(__("Ver ejecuciones"), () => {
			frappe.set_route("List", "STEL Bulk Sync Run");
		}, __("STEL Bulk Sync"));

		frm.add_custom_button(__("Ver staging"), () => {
			frappe.set_route("List", "STEL Raw Record");
		}, __("STEL Bulk Sync"));
	},
});
