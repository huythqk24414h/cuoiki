"""Recover missing SSI collectors without interrupting active captures."""
import json
import os
from datetime import datetime, time, timedelta, timezone
from urllib.request import Request, urlopen

VN = timezone(timedelta(hours=7))


def github(path, body=None):
    request = Request("https://api.github.com/repos/"+os.environ["GITHUB_REPOSITORY"]+path,
                      data=json.dumps(body).encode() if body is not None else None,
                      headers={"Authorization":"Bearer "+os.environ["GITHUB_TOKEN"],
                               "Accept":"application/vnd.github+json", "Content-Type":"application/json"})
    with urlopen(request, timeout=20) as response:
        data = response.read()
    return json.loads(data) if data else None


def active(workflow, session=None):
    for state in ("in_progress", "queued"):
        runs = github(f"/actions/workflows/{workflow}/runs?status={state}&per_page=100")["workflow_runs"]
        for run in runs:
            if session is None or state == "queued":
                return True
            jobs = github(f"/actions/runs/{run['id']}/jobs?per_page=100")["jobs"]
            if any(job["name"] == session and job["status"] in ("in_progress", "queued") for job in jobs):
                return True
    return False


def reconcile(now, *, charts_only=False):
    if now.weekday() >= 5:
        return []
    clock = now.time()
    session = "morning" if time(7) <= clock < time(11,25) else "afternoon" if time(11,35) <= clock < time(14,40) else None
    jobs = []
    if session and not charts_only:
        jobs.append(("ssi-live-capture.yml", {"session":session}, session))
    if time(9,17) <= clock < time(14,48):
        jobs.extend([("ssi-intraday.yml", {"follow_session":True}, None),
                     ("ssi-intraday-index-board.yml", {}, None)])
    if not charts_only and time(16,10) <= clock < time(19):
        with urlopen("https://cuoiki-jet.vercel.app/api/market-data?kind=history", timeout=15) as response:
            history = json.load(response)
        if history.get("symbols", {}).get("VNINDEX", {}).get("last", "") < now.date().isoformat():
            jobs.append(("ssi-eod-demo.yml", {}, None))
    started = []
    for workflow, inputs, part in jobs:
        if active(workflow, part):
            print(workflow, part or "", "already active", flush=True)
            continue
        recent = github(f"/actions/workflows/{workflow}/runs?per_page=1").get("workflow_runs", [])
        if recent and recent[0].get("conclusion") in ("failure", "timed_out"):
            updated = datetime.fromisoformat(recent[0]["updated_at"].replace("Z", "+00:00"))
            if (now - updated).total_seconds() < 600:
                print(workflow, "waiting before retry", flush=True)
                continue
        github(f"/actions/workflows/{workflow}/dispatches", {"ref":"main", "inputs":inputs})
        started.append(workflow)
        print("Recovered", workflow, part or "", flush=True)
    return started


if __name__ == "__main__":
    print("Checking SSI collectors at", datetime.now(VN).isoformat(), flush=True)
    reconcile(datetime.now(VN))
