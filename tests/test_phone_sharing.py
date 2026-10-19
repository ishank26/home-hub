import unittest
from unittest.mock import patch
from phone_sharing import PhonePairing

class PairTests(unittest.TestCase):
    def test_one_use_and_does_not_disclose_persistent_token(self):
        p=PhonePairing();r=p.create()
        self.assertEqual(set(r),{'code','expiresIn'})
        self.assertEqual(len(r['code']),6)
        self.assertTrue(p.consume(r['code']))
        self.assertFalse(p.consume(r['code']))
    def test_global_attempt_limit_and_no_recreation_flood(self):
        p=PhonePairing();r=p.create()
        wrong='000000' if r['code']!='000000' else '111111'
        for _ in range(5):self.assertFalse(p.consume(wrong))
        self.assertFalse(p.consume(r['code']))
        with self.assertRaises(ValueError):p.create()
    def test_expiry_and_new_code_revokes_old(self):
        with patch('phone_sharing.time.monotonic',return_value=10):
            p=PhonePairing();old=p.create()['code']
        with patch('phone_sharing.time.monotonic',return_value=311):
            self.assertFalse(p.consume(old))
            new=p.create()['code']
            self.assertTrue(p.consume(new))
    def test_malformed_codes_spend_attempt(self):
        p=PhonePairing();r=p.create()
        for v in (None,{},'1234567','１２３４５６','abc'):
            self.assertFalse(p.consume(v))
        self.assertFalse(p.consume(r['code']))

class AdmissionTests(unittest.TestCase):
    def test_unpaired_shell_then_single_use_admission(self):
        import server, tempfile, threading, ipaddress, urllib.request, urllib.error, json
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            handler=server.make_handler(server.Hub(server.Store(Path(d))),[ipaddress.ip_network('192.168.68.0/24')],'fixture-only-admission-token')
            class Remote(handler):
                def setup(self):
                    super().setup();self.client_address=('192.168.68.99',self.client_address[1])
            s=server.ThreadingHTTPServer(('127.0.0.1',0),Remote)
            t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
            self.addCleanup(s.server_close);self.addCleanup(s.shutdown)
            base='http://127.0.0.1:'+str(s.server_port)
            def call(path,body=None,cookie=None,content='application/json'):
                h={'Content-Type':content}
                if cookie:h['Cookie']=cookie
                req=urllib.request.Request(base+path,headers=h,data=None if body is None else json.dumps(body).encode())
                try:return urllib.request.urlopen(req)
                except urllib.error.HTTPError as e:return e
            with call('/phone/') as r:self.assertEqual(r.status,200);self.assertEqual(r.headers['Cache-Control'],'no-store')
            with call('/api/recipes') as r:self.assertEqual(r.code,403)
            with call('/api/phone/code',{}) as r:self.assertEqual(r.code,403)
            with call('/api/phone/code',{},'hub_device=fixture-only-admission-token') as r:code=json.load(r)['code']
            with call('/api/phone/pair',{'code':code},content='text/plain') as r:self.assertEqual(r.code,400)
            with call('/api/phone/pair',{'code':code}) as r:
                self.assertEqual(r.status,200);cookie=r.headers['Set-Cookie'];self.assertIn('HttpOnly',cookie);self.assertIn('SameSite=Strict',cookie)
            with call('/api/recipes',cookie=cookie.split(';')[0]) as r:self.assertEqual(r.status,200)
            with call('/api/phone/pair',{'code':code}) as r:self.assertEqual(r.code,403)
