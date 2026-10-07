#!/usr/bin/env python3
"""Pull live fund accounting / fund operations / fund finance postings and write them to leads.md.

Sources: Greenhouse, Lever, Ashby and Personio feeds for the firms in scripts/feeds.json,
the Bundesagentur für Arbeit job search API (covers employers on other systems), and four fund
administrators with their own career sites: Citco (Oracle HCM), Vistra (Phenom), TMF Group (Avature)
and Hannover Leasing (rexx). Glassdoor is deliberately not used (bot protection, terms of service).
Standard library only. Run from the repo root:  python3 scripts/fetch_leads.py
"""
import datetime as dt
import html
import json
import pathlib
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from zoneinfo import ZoneInfo

ROOT = pathlib.Path(__file__).resolve().parent.parent
FEEDS = ROOT / "scripts" / "feeds.json"
STATE = ROOT / "scripts" / "leads_state.json"
LEADS = ROOT / "leads.md"
START, END = "<!-- AUTO-LEADS:START -->", "<!-- AUTO-LEADS:END -->"
TODAY = dt.datetime.now(ZoneInfo("Europe/Berlin")).date().isoformat()  # Reyan's calendar day, not UTC
UA = {"User-Agent": "job-search-leads/1.0 (personal job search)"}

ROLE = re.compile(
    r"fund\s*(accountant|accounting|operations?|ops|finance|administrat\w*|reporting|controll\w*)"
    r"|fonds\w*(buchhalt\w*|administrat\w*|controlling|accounting)"
    r"|investor\s*reporting|capital\s*(calls?|activity)|private\s*(equity|markets)\s*(accountant|accounting|operations|finance)",
    re.I,
)
GERMANY = re.compile(
    r"germany|deutschland|berlin|m(ü|ue|u)nchen|munich|frankfurt|hamburg|d(ü|ue|u)sseldorf|k(ö|oe|o)ln|cologne|stuttgart"
    r"|eschborn|wiesbaden|mainz|hannover|leipzig|dresden|n(ü|ue|u)rnberg|bonn|pullach|kronberg|remote|\bde\b",
    re.I,
)
SENIOR = re.compile(r"\b(senior|sr\.?|head|lead|leader|director|principal|vp|vice president|manager|teamleit\w*|leiter\w*"
                    r"|abteilungsleit\w*)\b", re.I)
# At a fund administrator, client accounting work is fund accounting, so accept plain accounting titles there.
ADMIN_ROLE = re.compile(r"account(ant|ing)|buchhalt\w*|fund|fonds", re.I)
# Words that only appear in German-language ads: a strong hint the job needs fluent German.
GERMAN_AD = re.compile(r"sachbearbeit|mitarbeiter|buchhalter|bankkaufm|teamleitung|befristet|elternzeit"
                       r"|vertretung|fondsadministration|\b(für|und|im|das|der|die)\b", re.I)
AGENCY = re.compile(r"recruit|personal|page|hays|randstad|bankpower|amadeus fire|\bdis ag\b|robert half|adecco|manpower"
                    r"|kienbaum|experis|gulp|akzent|orizon|zeitarbeit", re.I)


def get(url, headers=None, tries=4):
    """GET with a short retry for dropped connections. HTTP errors (403, 404...) are not retried."""
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.read()
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))


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


class PartialSource(Exception):
    """A source failed part-way; rows already yielded are still valid."""


def page(url, pause=0.0):
    time.sleep(pause)  # be gentle with small career sites
    return get(url).decode("utf-8", "ignore")


def strip_tags(fragment):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def citco():
    """Oracle HCM candidate-experience API (public JSON)."""
    base = "https://fa-euxc-saasfaprod1.fa.ocs.oraclecloud.com"
    url = (f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?onlyData=true&expand=requisitionList"
           "&finder=findReqs;siteNumber=CX_1,keyword=Germany,limit=25")
    for item in json.loads(get(url)).get("items", []):
        for r in item.get("requisitionList", []):
            yield (r["Title"], r.get("PrimaryLocation", ""),
                   f"{base}/hcmUI/CandidateExperience/en/sites/CX_1/job/{r['Id']}", iso(r.get("PostedDate")), {})


def vistra():
    """Phenom career site: job data sits in the page as `phApp.ddo = {...};`.
    The keywords parameter is ignored server-side (every query returns all jobs), and result order shifts
    between page requests, so one pass can skip jobs. Re-page (max 3 passes) until every job id is seen."""
    all_ids, yielded, total = set(), set(), None
    for _ in range(3):
        offset = 0
        while total is None or offset < min(total, 1000):
            h = page(f"https://jobs.vistra.com/global/en/search-results?from={offset}&s=1", pause=0.3)
            m = re.search(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp", h, re.S)
            if not m:
                raise ValueError("phApp.ddo not found (page layout changed?)")
            search = json.loads(m.group(1))["eagerLoadRefineSearch"]
            total, jobs = search.get("totalHits", 0), search["data"]["jobs"]
            if not jobs:
                break
            for j in jobs:
                all_ids.add(j["jobId"])
                if j["jobId"] in yielded or j.get("country") != "DEU":
                    continue
                yielded.add(j["jobId"])
                yield (j["title"], f"{j.get('city') or ''}, Germany".lstrip(", "),
                       f"https://jobs.vistra.com/global/en/job/{j['jobId']}", iso(j.get("postedDate")), {})
            offset += len(jobs)
        if len(all_ids) >= (total or 0):
            return
    raise PartialSource(f"saw {len(all_ids)} of {total} jobs after 3 passes")


def tmf():
    """Avature, server-rendered. The working search parameter is `search` (the `keywords` URL parameter is
    ignored). Six results per page; location only on the detail page, so fetch details for title matches."""
    base = "https://tmf.avature.net/careersmarketplace"
    links = {}
    for term in ("fund", "accountant", "accounting", "private equity"):
        for offset in range(0, 300, 6):
            h = page(f"{base}/SearchJobs?search={urllib.parse.quote(term)}&jobOffset={offset}", pause=0.5)
            found = {u: strip_tags(t) for u, t in re.findall(r'<a[^>]+href="([^"]*JobDetail/[^"]+)"[^>]*>(.*?)</a>', h, re.S)}
            new = {u: t for u, t in found.items() if t and u not in links}
            if not new:
                break
            links.update(new)
    for url, title in links.items():
        if not ADMIN_ROLE.search(title):
            continue
        try:
            d = page(url, pause=0.5)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            raise PartialSource(f"detail page {url}: {e}") from e
        loc = re.search(r'field__label">\s*Location\s*</div>\s*<div class="article__content__view__field__value">(.*?)</div>', d, re.S)
        posted = re.search(r'"datePosted":"([0-9-]+)"', d)
        yield title, strip_tags(loc.group(1)) if loc else "", url, posted.group(1) if posted else "", {}


def hannover_leasing():
    """rexx job portal; the listing is static HTML. All ads are German-language."""
    h = page("https://karriere.hannover-leasing.de/stellenangebote.html")
    for url, body in re.findall(r"<article class=\"joboffer_container\" onclick=\"window\.location\.href='([^']+)'\">(.*?)</article>", h, re.S):
        parts = [p.strip() for p in html.unescape(re.sub(r"<[^>]+>", "|", body)).split("|") if p.strip()]
        if parts:
            yield parts[0], parts[-1] if len(parts) > 1 else "", url, "", {"german": True, "in_germany": True}


CUSTOM = {"citco": citco, "vistra": vistra, "tmf": tmf, "hannover-leasing": hannover_leasing}

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
    leads, errors, failed = {}, [], set()

    def add(company, title, loc, url, posted, source, need_germany, role=ROLE, force=None):
        if not role.search(title):
            return
        if need_germany and not (force or {}).get("in_germany") and not GERMANY.search(loc or ""):
            return
        leads[url] = {"company": company, "title": title, "location": loc or "?", "url": url,
                      "posted": posted, "source": source, "senior": bool(SENIOR.search(title)),
                      "german": bool(GERMAN_AD.search(title)), "agency": bool(AGENCY.search(company)),
                      **{k: v for k, v in (force or {}).items() if k != "in_germany"}}

    for f in cfg["ats"]:
        try:
            for title, loc, url, posted in ATS[f["ats"]](f["slug"]):
                add(f["company"], title, loc, url, posted, f["ats"], need_germany=True)
        except Exception as e:  # one dead feed must not stop the run
            errors.append(f"{f['company']} ({f['ats']}/{f['slug']}): {e}")
            failed.add(f["ats"])

    for f in cfg.get("fund_admins", []):
        try:
            for title, loc, url, posted, force in CUSTOM[f["type"]]():
                add(f["company"], title, loc, url, posted, f["type"], need_germany=True, role=ADMIN_ROLE, force=force)
        except Exception as e:
            errors.append(f"{f['company']} ({f['type']}): {e}")
            failed.add(f["type"])

    for q in cfg["arbeitsagentur_queries"]:
        try:
            for company, title, loc, url, posted in arbeitsagentur(q, cfg.get("arbeitsagentur_days", 30)):
                add(company, title, loc, url, posted, "arbeitsagentur", need_germany=False)
        except Exception as e:
            errors.append(f"Arbeitsagentur '{q}': {e}")
            failed.add("arbeitsagentur")
    return dedupe(leads), errors, failed


def company_key(name):
    words = re.findall(r"[a-z0-9]+", name.lower())
    return words[0] if words else ""


def dedupe(leads):
    """The same job is often listed twice (employer site + Arbeitsagentur, or two BA records, sometimes with
    city names appended to the title). Prefer the employer's own link, then the newest posting."""
    best = {}
    for l in leads.values():
        title = re.sub(r"\W+", " ", l["title"].lower().split(",")[0]).strip()
        key = (company_key(l["company"]), title)
        rank = (l["source"] != "arbeitsagentur", l["posted"])
        if key not in best or rank > (best[key]["source"] != "arbeitsagentur", best[key]["posted"]):
            best[key] = l
    return {l["url"]: l for l in best.values()}


def pipeline_companies():
    p = ROOT / "pipeline.md"
    if not p.exists():
        return set()
    names = [line.split("|")[1] for line in p.read_text().splitlines()
             if line.startswith("|") and not line.startswith("|---") and "Company" not in line]
    return {company_key(n) for n in names if n.strip()}


def render(leads, state, gone, errors, failed, n_feeds, n_queries):
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
           f"{len(gone)} gone since last run" + (f" · sources not fully checked this run: {', '.join(sorted(failed))}" if failed else ""),
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
    leads, errors, failed = collect(cfg)

    old = json.loads(STATE.read_text()) if STATE.exists() else {}
    state = {u: {"first_seen": old.get(u, {}).get("first_seen", TODAY), "company": l["company"], "title": l["title"],
                 "source": l["source"]} for u, l in leads.items()}
    # A source that failed this run can't prove its jobs are gone: keep them in state, don't report them.
    unchecked = {u: v for u, v in old.items() if u not in leads and v.get("source") in failed}
    live_keys = {(company_key(l["company"]), re.sub(r"\W+", " ", l["title"].lower().split(",")[0]).strip())
                 for l in leads.values()}
    gone = [v for u, v in old.items() if u not in leads and u not in unchecked
            and (company_key(v["company"]), re.sub(r"\W+", " ", v["title"].lower().split(",")[0]).strip()) not in live_keys]
    state.update(unchecked)
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False, sort_keys=True) + "\n")

    block = render(leads, state, gone, errors, failed, len(cfg["ats"]) + len(cfg.get("fund_admins", [])),
                   len(cfg["arbeitsagentur_queries"]))
    text = LEADS.read_text() if LEADS.exists() else "# Leads\n"
    if START in text and END in text:
        text = text[:text.index(START)] + block + text[text.index(END) + len(END):]
    else:  # first run: put the live block right under the title
        head, _, rest = text.partition("\n")
        text = f"{head}\n\n{block}\n{rest}"
    LEADS.write_text(text)

    print(f"{len(leads)} live leads ({sum(1 for u in leads if state[u]['first_seen'] == TODAY)} new), "
          f"{len(gone)} gone, {len(errors)} feed errors -> {LEADS.relative_to(ROOT)}")
    for e in errors:
        print("  feed error:", e, file=sys.stderr)


if __name__ == "__main__":
    main()
