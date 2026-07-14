frappe.ui.form.on("Event", {
	refresh(frm) {
		render_event_datetime_selectors(frm);
	},
	starts_on(frm) {
		setTimeout(() => render_event_datetime_selector(frm, "starts_on", __("Fecha de inicio"), __("Hora de inicio")), 0);
	},
	ends_on(frm) {
		setTimeout(() => render_event_datetime_selector(frm, "ends_on", __("Fecha de fin"), __("Hora de fin")), 0);
	},
});

function render_event_datetime_selectors(frm) {
	render_event_datetime_selector(frm, "starts_on", __("Fecha de inicio"), __("Hora de inicio"));
	render_event_datetime_selector(frm, "ends_on", __("Fecha de fin"), __("Hora de fin"));
}

function render_event_datetime_selector(frm, fieldname, dateLabel, timeLabel) {
	const control = frm.fields_dict[fieldname];
	if (!control?.$wrapper?.length) return;
	const rawValue = String(frm.doc[fieldname] || "");
	const date = rawValue.slice(0, 10);
	const time = round_event_time(rawValue.slice(11, 16));
	const disabled = frm.is_read_only() || Boolean(control.df.read_only);
	const options = event_time_options(time);
	const nativeInput = control.$wrapper.find(".control-input").first();
	nativeInput.hide();
	control.$wrapper.find(`.electrix-datetime-editor[data-fieldname="${fieldname}"]`).remove();
	const editor = $(`<div class="electrix-datetime-editor row" data-fieldname="${fieldname}">
		<div class="col-sm-6">
			<label class="control-label small text-muted">${dateLabel}</label>
			<input type="date" class="form-control electrix-event-date" value="${frappe.utils.escape_html(date)}" ${disabled ? "disabled" : ""}>
		</div>
		<div class="col-sm-6">
			<label class="control-label small text-muted">${timeLabel}</label>
			<select class="form-control electrix-event-time" ${disabled ? "disabled" : ""}>${options}</select>
		</div>
	</div>`);
	nativeInput.after(editor);
	editor.find("input,select").on("change", async () => {
		const selectedDate = editor.find(".electrix-event-date").val();
		const selectedTime = editor.find(".electrix-event-time").val();
		if (!selectedDate || !selectedTime) return;
		await frm.set_value(fieldname, `${selectedDate} ${selectedTime}:00`);
	});
}

function event_time_options(selected) {
	return Array.from({ length: 96 }, (_, index) => {
		const value = `${String(Math.floor(index / 4)).padStart(2, "0")}:${String((index % 4) * 15).padStart(2, "0")}`;
		return `<option value="${value}" ${value === selected ? "selected" : ""}>${value}</option>`;
	}).join("");
}

function round_event_time(value) {
	const parts = String(value || "08:00").split(":").map(Number);
	const rounded = Math.round(((parts[0] || 0) * 60 + (parts[1] || 0)) / 15) * 15;
	return `${String(Math.floor((rounded % 1440) / 60)).padStart(2, "0")}:${String(rounded % 60).padStart(2, "0")}`;
}
