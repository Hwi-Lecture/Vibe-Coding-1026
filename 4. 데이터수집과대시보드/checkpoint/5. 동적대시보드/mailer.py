"""Draft mail, export the displayed snapshot and send only on explicit POST."""
import hashlib
import json
import os
import smtplib
import ssl
from datetime import date
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path
from settings import env_values

from filelock import FileLock, Timeout
from briefing import basic_summary, generate, load_settings, summarize
from service import HERE, now, read_json, write_json

DRAFT_INSTRUCTIONS = '''유가 기간 비교 엑셀을 공유하는 업무용 한국어 이메일 본문을 작성하세요.
제공한 집계 데이터만 사용하고 인사, 실제 비교 기간, 전국 실내등유·휘발유·경유 평균과 증감,
첨부 엑셀에 전국·상표·지역별 일별 자료와 기간 비교가 있다는 설명, 맺음말을 포함하세요.
최근 7일과 직전 7일을 달력상 이번 주/지난주로 단정하지 마세요.
가격은 소수 둘째 자리, 수치는 재계산하지 말고 원인·전망·절감 효과를 추측하지 마세요.
수신자·발신자 이름이나 회사는 지어내지 마세요. 제목·마크다운 없이 1000자 이내 평문으로 작성하세요.'''


class MailError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def snapshot_id(snapshot):
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def validate_address(value):
    if '\r' in value or '\n' in value:
        raise MailError('이메일 주소에 줄바꿈을 사용할 수 없습니다.')
    try:
        address = Address(addr_spec=value)
        value.encode('ascii')
        if not address.username or not address.domain or '@' not in value:
            raise ValueError()
    except (ValueError, UnicodeError, IndexError):
        raise MailError('받는 주소를 name@example.com 형식으로 입력하세요.') from None


def smtp_settings():
    values = env_values()
    sender = os.environ.get('EMAIL_ADDRESS') or values.get('email_address', '')
    password = os.environ.get('GMAIL_APP_PASSWORD') or values.get('gmail_app_password', '')
    if not sender or not password:
        raise MailError('.env에 email_address와 gmail_app_password를 설정하세요.', 503)
    validate_address(sender)
    return sender, ''.join(password.split())


def context(snapshot):
    periods = snapshot['periods']
    return {'snapshot_id': snapshot_id(snapshot), 'as_of': snapshot['as_of'],
            'subject': f"유가 기간 비교 자료 ({periods['recent']['start']} ~ {periods['recent']['end']})",
            'attachment': f"유가_기간비교_{snapshot['as_of']}.xlsx",
            'periods': periods}


def draft(snapshot):
    summary = summarize(snapshot)
    key, model = load_settings()
    if key:
        try:
            text = generate(summary, key, model, instructions=DRAFT_INSTRUCTIONS, max_output_tokens=1800)
        except Exception:
            raise MailError('AI 초안을 생성하지 못했습니다. API 키와 모델 이용 가능 여부를 확인하세요.', 502) from None
        source = 'openai'
    else:
        recent, previous = summary['periods']['recent'], summary['periods']['previous']
        text = (f"안녕하세요.\n\n유가 기간별 비교 자료를 공유드립니다.\n"
                f"최근 기간: {recent['start']} ~ {recent['end']}\n"
                f"직전 기간: {previous['start']} ~ {previous['end']}\n\n"
                + basic_summary(summary) + '\n\n첨부 엑셀에는 기간별 비교와 전국·상표·지역별 일별 자료가 포함되어 있습니다. '
                '가격은 각 기간의 유효한 7일 평균이며 실제 구매·배달 가격과 다를 수 있습니다.\n\n확인 부탁드립니다. 감사합니다.')
        source = 'template'
    return {**context(snapshot), 'body': text, 'source': source}


def workbook(snapshot, storage):
    # Keep the existing project's Excel layout and formulas via the copied exporter.
    from excel_report import build_workbook
    identity = snapshot_id(snapshot)
    output = Path(storage) / 'exports' / identity / context(snapshot)['attachment']
    output.parent.mkdir(parents=True, exist_ok=True)
    with FileLock(str(output) + '.lock', timeout=15):
        if not output.exists():
            build_workbook(snapshot, output)
    return output


def message(snapshot, recipient, subject, body, attachment, sender):
    mail = EmailMessage()
    mail['From'], mail['To'], mail['Subject'] = sender, recipient, subject
    mail['Date'], mail['Message-ID'] = formatdate(localtime=True), make_msgid()
    mail.set_content(body)
    mail.add_attachment(attachment.read_bytes(), maintype='application',
        subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=attachment.name)
    return mail


def send(snapshot, storage, recipient, subject, body, request_id):
    validate_address(recipient)
    if not subject.strip() or '\n' in subject or '\r' in subject:
        raise MailError('메일 제목을 확인하세요.')
    if not body.strip():
        raise MailError('메일 내용을 입력하세요.')
    sender, password = smtp_settings()
    identity = snapshot_id(snapshot)
    record_path = Path(storage) / 'mail' / (request_id + '.json')
    record_path.parent.mkdir(parents=True, exist_ok=True)
    payload_hash = hashlib.sha256(json.dumps([identity, recipient, subject, body], ensure_ascii=False).encode()).hexdigest()
    try:
        with FileLock(str(record_path) + '.lock', timeout=0):
            if record_path.exists():
                record = read_json(record_path)
                if record.get('payload_hash') != payload_hash:
                    raise MailError('전송 요청이 변경되었습니다. 내용을 확인하고 다시 시도하세요.', 409)
                if record.get('status') == 'sent':
                    return {'message': '이미 메일 서버가 접수한 요청입니다. 중복 전송하지 않았습니다.', 'status': 'sent'}
                raise MailError('이 요청의 전송 여부를 확인해야 합니다. 보낸메일함을 확인하세요.', 409)
            attachment = workbook(snapshot, storage)
            mail = message(snapshot, recipient, subject, body, attachment, sender)
            # Persist before SMTP: ambiguous network failures must never auto-resend.
            write_json(record_path, {'status': 'pending', 'payload_hash': payload_hash, 'created_at': now().isoformat()})
            try:
                with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ssl.create_default_context(), timeout=30) as smtp:
                    smtp.login(sender, password)
                    refused = smtp.send_message(mail, from_addr=sender, to_addrs=[recipient])
                if refused:
                    raise smtplib.SMTPRecipientsRefused(refused)
            except smtplib.SMTPAuthenticationError:
                record_path.unlink(missing_ok=True)
                raise MailError('Gmail 인증에 실패했습니다. 발신 주소와 앱 비밀번호를 확인하세요.', 502) from None
            except smtplib.SMTPRecipientsRefused:
                record_path.unlink(missing_ok=True)
                raise MailError('메일 서버가 수신 주소를 거부했습니다.', 502) from None
            except Exception:
                write_json(record_path, {'status': 'unknown', 'payload_hash': payload_hash})
                raise MailError('전송 결과를 확인하지 못했습니다. 재전송 전에 보낸메일함을 확인하세요.', 502) from None
            write_json(record_path, {'status': 'sent', 'payload_hash': payload_hash, 'sent_at': now().isoformat()})
            return {'message': '엑셀을 첨부한 메일을 Gmail 서버가 접수했습니다.', 'status': 'sent'}
    except Timeout:
        raise MailError('같은 메일을 전송 중입니다. 잠시 기다려주세요.', 409) from None
