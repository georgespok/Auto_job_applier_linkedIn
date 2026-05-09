from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import csv
import json
from datetime import datetime
import os
from threading import Timer
import webbrowser
from config.settings import file_name
from config.secrets import use_AI, ai_provider, llm_api_url, llm_api_key, llm_model

app = Flask(__name__)
CORS(app)

APPLIED_JOBS_CSV = file_name
AI_LOCATION_FIELD = 'AI Location'
AI_COMPENSATION_FIELD = 'AI Compensation'
AI_EXTRACTION_BATCH_SIZE = 25
ABOUT_JOB_MAX_CHARS = 1600
APP_HOST = 'localhost'
APP_PORT = 5000
APP_URL = f'http://{APP_HOST}:{APP_PORT}'


def open_app_browser() -> None:
    webbrowser.open_new(APP_URL)


def text_value(value) -> str:
    return "" if value is None else str(value)


def extract_job_details_with_ai(rows: list[dict]) -> bool:
    """
    Uses the configured OpenAI-compatible model to extract job details from the
    saved job description text and caches the result in the CSV rows.
    """
    if not use_AI or ai_provider.lower() != "openai" or not llm_api_key:
        return False

    missing_rows = [
        row for row in rows
        if not text_value(row.get(AI_LOCATION_FIELD)).strip()
        or not text_value(row.get(AI_COMPENSATION_FIELD)).strip()
    ]
    if not missing_rows:
        return False

    try:
        from openai import OpenAI

        client = OpenAI(base_url=llm_api_url, api_key=llm_api_key)
        changed = False

        for start in range(0, len(missing_rows), AI_EXTRACTION_BATCH_SIZE):
            batch = missing_rows[start:start + AI_EXTRACTION_BATCH_SIZE]
            jobs_payload = [
                {
                    "job_id": row.get("Job ID", ""),
                    "title": row.get("Title", ""),
                    "company": row.get("Company", ""),
                    "stored_work_location": row.get("Work Location", ""),
                    "cached_location": row.get(AI_LOCATION_FIELD, ""),
                    "about_job": text_value(row.get("About Job"))[:ABOUT_JOB_MAX_CHARS],
                }
                for row in batch
            ]

            completion = client.chat.completions.create(
                model=llm_model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Extract job work location and compensation from saved job posting text. "
                            "Use only the provided data. Ignore stored_work_location when it looks like "
                            "a company-name fragment. Return compact JSON only in this shape: "
                            "{\"jobs\":[{\"job_id\":\"...\",\"location\":\"...\",\"compensation\":\"...\"}]}. "
                            "Use city/region/country plus Remote/Hybrid/On-site when stated. "
                            "For compensation, extract salary, hourly rate, yearly range, pay range, "
                            "OTE, contract rate, bonus/equity if explicitly stated. Preserve currency "
                            "and period such as CAD 90-100/hour or $100k-$130k/year. "
                            "If no location or compensation is clear, use \"Unknown\" for that field."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({"jobs": jobs_payload}, ensure_ascii=False),
                    },
                ],
            )

            content = completion.choices[0].message.content or "{}"
            parsed = json.loads(content)
            extracted_jobs = parsed.get("jobs", [])
            details_by_id = {
                str(item.get("job_id", "")): {
                    "location": str(item.get("location", "")).strip(),
                    "compensation": str(item.get("compensation", "")).strip(),
                }
                for item in extracted_jobs
                if item.get("job_id")
            }

            for row in batch:
                details = details_by_id.get(str(row.get("Job ID", "")), {})
                if not text_value(row.get(AI_LOCATION_FIELD)).strip():
                    row[AI_LOCATION_FIELD] = details.get("location") or "Unknown"
                    changed = True
                if not text_value(row.get(AI_COMPENSATION_FIELD)).strip():
                    row[AI_COMPENSATION_FIELD] = details.get("compensation") or "Unknown"
                    changed = True

        client.close()
        return changed
    except Exception as e:
        print(f"AI job detail extraction failed: {e}")
        return False


def read_applied_jobs_rows() -> list[dict]:
    with open(APPLIED_JOBS_CSV, 'r', encoding='utf-8', newline='') as file:
        reader = csv.DictReader(file)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])

    if AI_LOCATION_FIELD not in fieldnames:
        fieldnames.append(AI_LOCATION_FIELD)
        write_applied_jobs_rows(rows, fieldnames)
    if AI_COMPENSATION_FIELD not in fieldnames:
        fieldnames.append(AI_COMPENSATION_FIELD)
        write_applied_jobs_rows(rows, fieldnames)

    for row in rows:
        row[AI_LOCATION_FIELD] = text_value(row.get(AI_LOCATION_FIELD))
        row[AI_COMPENSATION_FIELD] = text_value(row.get(AI_COMPENSATION_FIELD))

    if extract_job_details_with_ai(rows):
        write_applied_jobs_rows(rows, fieldnames)

    return rows


def write_applied_jobs_rows(rows: list[dict], fieldnames: list[str] | None = None) -> None:
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    if AI_LOCATION_FIELD not in fieldnames:
        fieldnames.append(AI_LOCATION_FIELD)
    if AI_COMPENSATION_FIELD not in fieldnames:
        fieldnames.append(AI_COMPENSATION_FIELD)

    with open(APPLIED_JOBS_CSV, 'w', encoding='utf-8', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


##> ------ Karthik Sarode : karthik.sarode23@gmail.com - UI for excel files ------
@app.route('/')
def home():
    """Displays the home page of the application."""
    return render_template('index.html')

@app.route('/applied-jobs', methods=['GET'])
def get_applied_jobs():
    '''
    Retrieves a list of applied jobs from the applications history CSV file.
    
    Returns a JSON response containing a list of jobs, each with details such as 
    Job ID, Title, Company, HR Name, HR Link, Job Link, External Job link, and Date Applied.
    
    If the CSV file is not found, returns a 404 error with a relevant message.
    If any other exception occurs, returns a 500 error with the exception message.
    '''

    try:
        jobs = []
        for row in read_applied_jobs_rows():
            jobs.append({
                'Job_ID': row['Job ID'],
                'Title': row['Title'],
                'Company': row['Company'],
                'Location': row.get(AI_LOCATION_FIELD) or row.get('Work Location', 'Unknown'),
                'Compensation': row.get(AI_COMPENSATION_FIELD) or 'Unknown',
                'HR_Name': row['HR Name'],
                'HR_Link': row['HR Link'],
                'Job_Link': row['Job Link'],
                'External_Job_link': row['External Job link'],
                'Date_Applied': row['Date Applied']
            })
        return jsonify(jobs)
    except FileNotFoundError:
        return jsonify({"error": f"No applications history found at {APPLIED_JOBS_CSV}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/applied-jobs/<job_id>', methods=['PUT'])
def update_applied_date(job_id):
    """
    Updates the 'Date Applied' field of a job in the applications history CSV file.

    Args:
        job_id (str): The Job ID of the job to be updated.

    Returns:
        A JSON response with a message indicating success or failure of the update
        operation. If the job is not found, returns a 404 error with a relevant
        message. If any other exception occurs, returns a 500 error with the
        exception message.
    """
    try:
        data = []
        csvPath = APPLIED_JOBS_CSV
        
        if not os.path.exists(csvPath):
            return jsonify({"error": f"CSV file not found at {csvPath}"}), 404
            
        # Read current CSV content
        with open(csvPath, 'r', encoding='utf-8', newline='') as file:
            reader = csv.DictReader(file)
            fieldNames = reader.fieldnames
            found = False
            for row in reader:
                if row['Job ID'] == job_id:
                    row['Date Applied'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    found = True
                data.append(row)
        
        if not found:
            return jsonify({"error": f"Job ID {job_id} not found"}), 404

        with open(csvPath, 'w', encoding='utf-8', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=fieldNames)
            writer.writeheader()
            writer.writerows(data)
        
        return jsonify({"message": "Date Applied updated successfully"}), 200
    except Exception as e:
        print(f"Error updating applied date: {str(e)}")  # Debug log
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        Timer(1, open_app_browser).start()
    app.run(debug=True, host=APP_HOST, port=APP_PORT)

##<
