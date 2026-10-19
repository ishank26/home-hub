package android.view;
public class ViewGroup extends View {
 public void removeView(View v){throw new RuntimeException();}
 public void addView(View view, LayoutParams params) { throw new RuntimeException(); }
 public static class LayoutParams { public LayoutParams(int width,int height) { throw new RuntimeException(); } }
}
