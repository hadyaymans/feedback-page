import os
import json
import time
import uuid
import azure.functions as func
from azure.data.tables import TableServiceClient

app = func.FunctionApp()

TABLE_NAME = os.environ.get("FEEDBACK_TABLE", "CustomerFeedback")

def _json(status: int, payload: dict):
    return func.HttpResponse(
        body=json.dumps(payload, ensure_ascii=False),
        status_code=status,
        mimetype="application/json"
    )

@app.route(route="submit_feedback", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
    except Exception:
        return _json(400, {"ok": False, "error": "Invalid JSON"})

    case_no = (data.get("case_no") or "").strip()
    is_resolved = (data.get("is_resolved") or "").strip()

    if not case_no:
        return _json(400, {"ok": False, "error": "case_no is required"})
    if is_resolved not in ("Yes", "No"):
        return _json(400, {"ok": False, "error": "is_resolved must be Yes/No"})

    conn_str = os.environ.get("AZURE_STORAGE_CONNECTION_STRING=from your Storage Account → Access Keys")
    if not conn_str:
        return _json(500, {"ok": False, "error": "Missing AZURE_STORAGE_CONNECTION_STRING"})

    # Connect to Table Storage
    svc = TableServiceClient.from_connection_string(conn_str)
    table = svc.get_table_client(TABLE_NAME)
    table.create_table_if_not_exists()

    # RowKey should be unique
    row_key = f"{int(time.time())}-{uuid.uuid4().hex}"

    entity = {
        "PartitionKey": "feedback",
        "RowKey": row_key,
        "case_no": case_no,
        "is_resolved": is_resolved,
        "synced": False,
        "created_at": int(time.time())
    }

    table.create_entity(entity)

    return _json(200, {"ok": True})
