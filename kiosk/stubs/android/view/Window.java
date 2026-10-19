// Compile-only stub: never packaged. The real class comes from the device framework.
package android.view;
public abstract class Window {
    public WindowManager.LayoutParams getAttributes(){throw new RuntimeException();}
    public void setAttributes(WindowManager.LayoutParams p){throw new RuntimeException();}
    public void setSoftInputMode(int mode) { throw new RuntimeException(); }
    public void addFlags(int flags) { throw new RuntimeException(); }
    public abstract View getDecorView();
}
