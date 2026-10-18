package android.view;
public class View {
 public boolean requestFocus() { throw new RuntimeException(); }
 public android.os.IBinder getWindowToken() { throw new RuntimeException(); }
 public void setSystemUiVisibility(int visibility) { throw new RuntimeException(); }
 public void setOnClickListener(OnClickListener listener) { throw new RuntimeException(); }
 public void setEnabled(boolean enabled) { throw new RuntimeException(); }
 public interface OnClickListener { void onClick(View view); }
}
