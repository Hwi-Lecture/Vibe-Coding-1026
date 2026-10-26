"""Send the completed Excel workbook using Gmail SMTP (Python standard library only).

.env settings (in the same folder as this script):
    email_address=your Gmail address
    gmail_app_password=your Gmail app password

Examples:
    python send_opinet_email.py --to recipient@example.com --dry-run
    python send_opinet_email.py --to recipient@example.com
    python send_opinet_email.py --to first@example.com second@example.com --file "report.xlsx"

When --file is omitted, use the latest data/opinet/YYYY-MM-DD/유가_기간비교.xlsx.
--dry-run prepares and checks the message without connecting to Gmail.
"""

import argparse
import os
import smtplib
import ssl
import sys
import zipfile
from datetime import date
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_settings():
    settings = {}
    project_root = ROOT.parent.parent if ROOT.parent.name == 'checkpoint' else ROOT.parent
    for env_file in dict.fromkeys([project_root / '.env', ROOT / '.env']):
        if env_file.is_file():
            for line in env_file.read_text(encoding='utf-8-sig').splitlines():
                if '=' in line and not line.lstrip().startswith('#'):
                    key, value = line.split('=', 1)
                    settings[key.strip().lower()] = value.strip().strip(chr(34)).strip(chr(39))
    sender = os.environ.get('EMAIL_ADDRESS') or settings.get('email_address', '')
    password = os.environ.get('GMAIL_APP_PASSWORD') or settings.get('gmail_app_password', '')
    # Google displays app passwords in groups separated by spaces.
    password = ''.join(password.split())
    if not sender or not password:
        raise ValueError('.env에 email_address와 gmail_app_password를 설정하세요.')
    validate_address(sender)
    return sender, password


def validate_address(value):
    if '\r' in value or '\n' in value:
        raise ValueError('이메일 주소에 줄바꿈을 사용할 수 없습니다.')
    try:
        parsed = Address(addr_spec=value)
        if not parsed.username or not parsed.domain:
            raise ValueError
        value.encode('ascii')
    except (ValueError, IndexError, UnicodeError):
        raise ValueError('이메일 주소를 name@example.com 형식으로 입력하세요.') from None


def latest_workbook():
    candidates = []
    for file in (ROOT / 'data' / 'opinet').glob('*/유가_기간비교.xlsx'):
        try:
            collected_date = date.fromisoformat(file.parent.name)
        except ValueError:
            continue
        if file.is_file():
            candidates.append((collected_date, file))
    if not candidates:
        raise FileNotFoundError('완성된 엑셀이 없습니다. --file로 첨부할 파일을 지정하세요.')
    return max(candidates)[1]


def build_message(sender, recipients, attachment, subject=None, body=None):
    if not attachment.is_file():
        raise FileNotFoundError('첨부할 엑셀 파일을 찾을 수 없습니다.')
    if attachment.suffix.lower() != '.xlsx' or not zipfile.is_zipfile(attachment):
        raise ValueError('첨부파일은 정상적인 .xlsx 파일이어야 합니다.')
    with zipfile.ZipFile(attachment) as archive:
        if 'xl/workbook.xml' not in archive.namelist():
            raise ValueError('첨부파일에 엑셀 통합문서가 없습니다.')
    message = EmailMessage()
    message['From'] = sender
    message['To'] = ', '.join(recipients)
    message['Subject'] = subject if subject is not None else '오피넷 유가 기간별 비교 자료'
    message['Date'] = formatdate(localtime=True)
    message['Message-ID'] = make_msgid()
    message.set_content(body if body is not None else (
        '안녕하세요.\n\n오피넷 유가 기간별 비교 엑셀 파일을 첨부합니다.\n'
        '파일에는 기간별 비교, 전국 일별, 상표별 일별, 지역별 일별 자료가 담겨 있습니다.\n\n감사합니다.\n'))
    message.add_attachment(
        attachment.read_bytes(),
        maintype='application',
        subtype='vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        filename=attachment.name,
    )
    return message


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--to', required=True, nargs='+', help='받는 이메일 주소 (여러 명은 공백 또는 쉼표로 구분)')
    parser.add_argument('--file', type=Path, help='첨부할 .xlsx 경로 (생략하면 가장 최근 기준일의 완성된 엑셀)')
    parser.add_argument('--subject', help='메일 제목')
    parser.add_argument('--body', help='메일 본문')
    parser.add_argument('--dry-run', action='store_true', help='메일 구성만 확인하고 전송하지 않음')
    args = parser.parse_args()
    try:
        recipients = list(dict.fromkeys(address.strip() for item in args.to
                                        for address in item.split(',') if address.strip()))
        if not recipients:
            raise ValueError('받는 이메일 주소를 입력하세요.')
        for recipient in recipients:
            validate_address(recipient)
        sender, password = load_settings()
        attachment = args.file.expanduser().resolve() if args.file else latest_workbook()
        message = build_message(sender, recipients, attachment, args.subject, args.body)
        print(f'첨부파일: {attachment}')
        print(f'받는 사람: {", ".join(recipients)}')
        print(f'제목: {message["Subject"]}')
        if args.dry_run:
            print('구성 확인 완료. Gmail 연결과 메일 전송은 하지 않았습니다.')
            return 0
        # Implicit TLS: encrypted connection from the start; do not enable SMTP debug logs.
        with smtplib.SMTP_SSL('smtp.gmail.com', 465,
                             context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(sender, password)
            rejected = smtp.send_message(message, from_addr=sender, to_addrs=recipients)
        if rejected:
            print('일부 수신자가 거부되었습니다. 나머지 수신자에게는 발송되었을 수 있으므로 전체 재전송하지 마세요.', file=sys.stderr)
            return 1
        print('Gmail SMTP 서버가 메일을 접수했습니다.')
        return 0
    except smtplib.SMTPAuthenticationError:
        print('Gmail 인증 실패: email_address와 gmail_app_password를 확인하세요.', file=sys.stderr)
    except smtplib.SMTPRecipientsRefused:
        print('Gmail 서버가 받는 사람을 거부했습니다. 주소를 확인하세요.', file=sys.stderr)
    except (TimeoutError, ConnectionError, smtplib.SMTPServerDisconnected):
        print('SMTP 연결이 중단되었습니다. 전송 여부가 불확실할 수 있으니 보낸메일함을 확인하세요.', file=sys.stderr)
    except (ValueError, FileNotFoundError) as exc:
        print(f'오류: {exc}', file=sys.stderr)
    except Exception as exc:
        # Avoid logging server responses, credentials, or connection details.
        print(f'메일 처리 실패 ({type(exc).__name__}). 설정과 연결 상태를 확인하세요.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
