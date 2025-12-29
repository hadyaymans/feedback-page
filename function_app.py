import os
import time
import uuid
import logging
from urllib.parse import parse_qs

import azure.functions as func
from azure.data.tables import TableServiceClient

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="submit_feedback", methods=["POST"])
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("submit_feedback called")

    body = req.get_body().decode("utf-8", errors="ignore")
    data = parse_qs(body)

    case_no = (data.get("case_no", [""])[0]).strip()
    is_resolved = (data.get("is_resolved", [""])[0]).strip()
    return_url = (data.get("return_url", [""])[0]).strip()

    base_redirect = return_url or "https://zealous-mud-06328ed0f.1.azurestaticapps.net/"
    sep = "&" if "?" in base_redirect else "?"

    # Validate
    if not case_no or is_resolved not in ("Yes", "No"):
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
        )

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

    return func.HttpResponse(
        status_code=302,
        headers={"Location": f"{base_redirect}{sep}sent=1"}
    )