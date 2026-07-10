frappe.ui.form.on("Electrix Sync Settings", {
	refresh(frm) {
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
