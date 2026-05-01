import os
import base64
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
SAVE_DIR = r"C:\Scripts\gmail-parser\bills"

os.makedirs(SAVE_DIR, exist_ok=True)

# Авторизация
creds = None
if os.path.exists('token.json'):
    creds = Credentials.from_authorized_user_file('token.json', SCOPES)
else:
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open('token.json', 'w') as f:
        f.write(creds.to_json())

service = build('gmail', 'v1', credentials=creds)

# Получаем список писем
results = service.users().messages().list(
    userId='me',
    q='from:noreply@eda.yandex.ru'
).execute()

messages = results.get('messages', [])
print(f'Найдено писем: {len(messages)}')

# Скачиваем вложения
for msg_ref in messages:
    msg = service.users().messages().get(userId='me', id=msg_ref['id']).execute()
    
    parts = msg['payload'].get('parts', [])
    for part in parts:
        filename = part.get('filename', '')
        if not filename:
            continue
        
        body = part.get('body', {})
        att_id = body.get('attachmentId')
        if not att_id:
            continue
        
        att = service.users().messages().attachments().get(
            userId='me', messageId=msg_ref['id'], id=att_id
        ).execute()
        
        data = base64.urlsafe_b64decode(att['data'])
        name, ext = os.path.splitext(filename)
        counter = 1
        filepath = os.path.join(SAVE_DIR, f"{name}_{counter}{ext}")
        while os.path.exists(filepath):
            counter += 1
            filepath = os.path.join(SAVE_DIR, f"{name}_{counter}{ext}")

        with open(filepath, 'wb') as f:
            f.write(data)
        print(f'Сохранено: {filepath}')

print('Готово!')