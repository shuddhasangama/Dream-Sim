r"""Load journeys for the member API (c-scale-budget). LOCAL OR STAGING ONLY.

Never point this at production. Sign-in uses the local harness
(/api/v1/dev/login-as), which exists only on a local backend with
DHASHU_LOCAL_HARNESS=1. A staging run needs a staging-only sign-in path; see
docs/SCALING.md, "Staging run plan".

Local smoke (backend on 127.0.0.1:5000 against dhashu_load):
    .venv\\Scripts\\locust.exe -f tools\\load_test\\locustfile.py --headless ^
        -u 60 -r 10 -t 2m --host http://127.0.0.1:5000 --csv %TEMP%\\dhashu-load

Weights mirror a member's day: mostly Home and the week, some REACH/profile,
occasional Guru and token refresh.
"""
import os
import random

from locust import HttpUser, between, task

MEMBERS = int(os.environ.get('LOAD_MEMBERS', '1600'))


class Member(HttpUser):
    wait_time = between(1, 4)

    def on_start(self):
        if not self.host or not any(h in self.host for h in ('127.0.0.1', 'localhost', 'staging')):
            raise RuntimeError('Refusing to load-test a non-local, non-staging host.')
        self.user_id = 'u_%04d' % random.randint(1, MEMBERS)
        response = self.client.post('/api/v1/dev/login-as', json={'user_id': self.user_id}, name='login')
        data = (response.json() or {}).get('data') or {}
        self.refresh_token = data.get('refresh_token')
        self.headers = {'Authorization': 'Bearer ' + data.get('access_token', ''), 'Accept-Encoding': 'gzip'}

    def get(self, path, name):
        self.client.get(path, headers=self.headers, name=name)

    @task(6)
    def home(self):
        self.get('/api/v1/journey/status', 'home: journey/status')
        self.get('/api/v1/profile', 'home: profile')

    @task(3)
    def week(self):
        self.get('/api/v1/week', 'week')

    @task(3)
    def reach(self):
        self.get('/api/v1/reach', 'reach')

    @task(2)
    def profile(self):
        self.get('/api/v1/profile/stats', 'profile/stats')

    @task(1)
    def guru(self):
        self.get('/api/v1/guru/state', 'guru')

    @task(1)
    def refresh(self):
        if not self.refresh_token:
            return
        response = self.client.post('/api/v1/dev/refresh', json={'refresh_token': self.refresh_token}, name='session refresh')
        data = (response.json() or {}).get('data') or {}
        if data.get('access_token'):
            self.refresh_token = data['refresh_token']
            self.headers['Authorization'] = 'Bearer ' + data['access_token']
