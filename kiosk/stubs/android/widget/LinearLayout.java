package android.widget;
import android.view.ViewGroup;
import android.content.Context;
public class LinearLayout extends ViewGroup {
 public LinearLayout(Context context) { throw new RuntimeException(); }
 public void setOrientation(int orientation) { throw new RuntimeException(); }
 public void setBackgroundColor(int color) { throw new RuntimeException(); }
 public static class LayoutParams extends ViewGroup.LayoutParams {
  public LayoutParams(int width,int height) { super(width,height); }
  public LayoutParams(int width,int height,float weight) { super(width,height); }
 }
}
