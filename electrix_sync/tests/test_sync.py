from electrix_sync.api.sync import get_incident_subject


def test_incident_subject_keeps_title_separate_from_description():
    item = {
        "full-reference": "INC00260",
        "name": "Conectar fases a contactor",
        "description": "Faltan dos fases del extractor para conectar en el contactor.",
    }

    assert get_incident_subject(item, "5921195") == "INC00260 - Conectar fases a contactor"


def test_incident_subject_falls_back_to_description_without_title():
    item = {"reference": "00001", "description": "TV Repairs"}

    assert get_incident_subject(item, "5") == "00001 - TV Repairs"
