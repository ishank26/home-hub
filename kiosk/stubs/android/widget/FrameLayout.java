package android.widget;
public class FrameLayout extends android.view.ViewGroup {
 public FrameLayout(android.content.Context c){throw new RuntimeException();}
 public static class LayoutParams extends android.view.ViewGroup.LayoutParams {
  public int leftMargin,topMargin;
  public LayoutParams(int w,int h){super(w,h);}
 }
}
