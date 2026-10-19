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

    def test_embedded_panel_bounds_and_brightness_limits(self):
        source=Path(__file__).resolve().parents[1]/'kiosk/src/com/homehub/kiosk/PanelBounds.java'
        harness='''import com.homehub.kiosk.PanelBounds;
public class PanelCheck { public static void main(String[] args) {
 int[][] sizes={{1280,800,232,0,1048,800},{640,400,116,0,524,400},{1600,800,392,0,1048,800},{1280,1000,232,100,1048,800}};
 for(int[] test:sizes){int[] got=PanelBounds.at(test[0],test[1]);for(int i=0;i<4;i++)if(got[i]!=test[i+2])throw new AssertionError("sidebar overlap");}
 for(String bad:new String[]{"0","9","101","-1","NaN","70&url=x"}){try{PanelBounds.brightness(bad);throw new AssertionError("brightness out of bounds");}catch(IllegalArgumentException expected){}}
 if(PanelBounds.brightness("10")!=10 || PanelBounds.brightness("100")!=100)throw new AssertionError("boundary rejected");
 }}'''
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'PanelCheck.java';path.write_text(harness)
            subprocess.run(['javac','--release','8','-d',folder,str(source),str(path)],check=True,capture_output=True)
            subprocess.run(['java','-cp',folder,'PanelCheck'],check=True,capture_output=True)
