import os
import time
import uuid
import azure.functions as func
from azure.data.tables import TableServiceClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="submit_feedback", methods=["POST"])
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:
    # Read from HTML <form>
    case_no = (req.form.get("case_no") or "").strip()
    is_resolved = (req.form.get("is_resolved") or "").strip()
    return_url = (req.form.get("return_url") or "").strip()

    # Prepare redirect back
    base_redirect = return_url or "https://zealous-mud-06328ed0f.1.azurestaticapps.net/"
    sep = "&" if "?" in base_redirect else "?"

    if not case_no or is_resolved not in ("Yes", "No"):
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
        )

    # Read connection string ONLY from environment
    conn = os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
    table_name = os.environ.get("FEEDBACK_TABLE", "CustomerFeedback")

    if not conn:
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
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

    # ✅ Success → redirect back to static page
    return func.HttpResponse(
        status_code=302,
        headers={"Location": f"{base_redirect}{sep}sent=1"}
    )
