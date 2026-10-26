"""Verify real Next.js/FastAPI HTTP integration with in-memory test persistence.

Run with the backend development venv after npm ci in apps/frontend.
This never connects to Atlas or configures production credentials.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[3]
FRONT = 'http://127.0.0.1:3200'
API = 'http://127.0.0.1:4200'
KEY = 'local-integration-fixture-only-not-a-production-secret'
checks = []


def check(name, condition):
    if not condition:
        raise AssertionError(name)
    checks.append(name)


fixture = '''
from contextlib import asynccontextmanager
from mongomock_motor import AsyncMongoMockClient
import main
from database.db import get_db
database = AsyncMongoMockClient().elegance_integration_test
app = main.create_app()
@asynccontextmanager
async def lifespan(app):
    yield
async def ready():
    return True
app.router.lifespan_context = lifespan
main.database_is_ready = ready
app.dependency_overrides[get_db] = lambda: database
'''

with tempfile.TemporaryDirectory() as temporary:
    temp = Path(temporary)
    (temp / 'fixture_backend.py').write_text(fixture)
    backend_env = dict(os.environ, MONGODB_URI='mongodb://localhost/test-fixture-only', MONGO_DB_NAME='elegance_integration_test',
                       ADMIN_API_KEY=KEY, ALLOWED_ORIGINS=FRONT, PYTHONPATH=str(ROOT / 'apps/backend'))
    frontend_env = dict(os.environ, ADMIN_API_KEY=KEY, NEXT_PUBLIC_API_URL=API, NEXT_PUBLIC_SITE_URL=FRONT,
                        NEXT_PUBLIC_WHATSAPP_NUMBER='923001234567')
    backend = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'fixture_backend:app', '--app-dir', str(temp), '--host', '127.0.0.1', '--port', '4200'],
                               cwd=ROOT / 'apps/backend', env=backend_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    frontend = subprocess.Popen(['npm', 'run', 'dev', '--', '--hostname', '127.0.0.1', '--port', '3200'],
                                cwd=ROOT / 'apps/frontend', env=frontend_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        with httpx.Client(base_url=FRONT, timeout=20, trust_env=False) as web, httpx.Client(base_url=API, timeout=10, trust_env=False) as api:
            for _ in range(45):
                try:
                    if web.get('/api/health').status_code == 200 and api.get('/health/').status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                raise RuntimeError('local services did not become healthy')
            check('frontend-to-backend readiness', web.get('/api/ready').status_code == 200)
            check('anonymous proxy access rejected', web.get('/api/admin/products').status_code == 401)
            check('malformed cookie rejected', web.get('/api/admin/products', headers={'cookie':'es_admin_session=%E0%A4%A'}).status_code == 401)
            check('wrong login rejected', web.post('/api/admin/session', json={'key':'wrong'}).status_code == 401)
            login = web.post('/api/admin/session', json={'key':KEY})
            check('admin login accepted', login.status_code == 200)
            check('session cookie HttpOnly and SameSite', 'HttpOnly' in login.headers.get('set-cookie','') and 'SameSite=lax' in login.headers.get('set-cookie',''))
            check('private key absent from login response', KEY not in login.text)
            payload = {'name':'Integration Shawl','slug':'integration-shawl','cover_image_url':'https://images.example.com/test.jpg',
                       'category':'shawls','status':'draft','item_number':'E2E-ONLY',
                       'variants':[{'name':'Blue','color':'Blue','size':'Free Size','image_url':'https://images.example.com/test.jpg','price':4500,'stock':2}]}
            created = web.post('/api/admin/products', json=payload)
            check('create through authenticated frontend proxy', created.status_code == 201)
            data = created.json()
            product_id, variant_id = data['_id'], data['variants'][0]['_id']
            check('draft hidden from public catalog', api.get('/products/').json()['items'] == [])
            payload['name'] = 'Edited Integration Shawl'
            edited = web.put('/api/admin/products/' + product_id, json=payload)
            check('edit persisted through proxy', edited.status_code == 200 and edited.json()['name'] == payload['name'])
            variant_id = edited.json()['variants'][0]['_id']
            published = web.patch('/api/admin/products/' + product_id + '/status', json={'status':'active'})
            check('publish through proxy', published.status_code == 200)
            public = api.get('/products/slug/integration-shawl')
            check('public API sees published product, image and SKU', public.status_code == 200 and public.json()['item_number'] == 'E2E-ONLY' and public.json()['cover_image_url'] == payload['cover_image_url'])
            stock = web.patch('/api/admin/products/' + product_id + '/stock', json={'variant_id':variant_id,'stock':0})
            check('stock update persisted', stock.status_code == 200 and stock.json()['variants'][0]['stock'] == 0)
            check('out-of-stock status propagated', api.get('/products/slug/integration-shawl').json()['variants'][0]['stock_status'] == 'Out of stock')
            archived = web.delete('/api/admin/products/' + product_id)
            check('archive through proxy', archived.status_code == 200 and archived.json()['status'] == 'archived')
            check('archive hidden from public catalog', api.get('/products/slug/integration-shawl').status_code == 404)
            cors = api.options('/products/', headers={'Origin':FRONT,'Access-Control-Request-Method':'GET'})
            check('configured CORS origin accepted', cors.headers.get('access-control-allow-origin') == FRONT)
            denied = api.options('/products/', headers={'Origin':'https://untrusted.example.invalid','Access-Control-Request-Method':'GET'})
            check('untrusted CORS origin rejected', denied.status_code == 400 and 'access-control-allow-origin' not in denied.headers)
            web.delete('/api/admin/session')
            check('logout revokes proxy access', web.get('/api/admin/products').status_code == 401)
            print(json.dumps({'passed':len(checks),'checks':checks,'persistence':'mongomock; not live Atlas','services':'real Next.js and FastAPI HTTP servers'}))
    except Exception as exc:
        print(json.dumps({'passed':len(checks),'failed':str(exc)}))
        raise SystemExit(1)
    finally:
        backend.terminate()
        import signal
        os.killpg(frontend.pid, signal.SIGTERM)
        backend.wait(timeout=10)
        frontend.wait(timeout=10)
