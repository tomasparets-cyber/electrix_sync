from electrix_sync.install import create_custom_fields, create_unique_indexes


def execute():
    create_custom_fields()
    create_unique_indexes()

