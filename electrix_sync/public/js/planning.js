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
		this.startDate = frappe.datetime.get_today();
		this.draggedEvent = null;
		this.buildActions();
		this.load();
	}

	buildActions() {
		this.page.add_inner_button(__("Sincronizar calendarios"), () => this.repairCalendars());
		this.page.add_inner_button(__("Anterior"), () => this.shiftWeek(-7));
		this.page.add_inner_button(__("Hoy"), () => {
			this.startDate = frappe.datetime.get_today();
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

	async load() {
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
				<strong>${frappe.datetime.str_to_user(day).slice(0, 5)}</strong>
				<span>${this.weekday(day)}</span>
			</div>`).join("");
		const rows = this.data.employees.map((employee) => this.employeeRow(employee, days)).join("");
		const unplanned = this.data.unplanned.map((event) => this.eventCard(event, true)).join("");

		this.page.main.html(`
			<div class="planning-shell">
				<section class="planning-board">
					<div class="planning-period">${frappe.datetime.str_to_user(days[0])} – ${frappe.datetime.str_to_user(days[days.length - 1])}</div>
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
				event.custom_assigned_employee === employee.name && (event.starts_on || "").slice(0, 10) === day
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
		const metadata = [event.custom_stel_event_type_name, event.custom_stel_event_state || "PENDING"].filter(Boolean).join(" · ");
		return `<article class="planning-event ${backlog ? "is-backlog" : ""}" draggable="true" data-event="${event.name}" data-search="${this.escape((event.subject || "").toLowerCase())}">
			<strong>${this.escape(event.subject || event.name)}</strong>
			<span>${this.escape(metadata)}${backlog ? "" : ` · ${this.timeLabel(event.starts_on, event.ends_on)}`}</span>
			<small>${duration}h</small>
		</article>`;
	}

	bind() {
		this.page.main.find(".planning-event").on("dragstart", (event) => {
			this.draggedEvent = event.currentTarget.dataset.event;
			event.originalEvent.dataTransfer.setData("text/plain", this.draggedEvent);
		});
		this.page.main.find(".planning-cell").on("dragover", (event) => {
			event.preventDefault();
			event.currentTarget.classList.add("is-over");
		}).on("dragleave", (event) => event.currentTarget.classList.remove("is-over"))
			.on("drop", (event) => this.drop(event));
		this.page.main.find(".planning-search").on("input", (event) => {
			const value = event.currentTarget.value.toLowerCase();
			this.page.main.find(".planning-backlog .planning-event").each((_, card) => {
				card.style.display = card.dataset.search.includes(value) ? "" : "none";
			});
		});
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

	timeLabel(start, end) {
		return `${(start || "").slice(11, 16)}–${(end || "").slice(11, 16)}`;
	}

	escape(value) {
		return frappe.utils.escape_html(String(value || ""));
	}
}
