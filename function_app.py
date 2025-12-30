import os
import json
import time
import base64
import uuid
import logging
from urllib.parse import parse_qs

import azure.functions as func
import urllib.request

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

@app.route(route="submit_feedback", methods=["POST"])
def submit_feedback(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("submit_feedback (queue) called")

    # Read x-www-form-urlencoded
    body = req.get_body().decode("utf-8", errors="ignore")
    data = parse_qs(body)

    case_no = (data.get("case_no", [""])[0]).strip()
    is_resolved = (data.get("is_resolved", [""])[0]).strip()
    return_url = (data.get("return_url", [""])[0]).strip()

    default_return = os.environ.get("DEFAULT_RETURN_URL", "")
    base_redirect = return_url or default_return or "/"
    sep = "&" if "?" in base_redirect else "?"

    if not case_no or is_resolved not in ("Yes", "No"):
        return func.HttpResponse(status_code=302, headers={"Location": f"{base_redirect}{sep}sent=0"})

    account = os.environ.get("STORAGE_ACCOUNT_NAME")
    queue_name = os.environ.get("QUEUE_NAME")
    sas = os.environ.get("QUEUE_SAS")  # must start with "?"

    if not account or not queue_name or not sas:
        logging.error("Missing STORAGE_ACCOUNT_NAME / QUEUE_NAME / QUEUE_SAS")
        return func.HttpResponse(status_code=302, headers={"Location": f"{base_redirect}{sep}sent=0"})

    # Build message payload
    msg = {
        "id": uuid.uuid4().hex,
        "case_no": case_no,
        "is_resolved": is_resolved,
        "created_at": int(time.time()),
    }

    # Azure Queue requires message text base64 in XML body
    msg_text = base64.b64encode(json.dumps(msg, ensure_ascii=False).encode("utf-8")).decode("utf-8")

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

    try:
        req2 = urllib.request.Request(
            url,
            data=xml_body.encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req2, timeout=10) as resp:
            status = resp.status
            if status not in (201, 204):
                return func.HttpResponse(status_code=302, headers={"Location": f"{base_redirect}{sep}sent=0"})
    except Exception as e:
        logging.exception("Queue push exception: %s", e)
        return func.HttpResponse(status_code=302, headers={"Location": f"{base_redirect}{sep}sent=0"})
