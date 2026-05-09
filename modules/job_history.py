import csv
import re


_JOB_ID_RE = re.compile(r"/jobs/view/(\d+)")
_TOKEN_RE = re.compile(r"[a-z0-9#.+]+")

_COMPANY_SUFFIXES = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation",
    "company", "co", "services", "service"
}

_TITLE_STOP_WORDS = {
    "a", "an", "and", "the", "for", "of", "to", "in", "with",
    "senior", "sr", "jr", "junior", "mid", "level", "remote", "hybrid",
    "onsite", "on", "site", "contract", "contractor", "full", "part",
    "time", "permanent", "perm", "role", "position"
}

_TITLE_ALIASES = {
    ".net": "net",
    "dotnet": "net",
    "asp.net": "net",
    "aspnet": "net",
    "c#": "csharp",
    "engineer": "developer",
    "engineering": "developer",
    "developers": "developer",
    "developer": "developer",
    "dev": "developer",
}


def extract_job_id_from_link(job_link: str | None) -> str:
    if not job_link:
        return ""
    match = _JOB_ID_RE.search(job_link)
    return match.group(1) if match else ""


def normalize_job_id(job_id: str | None) -> str:
    return str(job_id or "").strip()


def normalize_company(company: str | None) -> str:
    tokens = []
    for token in _TOKEN_RE.findall(str(company or "").lower()):
        if token in _COMPANY_SUFFIXES:
            continue
        if token.endswith("s") and len(token) > 4:
            token = token[:-1]
        tokens.append(token)
    return " ".join(tokens)


def normalize_title_tokens(title: str | None) -> set[str]:
    text = str(title or "").lower()
    text = text.replace(".net", " dotnet ")
    text = text.replace("c#", " csharp ")

    tokens = set()
    for token in _TOKEN_RE.findall(text):
        token = _TITLE_ALIASES.get(token, token)
        if token in _TITLE_STOP_WORDS:
            continue
        tokens.add(token)
    return tokens


def title_similarity(first_title: str | None, second_title: str | None) -> float:
    first_tokens = normalize_title_tokens(first_title)
    second_tokens = normalize_title_tokens(second_title)
    if not first_tokens or not second_tokens:
        return 0
    return len(first_tokens & second_tokens) / len(first_tokens | second_tokens)


def make_applied_job_fingerprint(job_id: str | None, title: str | None, company: str | None) -> dict:
    return {
        "job_id": normalize_job_id(job_id),
        "title": str(title or "").strip(),
        "company": str(company or "").strip(),
        "company_key": normalize_company(company),
        "title_tokens": normalize_title_tokens(title),
    }


def load_applied_jobs_history(file_name: str) -> tuple[set[str], list[dict]]:
    job_ids = set()
    fingerprints = []
    try:
        with open(file_name, "r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            for row in reader:
                job_id = normalize_job_id(row.get("Job ID"))
                linked_job_id = extract_job_id_from_link(row.get("Job Link"))
                if job_id:
                    job_ids.add(job_id)
                if linked_job_id:
                    job_ids.add(linked_job_id)
                fingerprints.append(
                    make_applied_job_fingerprint(
                        job_id or linked_job_id,
                        row.get("Title"),
                        row.get("Company"),
                    )
                )
    except FileNotFoundError:
        return set(), []
    return job_ids, fingerprints


def find_previously_applied_match(
    job_id: str | None,
    title: str | None,
    company: str | None,
    applied_job_ids: set[str],
    applied_job_fingerprints: list[dict],
    title_similarity_threshold: float = 0.6,
) -> dict | None:
    normalized_job_id = normalize_job_id(job_id)
    if normalized_job_id and normalized_job_id in applied_job_ids:
        return {
            "match_type": "job_id",
            "job_id": normalized_job_id,
            "title": title or "",
            "company": company or "",
            "similarity": 1,
        }

    company_key = normalize_company(company)
    title_tokens = normalize_title_tokens(title)
    if not company_key or not title_tokens:
        return None

    for fingerprint in applied_job_fingerprints:
        if fingerprint.get("company_key") != company_key:
            continue
        previous_tokens = fingerprint.get("title_tokens", set())
        if not previous_tokens:
            continue
        similarity = len(title_tokens & previous_tokens) / len(title_tokens | previous_tokens)
        if similarity >= title_similarity_threshold:
            return {
                "match_type": "similar_company_title",
                "job_id": fingerprint.get("job_id", ""),
                "title": fingerprint.get("title", ""),
                "company": fingerprint.get("company", ""),
                "similarity": similarity,
            }

    return None
