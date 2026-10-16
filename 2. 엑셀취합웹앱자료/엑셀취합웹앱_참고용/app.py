import os
import re
import smtplib
import uuid
from email.message import EmailMessage
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
import io

from excel_merge import build_workbook, process

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(BASE_DIR))
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

RESULTS = {}


def load_env():
    path = BASE_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env()


def default_mail(stats, report, branch_rows):
    lines = [
        "안녕하세요.",
        "",
        "3분기 지점별 판매실적을 취합했습니다. 결과 파일을 첨부합니다.",
        "",
        f"- 정리결과 {stats['정리결과 행']:,}건 / 총 수량 {stats['총 수량']:,}대 / 총 판매금액 {stats['총 판매금액']:,}원",
        f"- 검증에서 제외한 행 {stats['제외한 행']}건, 금액을 수정한 행 {stats['금액 수정 행']}건 (검증리포트 시트 참고)",
        "",
        "[지점별 합계]",
    ]
    for row in branch_rows:
        lines.append(f"- {row['지점']}: {row['합계 건수']}건 / {row['합계 수량']:,}대 / {row['합계 판매금액']:,}원")
    return "\n".join(lines)


@app.get("/")
def index():
    return render_template("index.html", sender=os.environ.get("EMAIL_ADDRESS", ""))


@app.post("/api/merge")
def merge():
    uploads = [f for f in request.files.getlist("files") if f.filename]
    if not uploads:
        return jsonify(error="엑셀 파일을 선택해 주세요."), 400
    files = []
    for f in uploads:
        if not f.filename.lower().endswith(".xlsx"):
            return jsonify(error=f"{f.filename}: .xlsx 파일만 올릴 수 있습니다."), 400
        files.append((Path(f.filename).name, f.read()))
    try:
        result = process(files)
    except Exception as exc:
        return jsonify(error=f"파일을 읽는 중 오류가 났습니다: {exc}"), 400
    if not result["records"]:
        return jsonify(error="취합할 수 있는 판매 데이터를 찾지 못했습니다."), 400
    token = uuid.uuid4().hex
    RESULTS[token] = build_workbook(result)
    if len(RESULTS) > 20:
        RESULTS.pop(next(iter(RESULTS)))
    return jsonify(
        token=token,
        stats=result["stats"],
        months=result["months"],
        branch_rows=result["branch_rows"],
        product_rows=result["product_rows"],
        report=result["report"],
        files=[name for name, _ in files],
        mail_subject="[영업관리팀] 3분기 지점별 판매실적 취합 결과",
        mail_body=default_mail(result["stats"], result["report"], result["branch_rows"]),
    )


@app.get("/api/download/<token>")
def download(token):
    data = RESULTS.get(token)
    if data is None:
        return "결과가 없습니다. 다시 취합해 주세요.", 404
    return send_file(io.BytesIO(data), as_attachment=True, download_name="정리결과.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.post("/api/send")
def send():
    payload = request.get_json(silent=True) or {}
    data = RESULTS.get(payload.get("token"))
    if data is None:
        return jsonify(error="취합 결과가 없습니다. 먼저 취합을 실행해 주세요."), 400
    sender = os.environ.get("EMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        return jsonify(error=".env 파일에 EMAIL_ADDRESS와 GMAIL_APP_PASSWORD를 입력해 주세요."), 400
    recipients = [r for r in re.split(r"[,\s;]+", payload.get("to", "")) if r]
    if not recipients or not all(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", r) for r in recipients):
        return jsonify(error="받는 사람 메일 주소를 확인해 주세요."), 400

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = payload.get("subject") or "엑셀 취합 결과"
    msg.set_content(payload.get("body") or "")
    msg.add_attachment(data, maintype="application",
                       subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       filename="정리결과.xlsx")
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    try:
        if os.environ.get("SMTP_PLAIN") == "1":
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "25"))) as smtp:
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, 465) as smtp:
                smtp.login(sender, password)
                smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return jsonify(error="로그인에 실패했습니다. 앱 비밀번호(16자리)와 메일 주소를 확인해 주세요."), 400
    except Exception as exc:
        return jsonify(error=f"메일 전송 중 오류가 났습니다: {exc}"), 500
    return jsonify(ok=True, to=recipients)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
