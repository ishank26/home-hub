// Compile-only stub: never packaged. The real class comes from the device framework.
package android.webkit;
public abstract class WebSettings {
    public abstract String getUserAgentString();
    public abstract void setUserAgentString(String value);
    public abstract void setAllowContentAccess(boolean allow);
    public abstract void setMixedContentMode(int mode);
    public abstract void setCacheMode(int mode);
    public abstract void setSaveFormData(boolean save);
    public abstract void setSupportMultipleWindows(boolean support);
    public abstract void setJavaScriptCanOpenWindowsAutomatically(boolean allow);
    public abstract void setJavaScriptEnabled(boolean flag);
    public abstract void setDomStorageEnabled(boolean flag);
    public abstract void setDatabaseEnabled(boolean flag);
    public abstract void setAllowFileAccess(boolean allow);
    public abstract void setMediaPlaybackRequiresUserGesture(boolean require);
    public abstract void setTextZoom(int textZoom);
}
