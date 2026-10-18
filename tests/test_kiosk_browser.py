"""Compile/run the actual pure Java native-browser policy; no Android or network."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('javac') and shutil.which('java'), 'Java compiler required for native policy contract')
class BrowserPolicyTests(unittest.TestCase):
    def test_public_web_policy_search_and_pairing_origin_separation(self):
        source=Path(__file__).resolve().parents[1]/'kiosk/src/com/homehub/kiosk/BrowserPolicy.java'
        harness=r'''
import com.homehub.kiosk.BrowserPolicy;
public class BrowserPolicyCheck {
 public static void main(String[] args) {
  String[] blocked={"http://example.com", "file:///etc/passwd", "content://private", "javascript:alert(1)",
   "intent://example", "https://127.0.0.1", "https://192.168.1.1", "https://169.254.1.1", "https://[::1]",
   "https://[::ffff:8.8.8.8]", "https://[fc00::1]", "https://[fd12::1]",
   "https://0177.0.0.1", "https://100.64.0.1", "https://0x7f.0.0.1", "https://127.0x0.0.1",
   "https://example.local.", "https://localhost.", "https://2130706433", "https://example.local", "https://localhost", "https://example.com:8123",
   "https://" + "user:" + "example@example.com", "https://example.com/\n", "https://example.com\\@127.0.0.1"};
  for(String url:blocked) if(BrowserPolicy.isPublicHttps(url))throw new AssertionError("accepted blocked URL");
  if(!BrowserPolicy.isPublicHttps("https://example.com/recipe?q=1"))throw new AssertionError("public URL rejected");
  if(!BrowserPolicy.destination("pasta & tomatoes").equals("https://duckduckgo.com/?q=pasta+%26+tomatoes"))throw new AssertionError("query encoding");
  if(!BrowserPolicy.destination("example.com/recipe").equals("https://example.com/recipe"))throw new AssertionError("website address");
  if(!BrowserPolicy.origin("http://127.0.0.1:8099/pair?token=synthetic").equals("http://127.0.0.1:8099"))throw new AssertionError("pairing data crossed origin boundary");
  try {BrowserPolicy.destination("http://127.0.0.1");throw new AssertionError("unsafe address became search");}catch(IllegalArgumentException expected){}
 }
}
'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'BrowserPolicyCheck.java';path.write_text(harness)
            subprocess.run(['javac','--release','8','-d',folder,str(source),str(path)],check=True,capture_output=True)
            subprocess.run(['java','-cp',folder,'BrowserPolicyCheck'],check=True,capture_output=True)
