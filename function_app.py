import os
import json
import time
import base64
import uuid
import logging
from urllib.parse import parse_qs
import urllib.request

import azure.functions as func

# Azure SDK imports
from azure.data.tables import TableClient
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceExistsError
from azure.identity import DefaultAzureCredential

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

# -------------------------------
# Table Storage dedup using Managed Identity
# -------------------------------
def mark_case_once(case_no: str) -> bool:
    """
    Returns True if case inserted for first time.
    Returns False if duplicate.
    """

    try:
        table_name = os.environ.get("TABLE_NAME")
        account = os.environ.get("STORAGE_ACCOUNT_NAME")

        if not table_name or not account:
            logging.error("Missing Table Storage env variables")
            return True  # allow request to proceed

        # Use Managed Identity credential
        credential = DefaultAzureCredential()
        table_url = f"https://{account}.table.core.windows.net/{table_name}"
        table = TableClient(endpoint=table_url, table_name=table_name, credential=credential)

        entity = {
            "PartitionKey": "feedback",
            "RowKey": case_no,
            "created_at": int(time.time())
        }

        table.create_entity(entity=entity)
        return True

    except ResourceExistsError:
        # Duplicate case_no
        return False

    except Exception as e:
        logging.exception("Table check failed: %s", e)
        return True  # allow queue push in case of Table failure


# -------------------------------
# Main Function
# -------------------------------
@app.route(route="submit_feedback", methods=["POST"])
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:

    logging.info("submit_feedback called")

    # Parse x-www-form-urlencoded body
    body = req.get_body().decode("utf-8", errors="ignore")
    data = parse_qs(body)

    case_no = (data.get("case_no", [""])[0]).strip()
    is_resolved = (data.get("is_resolved", [""])[0]).strip()
    return_url = (data.get("return_url", [""])[0]).strip()

    default_return = os.environ.get("DEFAULT_RETURN_URL", "")
    base_redirect = return_url or default_return or "/"
    sep = "&" if "?" in base_redirect else "?"

    # ---------------- Validation ----------------
    if not case_no or is_resolved not in ("Yes", "No"):
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
        )

    # ---------------- Dedup Check ----------------
    if not mark_case_once(case_no):
        logging.info("Duplicate feedback blocked for %s", case_no)
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0&duplicate=1"}
        )

    # ---------------- Queue Push ----------------
    account = os.environ.get("STORAGE_ACCOUNT_NAME")
    queue_name = os.environ.get("QUEUE_NAME")

    if not account or not queue_name:
        logging.error("Missing Queue env variables")
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
        )

    # Use Managed Identity for Queue SAS-free
    try:
        # Generate a SharedKeyAuth token for the Queue or use a library like azure-storage-queue
        # Here we keep simple using SAS if you still prefer
        queue_sas = os.environ.get("QUEUE_SAS", "")  # Optional if using Managed Identity for Queue
        url = f"https://{account}.queue.core.windows.net/{queue_name}/messages{queue_sas}"

        msg = {
            "id": uuid.uuid4().hex,
            "case_no": case_no,
            "is_resolved": is_resolved,
            "created_at": int(time.time()),
        }

        msg_text = base64.b64encode(json.dumps(msg, ensure_ascii=False).encode("utf-8")).decode("utf-8")

        xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<QueueMessage>
  <MessageText>{msg_text}</MessageText>
</QueueMessage>
"""

        headers = {
            "x-ms-version": "2017-11-09",
            "Content-Type": "application/xml"
        }

        req2 = urllib.request.Request(
            url,
            data=xml_body.encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req2, timeout=10) as resp:
            if resp.status not in (201, 204):
                raise Exception("Queue push failed")

        # ✅ Success
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=1"}
        )

    except Exception as e:
        logging.exception("Queue push failed: %s", e)
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
        )
