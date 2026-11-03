"""SDK-01: actionable login failures must never expose codes, tokens or raw errors."""
import contextlib
import importlib
import io
import pathlib
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).parents[1]/'sdk'))
from scru_minecraft import GatewayError
cli=importlib.import_module('scru_minecraft.__main__')


class LoginCLITests(unittest.TestCase):
    code='synthetic-private-code-92583714'
    token='synthetic-private-issued-token-0123456789'

    def run_login(self,root,*,start_error=None,finish_error=None,response=None):
        destination=pathlib.Path(root)/'credentials.env'
        output=io.StringIO();errors=io.StringIO()
        with patch.object(sys,'argv',['scru_minecraft','login','FixtureUser','--output',str(destination)]),\
             patch.object(cli.AgentClient,'start_login',return_value={'request_id':'synthetic-challenge'},side_effect=start_error),\
             patch.object(cli.AgentClient,'finish_login',return_value=response or {'token':self.token},side_effect=finish_error),\
             patch.object(cli.getpass,'getpass',return_value=self.code),\
             contextlib.redirect_stdout(output),contextlib.redirect_stderr(errors):
            try:cli.main();status=0
            except SystemExit as error:status=error.code
        combined=output.getvalue()+errors.getvalue()
        self.assertNotIn(self.code,combined);self.assertNotIn(self.token,combined)
        self.assertNotIn('Traceback',combined)
        return status,combined,destination

    def test_expired_and_invalid_code_have_actionable_private_failure(self):
        for code,status,expected in [('enrollment_expired',410,'expired'),('invalid_code',401,'did not match')]:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as root:
                exit_code,text,destination=self.run_login(root,finish_error=GatewayError(status,code))
                self.assertEqual(1,exit_code);self.assertIn(expected,text);self.assertIn('new private code',text.replace('new code','new private code'))
                self.assertFalse(destination.exists())

    def test_unreachable_gateway_never_prints_raw_network_exception(self):
        with tempfile.TemporaryDirectory() as root:
            code,text,destination=self.run_login(root,start_error=urllib.error.URLError(self.code+' '+self.token))
            self.assertEqual(1,code);self.assertIn('Check your internet connection',text);self.assertFalse(destination.exists())

    def test_unknown_gateway_payload_is_not_displayed(self):
        with tempfile.TemporaryDirectory() as root:
            code,text,destination=self.run_login(root,finish_error=GatewayError(503,self.code+' '+self.token))
            self.assertEqual(1,code);self.assertIn('temporarily unavailable',text);self.assertFalse(destination.exists())

    def test_success_saves_private_token_without_printing_it(self):
        with tempfile.TemporaryDirectory() as root:
            code,text,destination=self.run_login(root)
            self.assertEqual(0,code);self.assertIn('Player access saved',text)
            self.assertIn('SCRU_AGENT_TOKEN='+self.token,destination.read_text())

    def test_invalid_credential_response_is_not_saved_or_displayed(self):
        with tempfile.TemporaryDirectory() as root:
            code,text,destination=self.run_login(root,response={'token':self.token+'\n'+self.code})
            self.assertEqual(1,code);self.assertIn('invalid response',text);self.assertFalse(destination.exists())
