import io
import json
import time
from concurrent.futures import wait
import unittest
from concurrent.futures import Future
from urllib.error import HTTPError
from unittest.mock import patch
from govee import GoveeCloud
from integrations import SourceUnavailable

ENTRY={'sku':'H6008','device':'00:00:00:00:00:00:00:01','name':'Synthetic bulb'}

def payload(online=True,power=1):
    return {'code':200,'payload':{'sku':ENTRY['sku'],'device':ENTRY['device'],'capabilities':[
        {'type':'devices.capabilities.online','instance':'online','state':{'value':online}},
        {'type':'devices.capabilities.on_off','instance':'powerSwitch','state':{'value':power}}]}}

class GoveeTests(unittest.TestCase):
    def setUp(self):
        self.cloud=GoveeCloud([ENTRY], 'synthetic-govee-key')
        self.addCleanup(self.cloud.pool.shutdown,wait=True,cancel_futures=True)
        self.alias=self.cloud.alias(ENTRY)

    def test_fixed_https_header_auth_no_proxies_and_unknown_endpoints_rejected(self):
        with patch.object(self.cloud.transport,'open',return_value=io.BytesIO(json.dumps(payload()).encode())) as request:
            state=self.cloud.read(ENTRY)
        req=request.call_args.args[0]
        self.assertEqual(req.full_url,'https://openapi.api.govee.com/router/api/v1/device/state')
        self.assertEqual(req.get_header('Govee-api-key'),'synthetic-govee-key')
        self.assertTrue(state['available'])
        self.assertNotIn(ENTRY['device'],json.dumps(state))
        self.assertNotIn('synthetic-govee-key',json.dumps(state))
        with self.assertRaises(SourceUnavailable):self.cloud.request('https://example.invalid')

    def test_offline_or_unconfirmed_state_never_enables_control(self):
        for online,power in [(False,1),(None,1),(True,None),(True,'1')]:
            with patch.object(self.cloud,'request',return_value=payload(online,power)):
                self.assertFalse(self.cloud.read(ENTRY)['available'])
        wrong=payload();wrong['payload']['device']='00:00:00:00:00:00:00:02'
        with patch.object(self.cloud,'request',return_value=wrong):
            with self.assertRaises(SourceUnavailable):self.cloud.read(ENTRY)

    def test_cloud_outage_preserves_disabled_rows_and_backs_off(self):
        with patch.object(self.cloud,'request',side_effect=SourceUnavailable('offline')) as request:
            self.cloud.lights();wait(list(self.cloud.jobs.values()))
            one=self.cloud.lights();two=self.cloud.lights()
        self.assertEqual(one,two);self.assertFalse(one[0]['available'])
        self.assertEqual(request.call_count,1)

    def test_inflight_read_reused_and_never_overwrites_confirmed_command(self):
        pending=Future()
        self.cloud.jobs[self.alias]=pending;self.cloud.job_versions[self.alias]=0
        self.assertFalse(self.cloud.lights()[0]['available'])
        self.assertIs(self.cloud.jobs[self.alias],pending)
        before={'available':True,'on':False};after={'id':self.alias,'available':True,'on':True}
        with patch.object(self.cloud,'read',side_effect=[before,after]),patch.object(self.cloud,'request'):
            self.assertEqual(self.cloud.action({'kind':'light','id':self.alias,'on':True})['result'],'confirmed')
        pending.set_result({'id':self.alias,'available':True,'on':False})
        self.assertTrue(self.cloud.lights()[0]['on'])

    def test_command_requires_readback_and_no_arbitrary_capability(self):
        command={'kind':'light','id':self.alias,'on':True}
        with patch.object(self.cloud,'read',return_value={'available':True,'on':False}),patch.object(self.cloud,'request') as request:
            with self.assertRaisesRegex(SourceUnavailable,'not yet confirmed'):self.cloud.action(command)
        self.assertEqual(request.call_args.args[0],'device/control')
        self.assertEqual(request.call_args.args[1]['capability'],{'type':'devices.capabilities.on_off','instance':'powerSwitch','value':1})
        with self.assertRaises(ValueError):self.cloud.action(dict(command,kind='heater'))
        with self.assertRaises(ValueError):self.cloud.action(dict(command,on='true'))

    def test_429_cooldown_and_provider_errors_are_sanitized(self):
        error=HTTPError('https://private.invalid',429,'secret-provider-response',{},None)
        with patch.object(self.cloud.transport,'open',side_effect=error) as request:
            for _ in range(2):
                with self.assertRaises(SourceUnavailable) as caught:self.cloud.request('user/devices')
                self.assertNotIn('secret-provider-response',str(caught.exception))
            self.assertEqual(request.call_count,1)

    def test_limits_reject_invalid_configuration_and_large_responses(self):
        for entries in ([],[ENTRY]*5,[dict(ENTRY,sku='../escape')],[dict(ENTRY,device='https://example.invalid')]):
            with self.assertRaises(ValueError):GoveeCloud(entries,'synthetic')
        with patch.object(self.cloud.transport,'open',return_value=io.BytesIO(b'x'*1000001)):
            with self.assertRaises(SourceUnavailable):self.cloud.request('user/devices')

    def test_expired_pending_state_is_disabled_without_waiting(self):
        self.cloud.cache[self.alias]=(time.monotonic()-61,{'id':self.alias,'available':True,'on':True})
        pending=Future();self.cloud.jobs[self.alias]=pending;self.cloud.job_versions[self.alias]=0
        start=time.monotonic();lights=self.cloud.lights()
        self.assertLess(time.monotonic()-start,.1)
        self.assertFalse(lights[0]['available']);self.assertFalse(lights[0]['on'])
        self.assertEqual(self.cloud.health['state'],'failed')
        pending.set_result({'id':self.alias,'available':True,'on':False})
        self.assertTrue(self.cloud.lights()[0]['available'])
