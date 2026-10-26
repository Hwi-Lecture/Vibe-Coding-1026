"""Run: python -m uvicorn app:app --host 127.0.0.1 --port 8000"""
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel, Field
from uuid import UUID
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from service import DashboardService
from briefing import BriefingService
import mailer

HERE = Path(__file__).resolve().parent
app = FastAPI(title='난방 연료비 대시보드', docs_url=None, redoc_url=None)
service = DashboardService()
briefings = BriefingService(service.storage)


class DraftRequest(BaseModel):
    snapshot_id: str = Field(min_length=64, max_length=64, pattern='^[a-f0-9]+$')


class SendRequest(DraftRequest):
    recipient: str = Field(min_length=3, max_length=254)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    request_id: UUID


@app.exception_handler(mailer.MailError)
async def mail_error(request, error):
    return JSONResponse({'detail': str(error)}, status_code=error.status)


def mail_snapshot(request, identity):
    # Local forms use a custom JSON header; disallow cross-origin drive-by sends.
    origin = request.headers.get('origin')
    if request.headers.get('x-dashboard-request') != '1' or (origin and origin != str(request.base_url).rstrip('/')):
        raise HTTPException(403, '대시보드 화면에서 요청해주세요.')
    snapshot = service.response()['data']
    if not snapshot:
        raise HTTPException(409, '먼저 유가 데이터를 불러와주세요.')
    if mailer.snapshot_id(snapshot) != identity:
        raise HTTPException(409, '데이터가 갱신되었습니다. 페이지를 새로고침하고 첨부 기준일을 확인하세요.')
    return snapshot


@app.post('/api/mail/draft')
def mail_draft(data: DraftRequest, request: Request):
    snapshot = mail_snapshot(request, data.snapshot_id)
    return mailer.draft(snapshot)


@app.post('/api/mail/send')
def mail_send(data: SendRequest, request: Request):
    snapshot = mail_snapshot(request, data.snapshot_id)
    return mailer.send(snapshot, service.storage, data.recipient.strip(), data.subject, data.body, str(data.request_id))


@app.get('/api/mail/attachment/{identity}')
def mail_attachment(identity: str):
    snapshot = service.response()['data']
    if not snapshot or mailer.snapshot_id(snapshot) != identity:
        raise HTTPException(409, '데이터가 갱신되었습니다. 페이지를 새로고침하세요.')
    return FileResponse(mailer.workbook(snapshot, service.storage),
        filename=mailer.context(snapshot)['attachment'],
        headers={'Cache-Control': 'no-store'})


@app.get('/api/briefing')
def briefing():
    result = briefings.response(service.response()['data'])
    return JSONResponse(result, headers={'Cache-Control': 'no-store'})


@app.get('/api/dashboard')
def dashboard():
    result = service.response()
    result['mail'] = mailer.context(result['data']) if result['data'] else None
    return JSONResponse(result, status_code=200 if result['data'] else 202,
                        headers={'Cache-Control': 'no-store'})


@app.get('/')
def index():
    return FileResponse(HERE / 'static' / 'index.html', headers={'Cache-Control': 'no-cache'})


app.mount('/static', StaticFiles(directory=HERE / 'static'), name='static')
