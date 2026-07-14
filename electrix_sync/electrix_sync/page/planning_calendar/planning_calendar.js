frappe.pages["planning-calendar"].on_page_load = function (wrapper) {
	new ElectrixPlanningCalendar(wrapper);
};

class ElectrixPlanningCalendar {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Calendario de planificación"), single_column: true });
		this.ensureComponentStyles();
		this.startDate = this.startOfWeek(frappe.datetime.get_today());
		this.visibleEmployees = new Set();
		this.page.add_inner_button(__("Tabla"), () => frappe.set_route("planning"));
		this.page.add_inner_button(__("Anterior"), () => this.shift(-7));
		this.page.add_inner_button(__("Hoy"), () => { this.startDate = this.startOfWeek(frappe.datetime.get_today()); this.load(); });
		this.page.add_inner_button(__("Siguiente"), () => this.shift(7));
		this.addCalendarMenu();
		this.page.set_primary_action(__("Actualizar"), () => this.load(), "refresh");
		this.load();
	}

	ensureComponentStyles() {
		if (document.getElementById("electrix-planning-calendar-actions-style")) return;
		$(document.head).append(`<style id="electrix-planning-calendar-actions-style">
			.pc-event > button.pc-actions-toggle {
				position:absolute !important; inset:3px 3px auto auto !important;
				width:22px !important; min-width:22px !important; max-width:22px !important;
				height:22px !important; min-height:22px !important; margin:0 !important;
				padding:0 !important; display:flex !important; align-items:center !important;
				justify-content:center !important; border:0 !important; border-radius:4px !important;
				background:transparent !important; box-shadow:none !important; color:var(--text-muted) !important;
				font-size:14px !important; line-height:1 !important; opacity:.8; z-index:5;
			}
			.pc-event > button.pc-actions-toggle:hover,
			.pc-event > button.pc-actions-toggle:focus { opacity:1; background:var(--control-bg) !important; }
			body > .pc-event-actions-menu {
				position:fixed !important; display:block !important; z-index:1060 !important;
				min-width:160px !important; width:auto !important; margin:0 !important; padding:5px !important;
				border:1px solid var(--border-color) !important; border-radius:8px !important;
				background:var(--card-bg) !important; box-shadow:0 8px 24px rgba(0,0,0,.16) !important;
			}
			body > .pc-event-actions-menu > button {
				position:static !important; width:100% !important; min-width:0 !important; height:auto !important;
				display:flex !important; align-items:center !important; gap:8px !important;
				margin:0 !important; padding:7px 9px !important; border:0 !important; border-radius:5px !important;
				background:transparent !important; box-shadow:none !important; color:var(--text-color) !important;
				justify-content:flex-start !important; text-align:left !important;
			}
			body > .pc-event-actions-menu > button > span { flex:1; text-align:left !important; }
			body > .pc-event-actions-menu > button:hover,
			body > .pc-event-actions-menu > button:focus { background:var(--subtle-fg) !important; }
		</style>`);
	}

	addCalendarMenu() {
		this.calendarMenu = $(`<div class="dropdown pc-calendar-menu">
			<button class="btn btn-default btn-sm dropdown-toggle" data-toggle="dropdown" aria-expanded="false">
				${frappe.utils.icon("calendar", "sm")} ${__("Calendarios")} <span class="caret"></span>
			</button><div class="dropdown-menu dropdown-menu-right pc-calendar-options"></div>
		</div>`);
		this.page.inner_toolbar.append(this.calendarMenu);
		this.calendarMenu.on("click", ".dropdown-menu", (event) => event.stopPropagation());
	}

	startOfWeek(value) {
		const date = new Date(`${value}T12:00:00`);
		return frappe.datetime.add_days(value, -((date.getDay() + 6) % 7));
	}

	shift(days) { this.startDate = frappe.datetime.add_days(this.startDate, days); this.load(); }

	async load() {
		this.closeActionsMenu();
		this.page.main.html(`<div class="planning-loading">${__("Cargando calendario…")}</div>`);
		const response = await frappe.call({ method: "electrix_sync.api.planning.get_board", args: { start_date: this.startDate, days: 7 } });
		this.data = response.message;
		this.employees = this.data.employees.filter((row) => row.custom_stel_calendar_id);
		if (!this.filtersInitialized) {
			this.employees.forEach((row) => this.visibleEmployees.add(row.name));
			this.filtersInitialized = true;
		}
		this.renderCalendarMenu();
		this.render();
	}

	renderCalendarMenu() {
		const rows = this.employees.map((row) => `<label class="dropdown-item pc-calendar-option">
			<input type="checkbox" data-employee="${row.name}" ${this.visibleEmployees.has(row.name) ? "checked" : ""}>
			<span>${frappe.utils.escape_html(row.employee_name)}</span>
		</label>`).join("");
		this.calendarMenu.find(".pc-calendar-options").html(`<div class="pc-calendar-actions">
			<button class="btn btn-xs btn-default pc-select-all">${__("Todos")}</button>
			<button class="btn btn-xs btn-default pc-select-none">${__("Ninguno")}</button>
		</div>${rows || `<div class="dropdown-item text-muted">${__("No hay calendarios")}</div>`}`);
		this.calendarMenu.find("input").on("change", (event) => {
			const employee = event.currentTarget.dataset.employee;
			event.currentTarget.checked ? this.visibleEmployees.add(employee) : this.visibleEmployees.delete(employee);
			this.applyFilters();
		});
		this.calendarMenu.find(".pc-select-all").on("click", () => {
			this.employees.forEach((row) => this.visibleEmployees.add(row.name)); this.renderCalendarMenu(); this.applyFilters();
		});
		this.calendarMenu.find(".pc-select-none").on("click", () => {
			this.visibleEmployees.clear(); this.renderCalendarMenu(); this.applyFilters();
		});
	}

	render() {
		this.didManipulate = false;
		this.dragged = null;
		this.employeeById = Object.fromEntries(this.employees.map((row) => [row.name, row]));
		const headers = this.data.days.map((day) => `<div class="pc-day-header"><strong>${this.weekday(day)}</strong><span>${frappe.datetime.str_to_user(day)}</span></div>`).join("");
		const dayColumns = this.data.days.map((day) => `<div class="pc-day" data-day="${day}">${this.eventsForDay(day)}</div>`).join("");
		const hours = Array.from({ length: 24 }, (_, hour) => `<div class="pc-hour">${String(hour).padStart(2, "0")}:00</div>`).join("");
		this.page.main.html(`<section class="pc-calendar"><div class="pc-header"><div></div>${headers}</div><div class="pc-body"><div class="pc-hours">${hours}</div>${dayColumns}</div></section>`);
		this.bind();
		this.applyFilters();
	}

	eventsForDay(day) {
		const cards = [];
		for (const event of this.data.events.filter((row) => (row.starts_on || "").slice(0, 10) === day)) {
			const employees = event.assigned_employees || [];
			employees.forEach((employee, index) => {
				if (!this.employeeById[employee]) return;
				const start = this.minutes(event.starts_on);
				const end = Math.max(this.minutes(event.ends_on), start + 15);
				const top = start * 0.8;
				const height = Math.max((end - start) * 0.8, 20);
				const width = 94 / Math.max(employees.length, 1);
				cards.push(`<div class="pc-event" data-employee="${employee}" data-event="${event.name}" data-start="${event.starts_on}" data-end="${event.ends_on}" style="top:${top}px;height:${height}px;left:${2 + index * width}%;width:${width - 1}%">
					<button type="button" class="pc-actions-toggle" title="${__("Acciones")}" aria-label="${__("Acciones del evento")}"><span aria-hidden="true">▾</span></button><strong>${frappe.utils.escape_html(event.subject || event.name)}</strong><span>${this.time(event.starts_on)}–${this.time(event.ends_on)}</span><small>${frappe.utils.escape_html(this.employeeById[employee].employee_name)}</small><i class="pc-resize" title="${__("Cambiar duración")}"></i>
				</div>`);
			});
		}
		return cards.join("");
	}

	bind() {
		this.page.main.find(".pc-event").on("pointerdown", (event) => {
			if ($(event.target).closest(".pc-resize,.pc-actions-toggle").length) return;
			this.startMove(event);
		});
		this.page.main.find(".pc-event").on("click", (event) => {
			if (this.didManipulate) { this.didManipulate = false; return; }
			this.editEvent(event.currentTarget.dataset.event);
		});
		this.page.main.find(".pc-resize").on("pointerdown", (event) => this.startResize(event));
		this.page.main.find(".pc-actions-toggle").on("click", (event) => this.showActionsMenu(event));
	}

	startMove(event) {
		event.preventDefault();
		const card = event.currentTarget;
		const originX = event.originalEvent.clientX;
		const originY = event.originalEvent.clientY;
		const duration = Math.max(this.datetimeMinutes(card.dataset.end) - this.datetimeMinutes(card.dataset.start), 15);
		this.didManipulate = false;
		card.classList.add("is-moving");
		const move = (pointerEvent) => {
			if (Math.abs(pointerEvent.clientX - originX) + Math.abs(pointerEvent.clientY - originY) > 4) this.didManipulate = true;
			card.style.transform = `translate(${pointerEvent.clientX - originX}px, ${pointerEvent.clientY - originY}px)`;
		};
		const up = async (pointerEvent) => {
			document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up);
			card.classList.remove("is-moving"); card.style.transform = "";
			if (!this.didManipulate) return;
			const dayColumn = document.elementFromPoint(pointerEvent.clientX, pointerEvent.clientY)?.closest(".pc-day");
			if (!dayColumn) return;
			const rect = dayColumn.getBoundingClientRect();
			const minutes = this.snapMinutes((pointerEvent.clientY - rect.top) / 0.8);
			await this.persistTime(card.dataset.event, this.dateTime(dayColumn.dataset.day, minutes), this.dateTime(dayColumn.dataset.day, minutes + duration));
		};
		document.addEventListener("pointermove", move); document.addEventListener("pointerup", up, { once: true });
	}

	startResize(event) {
		event.preventDefault(); event.stopPropagation();
		const card = event.currentTarget.closest(".pc-event");
		const originY = event.originalEvent.clientY;
		const originalDuration = Math.max(this.datetimeMinutes(card.dataset.end) - this.datetimeMinutes(card.dataset.start), 15);
		this.didManipulate = true;
		const move = (pointerEvent) => {
			const duration = Math.max(15, this.snapDuration(originalDuration + (pointerEvent.clientY - originY) / 0.8));
			card.style.height = `${duration * 0.8}px`;
			card.dataset.previewDuration = duration;
		};
		const up = async () => {
			document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up);
			const duration = Number(card.dataset.previewDuration || originalDuration);
			const start = card.dataset.start;
			await this.persistTime(card.dataset.event, start, this.addMinutes(start, duration));
		};
		document.addEventListener("pointermove", move); document.addEventListener("pointerup", up, { once: true });
	}

	showActionsMenu(event) {
		event.preventDefault(); event.stopPropagation();
		this.closeActionsMenu();
		const button = event.currentTarget;
		const eventName = button.closest(".pc-event").dataset.event;
		const rect = button.getBoundingClientRect();
		this.actionsMenu = $(`<div class="pc-event-actions-menu" role="menu">
			<button type="button" data-action="duplicate" role="menuitem">${frappe.utils.icon("copy", "sm")}<span>${__("Duplicar")}</span></button>
			<button type="button" data-action="unplan" role="menuitem">${frappe.utils.icon("calendar", "sm")}<span>${__("Desprogramar")}</span></button>
		</div>`).appendTo(document.body);
		const width = this.actionsMenu.outerWidth();
		const height = this.actionsMenu.outerHeight();
		this.actionsMenu.css({
			left: `${Math.max(8, Math.min(window.innerWidth - width - 8, rect.right - width))}px`,
			top: `${Math.max(8, Math.min(window.innerHeight - height - 8, rect.bottom + 4))}px`,
		});
		this.actionsMenu.on("click", (menuEvent) => menuEvent.stopPropagation());
		this.actionsMenu.find('[data-action="duplicate"]').on("click", async () => {
			this.closeActionsMenu();
			await this.duplicateEvent(eventName);
		});
		this.actionsMenu.find('[data-action="unplan"]').on("click", async () => {
			this.closeActionsMenu();
			await this.unplanEvent(eventName);
		});
		setTimeout(() => $(document).one("click.pc-event-actions", () => this.closeActionsMenu()), 0);
	}

	closeActionsMenu() {
		$(document).off("click.pc-event-actions");
		this.actionsMenu?.remove();
		this.actionsMenu = null;
	}

	editEvent(eventName) {
		const source = this.data.events.find((row) => row.name === eventName);
		if (!source) return;
		const dialog = new frappe.ui.Dialog({
			title: __("Editar evento"),
			fields: [
				...this.eventFields(source),
				{ fieldtype: "Button", fieldname: "duplicate", label: __("Duplicar evento"), click: () => this.duplicateEvent(source.name, dialog) },
				{ fieldtype: "Button", fieldname: "unplan", label: __("Pasar a sin programar"), click: () => this.unplanEvent(source.name, dialog) },
			],
			primary_action_label: __("Guardar"),
			primary_action: async (values) => {
				delete values.duplicate;
				delete values.unplan;
				await frappe.call({
					method: "electrix_sync.api.planning.edit_planned_event",
					args: { event_name: source.name, ...this.eventPayload(values) },
					freeze: true,
					freeze_message: __("Actualizando ERPNext y STEL…"),
				});
				dialog.hide();
				await this.load();
			},
		});
		dialog.show();
	}

	eventFields(source) {
		const start = this.splitDateTime(source.starts_on);
		const end = this.splitDateTime(source.ends_on);
		const times = this.timeOptions();
		return [
			{ fieldtype: "Data", fieldname: "subject", label: __("Asunto"), reqd: 1, default: source.subject || "" },
			{ fieldtype: "Small Text", fieldname: "description", label: __("Descripción"), default: source.description || "" },
			{ fieldtype: "Data", fieldname: "location", label: __("Ubicación"), default: source.location || "" },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Date", fieldname: "start_date", label: __("Fecha de inicio"), reqd: 1, default: start.date },
			{ fieldtype: "Select", fieldname: "start_time", label: __("Hora de inicio"), reqd: 1, options: times, default: start.time },
			{ fieldtype: "Column Break" },
			{ fieldtype: "Date", fieldname: "end_date", label: __("Fecha de fin"), reqd: 1, default: end.date },
			{ fieldtype: "Select", fieldname: "end_time", label: __("Hora de fin"), reqd: 1, options: times, default: end.time },
			{ fieldtype: "Section Break" },
			{ fieldtype: "Select", fieldname: "event_category", label: __("Categoría"), options: "Event\nMeeting\nCall\nSent/Received Email\nOther", default: source.event_category || "Event" },
			{ fieldtype: "Select", fieldname: "status", label: __("Estado"), options: "Open\nClosed\nCancelled", default: source.status || "Open" },
			{ fieldtype: "Link", fieldname: "employee", label: __("Empleado"), options: "Employee", reqd: 1, default: source.custom_assigned_employee || (source.assigned_employees || [])[0] },
		];
	}

	eventPayload(values) {
		const payload = { ...values };
		payload.starts_on = `${payload.start_date} ${payload.start_time}:00`;
		payload.ends_on = `${payload.end_date} ${payload.end_time}:00`;
		delete payload.start_date; delete payload.start_time; delete payload.end_date; delete payload.end_time;
		return payload;
	}

	splitDateTime(value) {
		const text = String(value || `${frappe.datetime.get_today()} 08:00:00`);
		const minute = Math.round(Number(text.slice(14, 16) || 0) / 15) * 15;
		const hour = Number(text.slice(11, 13) || 0) + Math.floor(minute / 60);
		return { date: text.slice(0, 10), time: `${String(hour % 24).padStart(2, "0")}:${String(minute % 60).padStart(2, "0")}` };
	}

	timeOptions() {
		return Array.from({ length: 96 }, (_, index) => `${String(Math.floor(index / 4)).padStart(2, "0")}:${String((index % 4) * 15).padStart(2, "0")}`).join("\n");
	}

	async duplicateEvent(eventName, dialog) {
		await frappe.call({ method: "electrix_sync.api.planning.duplicate_event", args: { event_name: eventName }, freeze: true, freeze_message: __("Duplicando evento…") });
		dialog?.hide();
		frappe.show_alert({ message: __("Evento duplicado"), indicator: "green" });
		await this.load();
	}

	async unplanEvent(eventName, dialog) {
		await frappe.call({ method: "electrix_sync.api.planning.unplan_event", args: { event_name: eventName }, freeze: true, freeze_message: __("Desprogramando evento…") });
		dialog?.hide();
		frappe.show_alert({ message: __("Evento desprogramado"), indicator: "green" });
		await this.load();
	}

	async persistTime(eventName, startsOn, endsOn) {
		try {
			await frappe.call({ method: "electrix_sync.api.planning.resize_event", args: { event_name: eventName, starts_on: startsOn, ends_on: endsOn }, freeze: true, freeze_message: __("Actualizando ERPNext y STEL…") });
			frappe.show_alert({ message: __("Evento actualizado"), indicator: "green" });
			await this.load();
		} catch (error) {
			frappe.show_alert({ message: __("No se pudo actualizar el evento"), indicator: "red" });
			await this.load();
		}
	}

	applyFilters() {
		this.page.main.find(".pc-event").each((_, card) => { card.style.display = this.visibleEmployees.has(card.dataset.employee) ? "" : "none"; });
	}

	snapMinutes(value) { return Math.max(0, Math.min(1425, Math.round(value / 15) * 15)); }
	snapDuration(value) { return Math.round(value / 15) * 15; }
	dateTime(day, minutes) {
		const dayOffset = Math.floor(minutes / 1440);
		const minuteOfDay = ((minutes % 1440) + 1440) % 1440;
		return `${frappe.datetime.add_days(day, dayOffset)} ${String(Math.floor(minuteOfDay / 60)).padStart(2, "0")}:${String(minuteOfDay % 60).padStart(2, "0")}:00`;
	}
	datetimeMinutes(value) { const date = new Date(String(value).replace(" ", "T")); return Math.round(date.getTime() / 60000); }
	addMinutes(value, minutes) { const date = new Date(String(value).replace(" ", "T")); date.setMinutes(date.getMinutes() + minutes); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}:00`; }
	minutes(value) { const time = (value || "").slice(11, 16).split(":").map(Number); return (time[0] || 0) * 60 + (time[1] || 0); }
	time(value) { return (value || "").slice(11, 16); }
	weekday(day) { return new Intl.DateTimeFormat(frappe.boot.lang || "es", { weekday: "short" }).format(new Date(`${day}T12:00:00`)); }
}
