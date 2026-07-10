from electrix_sync.api.sync import (
    get_catalog_names,
    get_incident_account_id,
    get_incident_address_id,
    get_incident_assignee_id,
    get_incident_description,
    get_incident_state_id,
    get_incident_subject,
    get_incident_type_id,
    get_issue_priority,
    get_issue_status,
    get_task_priority,
    get_task_status,
)


def test_incident_uses_only_stel_title_and_description():
    item = {
        "full-reference": "INC00260",
        "name": "Conectar fases a contactor",
        "description": "Faltan dos fases del extractor para conectar en el contactor.",
    }

    assert get_incident_subject(item, "5921195") == "Conectar fases a contactor"
    assert get_incident_description(item) == "Faltan dos fases del extractor para conectar en el contactor."


def test_incident_subject_falls_back_to_description_without_title():
    item = {"reference": "00001", "description": "TV Repairs"}

    assert get_incident_subject(item, "5") == "TV Repairs"


def test_incident_supports_stel_camel_case_relationships():
    item = {
        "accountId": 16115240,
        "addressId": 15252435,
        "assigneeId": 42,
        "stateId": 841823,
        "typeId": 2779,
    }

    assert get_incident_account_id(item) == 16115240
    assert get_incident_address_id(item) == 15252435
    assert get_incident_assignee_id(item) == 42
    assert get_incident_state_id(item) == 841823
    assert get_incident_type_id(item) == 2779


def test_incident_catalog_and_state_mappings():
    assert get_catalog_names([{"id": 841823, "name": "Pendiente"}]) == {"841823": "Pendiente"}
    assert get_issue_status({}, "Pendiente") == "Open"
    assert get_issue_status({}, "Atendida") == "Replied"
    assert get_issue_status({}, "Resuelta") == "Resolved"
    assert get_task_status({}, "Pendiente") == "Open"
    assert get_task_status({}, "Atendida") == "Working"
    assert get_task_status({}, "Resuelta") == "Completed"


def test_incident_priority_mappings():
    assert get_issue_priority({"priority": "VERYLOW"}) == "Low"
    assert get_issue_priority({"priority": "NORMAL"}) == "Medium"
    assert get_issue_priority({"priority": "VERYHIGH"}) == "High"
    assert get_task_priority({"priority": "VERYLOW"}) == "Low"
    assert get_task_priority({"priority": "NORMAL"}) == "Medium"
    assert get_task_priority({"priority": "VERYHIGH"}) == "Urgent"
