frappe.pages["planning"].on_page_load = function (wrapper) {
	new ElectrixPlanning(wrapper);
};

class ElectrixPlanning {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Planificación"),
			single_column: true,
		});
		this.ensureComponentStyles();
		this.startDate = this.startOfWeek(frappe.datetime.get_today());
		this.draggedEvent = null;
		this.wasDragging = false;
		this.buildActions();
		this.load();
	}

	ensureComponentStyles() {
		if (document.getElementById("electrix-planning-table-actions-style")) return;
		$(document.head).append(`<style id="electrix-planning-table-actions-style">
			.planning-event > button.pc-actions-toggle {
				position:absolute !important; inset:3px 3px auto auto !important;
				width:22px !important; min-width:22px !important; max-width:22px !important;
				height:22px !important; min-height:22px !important; margin:0 !important;
				padding:0 !important; display:flex !important; align-items:center !important;
				justify-content:center !important; border:0 !important; border-radius:4px !important;
				background:transparent !important; box-shadow:none !important; color:var(--text-muted) !important;
				font-size:14px !important; line-height:1 !important; opacity:.8; z-index:5;
			}
			.planning-event > button.pc-actions-toggle:hover,
			.planning-event > button.pc-actions-toggle:focus { opacity:1; background:var(--control-bg) !important; }
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
			body > .pc-event-actions-menu > button[data-action="delete"] { color:var(--red-500) !important; }
			body > .pc-event-actions-menu > button > span { flex:1; text-align:left !important; }
			body > .pc-event-actions-menu > button:hover,
			body > .pc-event-actions-menu > button:focus { background:var(--subtle-fg) !important; }
		</style>`);
	}

	buildActions() {
		this.page.add_inner_button(__("Sincronizar calendarios"), () => this.repairCalendars());
		this.page.add_inner_button(__("Anterior"), () => this.shiftWeek(-7));
		this.page.add_inner_button(__("Hoy"), () => {
			this.startDate = this.startOfWeek(frappe.datetime.get_today());
			this.load();
		});
		this.page.add_inner_button(__("Siguiente"), () => this.shiftWeek(7));
		this.page.set_primary_action(__("Actualizar"), () => this.load(), "refresh");
	}

	async repairCalendars() {
		const response = await frappe.call({
			method: "electrix_sync.api.planning.repair_calendar_assignments",
			args: { refresh: 1 },
			freeze: true,
			freeze_message: __("Relacionando calendarios, empleados y eventos…"),
		});
		const result = response.message || {};
		const missing = (result.unmatched || []).map((row) => row.employee_name).join(", ");
		frappe.msgprint({
			title: __("Sincronización de calendarios"),
			message: `<p>${__("Calendarios leídos")}: ${result.calendars || 0}</p><p>${__("Empleados asociados")}: ${result.employees || 0}</p><p>${__("Eventos asociados")}: ${result.events || 0}</p>${missing ? `<p><strong>${__("Sin asociación")}:</strong> ${frappe.utils.escape_html(missing)}</p>` : ""}`,
			indicator: missing ? "orange" : "green",
		});
		await this.load();
	}

	shiftWeek(days) {
		this.startDate = frappe.datetime.add_days(this.startDate, days);
		this.load();
	}

	startOfWeek(value) {
		const date = new Date(`${value}T12:00:00`);
		const daysSinceMonday = (date.getDay() + 6) % 7;
		return frappe.datetime.add_days(value, -daysSinceMonday);
	}

	async load() {
		this.closeActionsMenu();
		this.page.main.html(`<div class="planning-loading">${__("Cargando planificación…")}</div>`);
		const response = await frappe.call({
			method: "electrix_sync.api.planning.get_board",
			args: { start_date: this.startDate, days: 7 },
			freeze: false,
		});
		this.data = response.message;
		this.render();
	}

	render() {
		const days = this.data.days;
		const dayHeaders = days.map((day) => `
			<div class="planning-day-header">
				<strong>${this.dayHeading(day)}</strong>
			</div>`).join("");
		const rows = this.data.employees.map((employee) => this.employeeRow(employee, days)).join("");
		const unplanned = this.data.unplanned.map((event) => this.eventCard(event, true)).join("");

		this.page.main.html(`
			<div class="planning-shell">
				<section class="planning-board">
					<div class="planning-period">${this.monthHeading(days[0])}</div>
					<div class="planning-grid planning-grid-header">
						<div class="planning-employee-header">${__("Empleado")}</div>${dayHeaders}
					</div>
					<div class="planning-rows">${rows || `<div class="planning-empty">${__("No hay empleados activos")}</div>`}</div>
				</section>
				<aside class="planning-backlog">
					<div class="planning-backlog-title"><strong>${__("Sin planificar")}</strong><span>${this.data.unplanned.length}</span></div>
					<input class="form-control planning-search" placeholder="${__("Buscar")}">
					<div class="planning-backlog-list">${unplanned || `<div class="planning-empty">${__("No hay eventos pendientes")}</div>`}</div>
				</aside>
			</div>`);
		this.bind();
	}

	employeeRow(employee, days) {
		const cells = days.map((day) => {
			const events = this.data.events.filter((event) =>
				(event.assigned_employees || [event.custom_assigned_employee]).includes(employee.name) && (event.starts_on || "").slice(0, 10) === day
			);
			return `<div class="planning-cell" data-employee="${employee.name}" data-date="${day}">
				${events.map((event) => this.eventCard(event, false)).join("")}
			</div>`;
		}).join("");
		return `<div class="planning-grid planning-row">
			<div class="planning-employee">
				<strong>${this.escape(employee.employee_name)}</strong>
				<span>${this.escape(employee.designation || "")}</span>
				${employee.custom_stel_calendar_id ? "" : `<em>${__("Sin calendario STEL")}</em>`}
			</div>${cells}
		</div>`;
	}

	eventCard(event, backlog) {
		const duration = Number(event.custom_estimated_duration || 1).toFixed(1).replace(".0", "");
		const metadata = [event.event_category, event.status || "Open"].filter(Boolean).join(" · ");
		return `<article class="planning-event ${backlog ? "is-backlog" : ""}" draggable="true" data-event="${event.name}" data-search="${this.escape((event.subject || "").toLowerCase())}">
			<button type="button" class="pc-actions-toggle" title="${__("Acciones")}" aria-label="${__("Acciones del evento")}" aria-expanded="false"><span aria-hidden="true">▾</span></button>
			<strong>${this.escape(event.subject || event.name)}</strong>
			<span>${this.escape(metadata)}${backlog ? "" : ` · ${this.timeLabel(event.starts_on, event.ends_on)}`}</span>
			<small>${duration}h</small>
		</article>`;
	}

	bind() {
		this.page.main.find(".planning-event").on("dragstart", (event) => {
			this.wasDragging = true;
			this.draggedEvent = event.currentTarget.dataset.event;
			event.originalEvent.dataTransfer.setData("text/plain", this.draggedEvent);
		}).on("dragend", () => setTimeout(() => { this.wasDragging = false; }, 50))
			.on("click", (event) => {
				if ($(event.target).closest(".pc-actions-toggle").length) return;
				if (!this.wasDragging) this.editEvent(event.currentTarget.dataset.event);
			});
		this.page.main.find(".pc-actions-toggle").on("click", (event) => this.showActionsMenu(event));
		this.page.main.find(".planning-cell").on("dragover", (event) => {
			event.preventDefault();
			event.currentTarget.classList.add("is-over");
		}).on("dragleave", (event) => event.currentTarget.classList.remove("is-over"))
			.on("drop", (event) => this.drop(event))
			.on("click", (event) => {
				if (event.target === event.currentTarget) this.createInCell(event.currentTarget);
			});
		this.page.main.find(".planning-backlog-list").on("dragover", (event) => {
			event.preventDefault();
			event.currentTarget.classList.add("is-over");
		}).on("dragleave", (event) => event.currentTarget.classList.remove("is-over"))
			.on("drop", (event) => this.dropToBacklog(event));
		this.page.main.find(".planning-search").on("input", (event) => {
			const value = event.currentTarget.value.toLowerCase();
			this.page.main.find(".planning-backlog .planning-event").each((_, card) => {
				card.style.display = card.dataset.search.includes(value) ? "" : "none";
			});
		});
	}

	showActionsMenu(event) {
		event.preventDefault(); event.stopPropagation();
		const button = event.currentTarget;
		const eventName = button.closest(".planning-event").dataset.event;
		if (this.actionsButton === button) {
			this.closeActionsMenu();
			return;
		}
		this.closeActionsMenu();
		this.actionsEventName = eventName;
		this.actionsButton = button;
		button.setAttribute("aria-expanded", "true");
		const rect = button.getBoundingClientRect();
		this.actionsMenu = $(`<div class="pc-event-actions-menu" role="menu">
			<button type="button" data-action="duplicate" role="menuitem">${frappe.utils.icon("copy", "sm")}<span>${__("Duplicar")}</span></button>
			<button type="button" data-action="unplan" role="menuitem">${frappe.utils.icon("calendar", "sm")}<span>${__("Desprogramar")}</span></button>
			<button type="button" data-action="delete" role="menuitem">${frappe.utils.icon("delete", "sm")}<span>${__("Eliminar")}</span></button>
		</div>`).appendTo(document.body);
		const width = this.actionsMenu.outerWidth();
		const height = this.actionsMenu.outerHeight();
		this.actionsMenu.css({
			left: `${Math.max(8, Math.min(window.innerWidth - width - 8, rect.right - width))}px`,
			top: `${Math.max(8, Math.min(window.innerHeight - height - 8, rect.bottom + 4))}px`,
		});
		this.actionsMenu.on("click", (menuEvent) => menuEvent.stopPropagation());
		this.actionsMenu.find('[data-action="duplicate"]').on("click", async () => { this.closeActionsMenu(); await this.duplicateEvent(eventName); });
		this.actionsMenu.find('[data-action="unplan"]').on("click", async () => { this.closeActionsMenu(); await this.unplanEvent(eventName); });
		this.actionsMenu.find('[data-action="delete"]').on("click", () => { this.closeActionsMenu(); this.deleteEvent(eventName); });
		setTimeout(() => $(document).one("click.pc-event-actions", () => this.closeActionsMenu()), 0);
	}

	closeActionsMenu() {
		$(document).off("click.pc-event-actions");
		this.actionsMenu?.remove();
		this.actionsButton?.setAttribute("aria-expanded", "false");
		this.actionsMenu = null;
		this.actionsButton = null;
		this.actionsEventName = null;
	}

	createInCell(cell) {
		const startsOn = `${cell.dataset.date} 08:00:00`;
		const endsOn = `${cell.dataset.date} 09:00:00`;
		const dialog = new frappe.ui.Dialog({
			title: __("Nuevo evento"),
			fields: this.eventFields({ starts_on: startsOn, ends_on: endsOn, status: "Open", assigned_employees: [cell.dataset.employee] }),
			primary_action_label: __("Crear y planificar"),
			primary_action: async (values) => {
				values = this.eventPayload(values);
				await frappe.call({
					method: "electrix_sync.api.planning.create_planned_event",
					args: { employee: cell.dataset.employee, ...values },
					freeze: true,
					freeze_message: __("Creando evento en ERPNext y STEL…"),
				});
				dialog.hide();
				await this.load();
			},
		});
		dialog.show();
	}

	editEvent(eventName) {
		const source = [...this.data.events, ...this.data.unplanned].find((row) => row.name === eventName);
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
				delete values.unplan;
				delete values.duplicate;
				values = this.eventPayload(values);
				await frappe.call({
					method: "electrix_sync.api.planning.edit_planned_event",
					args: { event_name: source.name, ...values },
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
			{ fieldtype: "Link", fieldname: "employee", label: __("Empleado"), options: "Employee", reqd: 1, default: source.custom_assigned_employee || (source.assigned_employees || [])[0], get_query: () => ({ filters: { status: "Active" } }) },
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
		let hour = Number(text.slice(11, 13) || 0) + Math.floor(minute / 60);
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
		await frappe.call({
			method: "electrix_sync.api.planning.unplan_event",
			args: { event_name: eventName },
			freeze: true,
			freeze_message: __("Pasando evento a sin programar…"),
		});
		dialog?.hide();
		await this.load();
	}

	deleteEvent(eventName, dialog) {
		frappe.confirm(__("¿Eliminar esta cita de ERPNext y STEL Order?"), async () => {
			await frappe.call({ method: "electrix_sync.api.planning.delete_planned_event", args: { event_name: eventName }, freeze: true, freeze_message: __("Eliminando evento…") });
			dialog?.hide();
			frappe.show_alert({ message: __("Evento eliminado"), indicator: "green" });
			await this.load();
		});
	}

	async dropToBacklog(event) {
		event.preventDefault();
		event.currentTarget.classList.remove("is-over");
		const eventName = event.originalEvent.dataTransfer.getData("text/plain") || this.draggedEvent;
		const source = this.data.events.find((row) => row.name === eventName);
		if (source) await this.unplanEvent(source.name);
	}

	async drop(event) {
		event.preventDefault();
		const cell = event.currentTarget;
		cell.classList.remove("is-over");
		const eventName = event.originalEvent.dataTransfer.getData("text/plain") || this.draggedEvent;
		const source = [...this.data.events, ...this.data.unplanned].find((row) => row.name === eventName);
		if (!source) return;
		const time = source.starts_on ? source.starts_on.slice(11, 19) : "08:00:00";
		const startsOn = `${cell.dataset.date} ${time}`;
		try {
			await frappe.call({
				method: "electrix_sync.api.planning.plan_event",
				args: { event_name: eventName, employee: cell.dataset.employee, starts_on: startsOn },
				freeze: true,
				freeze_message: __("Actualizando ERPNext y STEL…"),
			});
			frappe.show_alert({ message: __("Evento planificado"), indicator: "green" });
			await this.load();
		} catch (error) {
			frappe.show_alert({ message: __("No se pudo planificar el evento"), indicator: "red" });
		}
	}

	weekday(day) {
		return new Intl.DateTimeFormat(frappe.boot.lang || "es", { weekday: "short" }).format(new Date(`${day}T12:00:00`));
	}

	dayHeading(day) {
		const date = new Date(`${day}T12:00:00`);
		const value = new Intl.DateTimeFormat(frappe.boot.lang || "es", { weekday: "short", day: "numeric" }).format(date).replace(/[.,]/g, "");
		return value.charAt(0).toUpperCase() + value.slice(1);
	}

	monthHeading(day) {
		const date = new Date(`${day}T12:00:00`);
		const month = new Intl.DateTimeFormat(frappe.boot.lang || "es", { month: "long" }).format(date);
		return `${month.charAt(0).toUpperCase() + month.slice(1)} ${date.getFullYear()}`;
	}

	timeLabel(start, end) {
		return `${(start || "").slice(11, 16)}–${(end || "").slice(11, 16)}`;
	}

	escape(value) {
		return frappe.utils.escape_html(String(value || ""));
	}
}
