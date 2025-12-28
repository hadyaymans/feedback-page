import json
import os
import time
import uuid
import azure.functions as func
from azure.data.tables import TableServiceClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

def _cors():
    origin = os.environ.get("CORS_ORIGIN", "*")
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400",
    }

@app.route(route="submit_feedback", methods=["POST", "OPTIONS"])
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:
    # Preflight
    if req.method == "OPTIONS":
        return func.HttpResponse("", status_code=204, headers=_cors())

    try:
        data = req.get_json()
    except Exception:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Invalid JSON"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors()
        )

    case_no = (data.get("case_no") or "").strip()
    is_resolved = (data.get("is_resolved") or "").strip()

    if not case_no or is_resolved not in ("Yes", "No"):
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Invalid data"}),
            status_code=400,
            mimetype="application/json",
            headers=_cors()
        )

    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    table_name = os.environ.get("FEEDBACK_TABLE", "CustomerFeedback")

    if not conn:
        return func.HttpResponse(
            json.dumps({"ok": False, "error": "Missing AZURE_STORAGE_CONNECTION_STRING"}),
            status_code=500,
            mimetype="application/json",
            headers=_cors()
        )

    service = TableServiceClient.from_connection_string(conn)
    table = service.get_table_client(table_name)
    table.create_table_if_not_exists()

    table.create_entity({
        "PartitionKey": "feedback",
        "RowKey": f"{int(time.time())}-{uuid.uuid4().hex}",
        "case_no": case_no,
        "is_resolved": is_resolved,
        "synced": False,
        "created_at": int(time.time()),
    })

    return func.HttpResponse(
        json.dumps({"ok": True}),
        status_code=200,
        mimetype="application/json",
        headers=_cors()
    )
