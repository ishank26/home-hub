// Compile-only stub: never packaged. The real class comes from the device framework.
package android.app;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.view.MotionEvent;
import android.view.View;
import android.view.Window;
public class Activity extends Context {
    public Object getSystemService(String name) { throw new RuntimeException(); }
    protected void onCreate(Bundle savedInstanceState) { throw new RuntimeException(); }
    protected void onNewIntent(Intent intent) { throw new RuntimeException(); }
    protected void onResume() { throw new RuntimeException(); }
    protected void onPause() { throw new RuntimeException(); }
    protected void onDestroy() { throw new RuntimeException(); }
    public void onWindowFocusChanged(boolean hasFocus) { throw new RuntimeException(); }
    public boolean dispatchTouchEvent(MotionEvent ev) { throw new RuntimeException(); }
    public void onBackPressed() { throw new RuntimeException(); }
    public Window getWindow() { throw new RuntimeException(); }
    public Intent getIntent() { throw new RuntimeException(); }
    public SharedPreferences getSharedPreferences(String name, int mode) { throw new RuntimeException(); }
    public void setContentView(View view) { throw new RuntimeException(); }
    public void finish() { throw new RuntimeException(); }
    public void startActivityForResult(Intent intent, int request) { throw new RuntimeException(); }
    public void setResult(int result, Intent intent) { throw new RuntimeException(); }
    protected void onActivityResult(int request, int result, Intent intent) { throw new RuntimeException(); }
    public void startActivity(Intent intent) { throw new RuntimeException(); }
}
