frappe.pages["planning-calendar"].on_page_load = function (wrapper) {
	new ElectrixPlanningCalendar(wrapper);
};

class ElectrixPlanningCalendar {
	constructor(wrapper) {
		this.page = frappe.ui.make_app_page({ parent: wrapper, title: __("Calendario de planificación"), single_column: true });
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
				cards.push(`<div class="pc-event" draggable="true" data-employee="${employee}" data-event="${event.name}" data-start="${event.starts_on}" data-end="${event.ends_on}" style="top:${top}px;height:${height}px;left:${2 + index * width}%;width:${width - 1}%">
					<strong>${frappe.utils.escape_html(event.subject || event.name)}</strong><span>${this.time(event.starts_on)}–${this.time(event.ends_on)}</span><small>${frappe.utils.escape_html(this.employeeById[employee].employee_name)}</small><i class="pc-resize" title="${__("Cambiar duración")}"></i>
				</div>`);
			});
		}
		return cards.join("");
	}

	bind() {
		this.page.main.find(".pc-event").on("dragstart", (event) => {
			if ($(event.target).hasClass("pc-resize")) { event.preventDefault(); return; }
			this.didManipulate = true;
			event.originalEvent.dataTransfer.effectAllowed = "move";
			event.originalEvent.dataTransfer.setData("text/plain", event.currentTarget.dataset.event);
			this.dragged = event.currentTarget;
		});
		this.page.main.find(".pc-day").on("dragover", (event) => { event.preventDefault(); event.currentTarget.classList.add("is-over"); event.originalEvent.dataTransfer.dropEffect = "move"; });
		this.page.main.find(".pc-day").on("dragleave", (event) => event.currentTarget.classList.remove("is-over"));
		this.page.main.find(".pc-day").on("drop", (event) => this.dropEvent(event));
		this.page.main.find(".pc-event").on("click", (event) => {
			if (this.didManipulate) { this.didManipulate = false; return; }
			frappe.set_route("Form", "Event", event.currentTarget.dataset.event);
		});
		this.page.main.find(".pc-resize").on("pointerdown", (event) => this.startResize(event));
	}

	async dropEvent(event) {
		event.preventDefault();
		event.currentTarget.classList.remove("is-over");
		const card = this.dragged;
		if (!card) return;
		const day = event.currentTarget.dataset.day;
		const rect = event.currentTarget.getBoundingClientRect();
		const minutes = this.snapMinutes((event.originalEvent.clientY - rect.top) / 0.8);
		const duration = Math.max(this.datetimeMinutes(card.dataset.end) - this.datetimeMinutes(card.dataset.start), 15);
		await this.persistTime(card.dataset.event, this.dateTime(day, minutes), this.dateTime(day, Math.min(minutes + duration, 1440)));
	}

	startResize(event) {
		event.preventDefault(); event.stopPropagation();
		const card = event.currentTarget.closest(".pc-event");
		const originY = event.originalEvent.clientY;
		const originHeight = card.getBoundingClientRect().height;
		this.didManipulate = true;
		const move = (pointerEvent) => {
			const height = Math.max(12, originHeight + pointerEvent.clientY - originY);
			card.style.height = `${height}px`;
		};
		const up = async () => {
			document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", up);
			const duration = Math.max(this.snapMinutes(parseFloat(card.style.height) / 0.8), 15);
			const start = card.dataset.start;
			await this.persistTime(card.dataset.event, start, this.addMinutes(start, duration));
		};
		document.addEventListener("pointermove", move); document.addEventListener("pointerup", up, { once: true });
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
	dateTime(day, minutes) {
		if (minutes >= 1440) return `${frappe.datetime.add_days(day, 1)} 00:00:00`;
		return `${day} ${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}:00`;
	}
	datetimeMinutes(value) { const date = new Date(String(value).replace(" ", "T")); return Math.round(date.getTime() / 60000); }
	addMinutes(value, minutes) { const date = new Date(String(value).replace(" ", "T")); date.setMinutes(date.getMinutes() + minutes); return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")} ${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}:00`; }
	minutes(value) { const time = (value || "").slice(11, 16).split(":").map(Number); return (time[0] || 0) * 60 + (time[1] || 0); }
	time(value) { return (value || "").slice(11, 16); }
	weekday(day) { return new Intl.DateTimeFormat(frappe.boot.lang || "es", { weekday: "short" }).format(new Date(`${day}T12:00:00`)); }
}
