import json
import time
import uuid
import os
import azure.functions as func
from azure.data.tables import TableServiceClient

def main(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except Exception:
        return func.HttpResponse("Invalid JSON", status_code=400)

    case_no = (data.get("case_no") or "").strip()
    is_resolved = (data.get("is_resolved") or "").strip()

    if not case_no or is_resolved not in ("Yes", "No"):
        return func.HttpResponse("Invalid data", status_code=400)

    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    table_name = os.environ.get("FEEDBACK_TABLE", "CustomerFeedback")

    service = TableServiceClient.from_connection_string(conn)
    table = service.get_table_client(table_name)
    table.create_table_if_not_exists()

    entity = {
        "PartitionKey": "feedback",
        "RowKey": f"{int(time.time())}-{uuid.uuid4().hex}",
        "case_no": case_no,
        "is_resolved": is_resolved,
        "synced": False,
        "created_at": int(time.time())
    }

    table.create_entity(entity)

    return func.HttpResponse(
        json.dumps({"ok": True}),
        mimetype="application/json"
    )
