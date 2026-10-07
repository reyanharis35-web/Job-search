#!/usr/bin/env python3
"""Pull live fund accounting / fund operations / fund finance postings and write them to leads.md.

Sources: Greenhouse, Lever, Ashby and Personio feeds for the firms in scripts/feeds.json,
plus the Bundesagentur für Arbeit job search API (covers employers on other systems).
Standard library only. Run from the repo root:  python3 scripts/fetch_leads.py
"""
import datetime as dt
import json
import pathlib
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
FEEDS = ROOT / "scripts" / "feeds.json"
STATE = ROOT / "scripts" / "leads_state.json"
LEADS = ROOT / "leads.md"
START, END = "<!-- AUTO-LEADS:START -->", "<!-- AUTO-LEADS:END -->"
TODAY = dt.date.today().isoformat()
UA = {"User-Agent": "job-search-leads/1.0 (personal job search)"}

ROLE = re.compile(
    r"fund\s*(accountant|accounting|operations?|ops|finance|administrat\w*|reporting|controll\w*)"
    r"|fonds\w*(buchhalt\w*|administrat\w*|controlling|accounting)"
    r"|investor\s*reporting|capital\s*(calls?|activity)|private\s*(equity|markets)\s*(accountant|accounting|operations|finance)",
    re.I,
)
GERMANY = re.compile(
    r"germany|deutschland|berlin|m(ü|ue|u)nchen|munich|frankfurt|hamburg|d(ü|ue|u)sseldorf|k(ö|oe|o)ln|cologne|stuttgart"
    r"|eschborn|wiesbaden|mainz|hannover|leipzig|dresden|n(ü|ue|u)rnberg|bonn|remote|\bde\b",
    re.I,
)
SENIOR = re.compile(r"\b(senior|sr\.?|head|lead|director|principal|vp|manager|teamleit\w*|leiter\w*|abteilungsleit\w*)\b", re.I)
# Words that only appear in German-language ads: a strong hint the job needs fluent German.
GERMAN_AD = re.compile(r"sachbearbeit|mitarbeiter|fondsbuchhalt|bilanzbuchhalt|bankkaufm|teamleitung|befristet|elternzeit"
                       r"|vertretung|fondsadministration|\b(für|und|im|das|der|die)\b", re.I)
AGENCY = re.compile(r"recruit|personal|page|hays|randstad|bankpower|amadeus fire|\bdis ag\b|robert half|adecco|manpower"
                    r"|kienbaum|experis|gulp|akzent|orizon|zeitarbeit", re.I)


def get(url, headers=None):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def iso(value):
    """Normalise ISO strings and epoch-millis to YYYY-MM-DD."""
    if value in (None, ""):
        return ""
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / 1000, dt.timezone.utc).date().isoformat()
    return str(value)[:10]


def greenhouse(slug):
    for j in json.loads(get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"))["jobs"]:
        yield j["title"], j["location"]["name"], j["absolute_url"], iso(j.get("first_published") or j.get("updated_at"))


def lever(slug, host="api.lever.co"):
    for j in json.loads(get(f"https://{host}/v0/postings/{slug}?mode=json")):
        cats = j.get("categories", {})
        loc = cats.get("location") or ", ".join(cats.get("allLocations", []))
        yield j["text"], loc, j["hostedUrl"], iso(j.get("createdAt"))


def ashby(slug):
    for j in json.loads(get(f"https://api.ashbyhq.com/posting-api/job-board/{slug}"))["jobs"]:
        locs = [j.get("location") or ""] + [s.get("location", "") for s in j.get("secondaryLocations", [])]
        yield j["title"], "; ".join(l for l in locs if l), j["jobUrl"], iso(j.get("publishedAt"))


def personio(slug):
    root = ET.fromstring(get(f"https://{slug}.jobs.personio.de/xml"))
    for p in root.iter("position"):
        offices = [p.findtext("office") or ""] + [o.text or "" for o in p.iter("additionalOffice")]
        yield (p.findtext("name") or "").strip(), "; ".join(o for o in offices if o), \
            f"https://{slug}.jobs.personio.de/job/{p.findtext('id')}", iso(p.findtext("createdAt"))


ATS = {
    "greenhouse": greenhouse,
    "lever": lever,
    "lever-eu": lambda s: lever(s, "api.eu.lever.co"),
    "ashby": ashby,
    "personio": personio,
}


def arbeitsagentur(query, days):
    params = urllib.parse.urlencode({"was": query, "angebotsart": 1, "veroeffentlichtseit": days, "size": 100, "page": 1})
    data = json.loads(get(f"https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs?{params}",
                          {"X-API-Key": "jobboerse-jobsuche"}))
    for j in data.get("ergebnisliste", []):
        locs = "; ".join(sorted({l.get("adresse", {}).get("ort", "") for l in j.get("stellenlokationen", [])} - {""}))
        yield (j.get("firma", "").strip(), j.get("stellenangebotsTitel", "").strip(), locs,
               f"https://www.arbeitsagentur.de/jobsuche/jobdetail/{j['referenznummer']}",
               iso((j.get("veroeffentlichungszeitraum") or {}).get("von")))


def collect(cfg):
    leads, errors = {}, []

    def add(company, title, loc, url, posted, source, need_germany):
        if not ROLE.search(title):
            return
        if need_germany and not GERMANY.search(loc or ""):
            return
        leads[url] = {"company": company, "title": title, "location": loc or "?", "url": url,
                      "posted": posted, "source": source, "senior": bool(SENIOR.search(title)),
                      "german": bool(GERMAN_AD.search(title)), "agency": bool(AGENCY.search(company))}

    for f in cfg["ats"]:
        try:
            for title, loc, url, posted in ATS[f["ats"]](f["slug"]):
                add(f["company"], title, loc, url, posted, f["ats"], need_germany=True)
        except Exception as e:  # one dead feed must not stop the run
            errors.append(f"{f['company']} ({f['ats']}/{f['slug']}): {e}")

    for q in cfg["arbeitsagentur_queries"]:
        try:
            for company, title, loc, url, posted in arbeitsagentur(q, cfg.get("arbeitsagentur_days", 30)):
                add(company, title, loc, url, posted, "arbeitsagentur", need_germany=False)
        except Exception as e:
            errors.append(f"Arbeitsagentur '{q}': {e}")
    return dedupe(leads), errors


def company_key(name):
    words = re.findall(r"[a-z0-9]+", name.lower())
    return words[0] if words else ""


def dedupe(leads):
    """The same job is often listed twice (employer feed + Arbeitsagentur, or two BA records). Keep the newest."""
    best = {}
    for l in leads.values():
        key = (company_key(l["company"]), re.sub(r"\W+", " ", l["title"].lower()).strip(), l["location"].lower())
        if key not in best or l["posted"] > best[key]["posted"]:
            best[key] = l
    return {l["url"]: l for l in best.values()}


def pipeline_companies():
    p = ROOT / "pipeline.md"
    if not p.exists():
        return set()
    names = [line.split("|")[1] for line in p.read_text().splitlines()
             if line.startswith("|") and not line.startswith("|---") and "Company" not in line]
    return {company_key(n) for n in names if n.strip()}


def render(leads, state, gone, errors, n_feeds, n_queries):
    rows = sorted(leads.values(), key=lambda l: (l["senior"], l["german"], l["agency"], l["company"].lower(), l["title"].lower()))
    in_pipeline = pipeline_companies()
    out = [START,
           f"## Live leads (auto, last checked {TODAY})",
           "",
           f"Generated by `scripts/fetch_leads.py` from {n_feeds} company feeds and {n_queries} Arbeitsagentur searches. "
           "Every row was live on the check date. Don't edit inside this block; it's rewritten on each run. "
           "Copy a row to `pipeline.md` when you apply.",
           "",
           f"**{len(rows)} live** · {sum(1 for l in rows if state[l['url']]['first_seen'] == TODAY)} new today · "
           f"{len(gone)} gone since last run",
           "",
           "Level: `fit` or `stretch` (senior/lead title). Ad: `EN` or `DE` (German-language ad, expect fluent German). "
           "Via: `direct` or `agency` (recruiter; employer hidden). ⭐ = company already in `pipeline.md`.",
           "",
           "| New | Level | Ad | Via | Company | Role | Location | Posted | First seen | Checked | Source | Link |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for l in rows:
        s = state[l["url"]]
        cell = lambda t: str(t).replace("|", "/").replace("\n", " ")
        star = " ⭐" if company_key(l["company"]) in in_pipeline else ""
        out.append(f"| {'🆕' if s['first_seen'] == TODAY else ''} | {'stretch' if l['senior'] else 'fit'} | "
                   f"{'DE' if l['german'] else 'EN'} | {'agency' if l['agency'] else 'direct'} | {cell(l['company'])}{star} | {cell(l['title'])} | {cell(l['location'])} | {l['posted'] or '?'} | "
                   f"{s['first_seen']} | {TODAY} | {l['source']} | [open]({l['url']}) |")
    if not rows:
        out.append("| | | | | | No matching postings today | | | | | | |")
    if gone:
        out += ["", "**Gone since last run (filled or taken down):**"]
        out += [f"- {g['company']}: {g['title']} (first seen {g['first_seen']})" for g in gone]
    if errors:
        out += ["", "**Feeds that failed this run (check or remove from `scripts/feeds.json`):**"]
        out += [f"- {e}" for e in errors]
    out.append(END)
    return "\n".join(out)


def main():
    cfg = json.loads(FEEDS.read_text())
    leads, errors = collect(cfg)

    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    state = {u: {"first_seen": old.get(u, {}).get("first_seen", TODAY), "company": l["company"], "title": l["title"]}
             for u, l in leads.items()}
    gone = [v for u, v in old.items() if u not in leads]
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True) + "\n")

    block = render(leads, state, gone, errors, len(cfg["ats"]), len(cfg["arbeitsagentur_queries"]))
    text = LEADS.read_text() if LEADS.exists() else "# Leads\n"
    if START in text and END in text:
        text = text[:text.index(START)] + block + text[text.index(END) + len(END):]
    else:  # first run: put the live block right under the title
        head, _, rest = text.partition("\n")
        text = f"{head}\n\n{block}\n{rest}"
    LEADS.write_text(text)

    print(f"{len(leads)} live leads ({sum(1 for v in state.values() if v['first_seen'] == TODAY)} new), "
          f"{len(gone)} gone, {len(errors)} feed errors -> {LEADS.relative_to(ROOT)}")
    for e in errors:
        print("  feed error:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
