"""One-use local phone pairing grants; no persistent credential is returned."""
import hmac
import secrets
import threading
import time

class PhonePairing:
    def __init__(self):
        self.lock=threading.Lock()
        self.code=None
        self.expires=0
        self.attempts=0
        self.last_created=float('-inf')

    def create(self):
        with self.lock:
            now=time.monotonic()
            if now-self.last_created<15:
                raise ValueError('Wait a few seconds before making another code.')
            self.code=f'{secrets.randbelow(1000000):06d}'
            self.expires=now+300
            self.attempts=0
            self.last_created=now
            return {'code':self.code,'expiresIn':300}

    def consume(self,value):
        with self.lock:
            if self.code is None or time.monotonic()>=self.expires or self.attempts>=5:
                self.code=None
                return False
            self.attempts+=1
            valid=isinstance(value,str) and len(value)==6 and value.isascii() and value.isdigit() and hmac.compare_digest(value,self.code)
            if valid or self.attempts>=5:self.code=None
            return valid
