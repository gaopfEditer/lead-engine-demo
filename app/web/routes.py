from __future__ import annotations

import json
from pathlib import Path

import yaml
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from sqlalchemy.orm import Session, joinedload

from app.db.models import Company, Draft, MergeCluster, PipelineRun, Score, SyncLog
from app.db.session import SessionLocal, get_db
from app.services.export import csv_string, export_sample_bundle, exportable_companies, leads_to_csv_rows, quality_report
from app.services.pipeline import compute_funnel, run_pipeline
from app.services.score import load_icp, score_all
from app.services.privacy import scrub_company
from app.settings import settings

router = APIRouter()
TEMPLATES = Path(__file__).parent / "templates"


def _public_company(company: Company) -> Company:
    return scrub_company(company) if settings.public_demo else company


def render(name: str, **ctx) -> HTMLResponse:
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    tpl = env.get_template(name)
    return HTMLResponse(tpl.render(**ctx))


def _latest_run(db: Session) -> PipelineRun | None:
    return db.query(PipelineRun).order_by(PipelineRun.id.desc()).first()


@router.get("/", response_class=HTMLResponse)
def pipeline_page(request: Request, db: Session = Depends(get_db)):
    run = _latest_run(db)
    funnel = run.funnel_json if run else compute_funnel(db)
    meta_path = settings.cslb_sample_path.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return render(
        "pipeline.html",
        request=request,
        funnel=funnel,
        run=run,
        meta=meta,
    )


@router.get("/leads", response_class=HTMLResponse)
def leads_page(
    request: Request,
    tier: str | None = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(Company)
        .options(
            joinedload(Company.scores),
            joinedload(Company.contacts),
            joinedload(Company.drafts),
            joinedload(Company.people),
            joinedload(Company.facts),
        )
        .filter(Company.is_primary_in_cluster.is_(True))
    )
    companies = q.all()
    rows = []
    for c in companies:
        sc = c.scores[-1] if c.scores else None
        if tier and (not sc or sc.tier != tier):
            continue
        email = next((ct.value for ct in c.contacts if ct.status == "ok" and not ct.is_guessed), "")
        rows.append({"company": _public_company(c), "score": sc, "email": email})
    rows.sort(key=lambda r: r["score"].score if r["score"] else -1, reverse=True)
    return render("leads.html", request=request, rows=rows, tier=tier)


@router.get("/leads/{company_id}", response_class=HTMLResponse)
def lead_detail(company_id: int, request: Request, db: Session = Depends(get_db)):
    company = (
        db.query(Company)
        .options(
            joinedload(Company.facts),
            joinedload(Company.contacts),
            joinedload(Company.signals),
            joinedload(Company.scores),
            joinedload(Company.drafts),
            joinedload(Company.people),
        )
        .filter(Company.id == company_id)
        .first()
    )
    if not company:
        return PlainTextResponse("Not found", status_code=404)
    sc = company.scores[-1] if company.scores else None
    draft = company.drafts[0] if company.drafts else None
    pub = _public_company(company)
    draft_pub = pub.drafts[0] if pub.drafts else None
    return render("lead_detail.html", request=request, company=pub, score=sc, draft=draft_pub)


@router.post("/leads/{company_id}/draft")
def update_draft(company_id: int, action: str = Form(...), db: Session = Depends(get_db)):
    draft = db.query(Draft).filter(Draft.company_id == company_id).first()
    if not draft:
        return PlainTextResponse("No draft", status_code=404)
    if action in ("approve", "reject"):
        draft.status = "approved" if action == "approve" else "rejected"
        db.commit()
    return HTMLResponse(f'<span class="badge">{draft.status}</span>')


@router.get("/icp", response_class=HTMLResponse)
def icp_page(request: Request):
    icp = load_icp()
    return render("icp.html", request=request, icp=icp, icp_yaml=yaml.safe_dump(icp))


@router.post("/icp/recompute")
def icp_recompute(db: Session = Depends(get_db)):
    if settings.demo_read_only:
        return PlainTextResponse("Read-only demo", status_code=403)
    score_all(db)
    return HTMLResponse("<p>Scores recomputed.</p>")


@router.get("/quality", response_class=HTMLResponse)
def quality_page(request: Request, db: Session = Depends(get_db)):
    report = quality_report(db)
    meta_path = settings.cslb_sample_path.with_suffix(".meta.json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    clusters = db.query(MergeCluster).count()
    return render(
        "quality.html",
        request=request,
        report=report,
        meta=meta,
        merge_clusters=clusters,
    )


@router.get("/export/sample.csv")
def export_sample(db: Session = Depends(get_db)):
    out_dir = Path(__file__).resolve().parents[2] / "data" / "exports"
    csv_path, _ = export_sample_bundle(db, out_dir)
    return FileResponse(csv_path, filename="sample_50_leads.csv")


@router.get("/export/sample-report.json")
def export_sample_report(db: Session = Depends(get_db)):
    return quality_report(db)


@router.get("/export/leads.csv")
def export_leads(db: Session = Depends(get_db)):
    rows = leads_to_csv_rows(db, exportable_companies(db))
    return PlainTextResponse(csv_string(rows), media_type="text/csv")


@router.get("/sync", response_class=HTMLResponse)
def sync_page(request: Request, db: Session = Depends(get_db)):
    logs = db.query(SyncLog).order_by(SyncLog.id.desc()).limit(50).all()
    return render("sync.html", request=request, logs=logs, hubspot_enabled=bool(settings.hubspot_token))


@router.post("/sync/hubspot")
def sync_hubspot(db: Session = Depends(get_db)):
    from app.services.crm.hubspot import push_hubspot

    result = push_hubspot(db)
    return HTMLResponse(f"<li>{result}</li>")
