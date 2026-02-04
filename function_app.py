import os
import json
import time
import base64
import uuid
import logging
from urllib.parse import parse_qs
import urllib.request

import azure.functions as func


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


# ---------------------------------------------------
# Prevent duplicate feedback using Table Storage
# ---------------------------------------------------
# def mark_case_once(case_no: str) -> bool:

#     try:
#         from azure.data.tables import TableClient
#         from azure.core.exceptions import ResourceExistsError

#         account = os.environ.get("STORAGE_ACCOUNT_NAME")
#         table_name = os.environ.get("TABLE_NAME")
#         sas = os.environ.get("TABLE_SAS")

#         if not account or not table_name or not sas:
#             logging.error("Table env variables missing")
#             return True

#         table_url = f"https://{account}.table.core.windows.net/{table_name}{sas}"
#         table = TableClient.from_table_url(table_url)

#         entity = {
#             "PartitionKey": "feedback",
#             "RowKey": case_no,
#             "created_at": int(time.time())
#         }

#         table.create_entity(entity=entity)
#         return True

#     except ResourceExistsError:
#         return False

#     except Exception as e:
#         logging.exception("Table check failed: %s", e)
#         return True

# ---------------------------------------------------
# Main Function
# ---------------------------------------------------
@app.route(route="submit_feedback", methods=["POST"])
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:

    logging.info("submit_feedback (queue) called")

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

    # ---------------- Duplicate Protection ----------------
    # if not mark_case_once(case_no):
    #     logging.info("Duplicate feedback blocked for %s", case_no)
    #     return func.HttpResponse(
    #         status_code=302,
    #         headers={"Location": f"{base_redirect}{sep}sent=0&duplicate=1"}
    #     )

    # ---------------- Queue Config ----------------
    account = os.environ.get("STORAGE_ACCOUNT_NAME")
    queue_name = os.environ.get("QUEUE_NAME")
    sas = os.environ.get("QUEUE_SAS")

    if not account or not queue_name or not sas:
        logging.error("Missing queue environment variables")
        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
        )

    # ---------------- Build Queue Message ----------------
    msg = {
        "id": uuid.uuid4().hex,
        "case_no": case_no,
        "is_resolved": is_resolved,
        "created_at": int(time.time()),
    }

    msg_text = base64.b64encode(
        json.dumps(msg, ensure_ascii=False).encode("utf-8")
    ).decode("utf-8")

    url = f"https://{account}.queue.core.windows.net/{queue_name}/messages{sas}"

    headers = {
        "x-ms-version": "2017-11-09",
        "Content-Type": "application/xml"
    }

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<QueueMessage>
  <MessageText>{msg_text}</MessageText>
</QueueMessage>
"""

    # ---------------- Send To Queue ----------------
    try:
        req2 = urllib.request.Request(
            url,
            data=xml_body.encode("utf-8"),
            headers=headers,
            method="POST"
        )

        with urllib.request.urlopen(req2, timeout=10) as resp:
            if resp.status not in (201, 204):
                raise Exception("Queue push failed")

        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=1"}
        )

    except Exception as e:
        logging.exception("Queue push exception: %s", e)

        return func.HttpResponse(
            status_code=302,
            headers={"Location": f"{base_redirect}{sep}sent=0"}
        )
