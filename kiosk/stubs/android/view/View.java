package android.view;
public class View {
 public int getWidth(){throw new RuntimeException();}
 public int getHeight(){throw new RuntimeException();}
 protected void onSizeChanged(int w,int h,int oldw,int oldh){}
 public void setLayoutParams(ViewGroup.LayoutParams p){throw new RuntimeException();}
 public void setBackgroundColor(int color){throw new RuntimeException();}
 public boolean requestFocus() { throw new RuntimeException(); }
 public android.os.IBinder getWindowToken() { throw new RuntimeException(); }
 public void setSystemUiVisibility(int visibility) { throw new RuntimeException(); }
 public void setOnClickListener(OnClickListener listener) { throw new RuntimeException(); }
 public void setEnabled(boolean enabled) { throw new RuntimeException(); }
 public interface OnClickListener { void onClick(View view); }
}
