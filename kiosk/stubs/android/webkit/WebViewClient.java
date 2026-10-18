// Compile-only stub: never packaged. The real class comes from the device framework.
package android.webkit;
public class WebViewClient {
    public WebResourceResponse shouldInterceptRequest(WebView view, String url) { throw new RuntimeException(); }
    public void onPageStarted(WebView view, String url, android.graphics.Bitmap icon) { throw new RuntimeException(); }
    public void onPageFinished(WebView view, String url) { throw new RuntimeException(); }
    public boolean shouldOverrideUrlLoading(WebView view, String url) { throw new RuntimeException(); }
    public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) { throw new RuntimeException(); }
}
