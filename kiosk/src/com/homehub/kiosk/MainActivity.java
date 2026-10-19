package com.homehub.kiosk;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.view.MotionEvent;
import android.view.View;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.net.URI;
import java.net.URLDecoder;

/**
 * Fullscreen dashboard kiosk. Loads the Home Hub page, keeps the screen on, hides system bars,
 * and retries every few seconds while the server is unreachable. A three-finger hold for two
 * seconds opens Android Settings, where Settings > Home switches back to the stock launcher
 * (the dashboard itself uses a two-finger hold for its admin panel).
 *
 * Server address: `am start -n com.homehub.kiosk/.MainActivity --es url <http(s) URL>` saves the
 * URL (for the LAN, the server's /pair?token=... link) and every later launch, including boot as
 * the Home app, reuses it. Without a saved URL it loads the USB address below.
 */
public class MainActivity extends Activity {
    private static final String DEFAULT_URL = "http://127.0.0.1:8099/";
    private static final long RETRY_MS = 5000;
    private static final long EXIT_HOLD_MS = 2000;

    // Platform constants (API 23), written out because this app compiles against minimal stubs.
    private static final int FLAG_KEEP_SCREEN_ON = 0x00000080;
    private static final int FLAG_FULLSCREEN = 0x00000400;
    private static final int IMMERSIVE_FLAGS =
            0x00000002   // SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | 0x00000004 // SYSTEM_UI_FLAG_FULLSCREEN
            | 0x00000100 // SYSTEM_UI_FLAG_LAYOUT_STABLE
            | 0x00000200 // SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | 0x00000400 // SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
            | 0x00001000; // SYSTEM_UI_FLAG_IMMERSIVE_STICKY
    private static final int FLAG_ACTIVITY_NEW_TASK = 0x10000000;
    private static final int ACTION_UP = 1;
    private static final int ACTION_CANCEL = 3;
    private static final int ACTION_POINTER_DOWN = 5;
    private static final int ACTION_POINTER_UP = 6;

    private final Handler handler = new Handler();
    private WebView web;
    private android.widget.FrameLayout root;
    private BrowserPanel browser;
    private int brightness;
    private String url = DEFAULT_URL;
    private boolean retryPending;

    private final Runnable retry = new Runnable() {
        @Override
        public void run() {
            retryPending = false;
            web.loadUrl(url);
        }
    };

    private final Runnable exit = new Runnable() {
        @Override
        public void run() {
            try {
                startActivity(new Intent("android.settings.SETTINGS").addFlags(FLAG_ACTIVITY_NEW_TASK));
            } catch (RuntimeException e) {
                finish();
            }
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(FLAG_KEEP_SCREEN_ON | FLAG_FULLSCREEN);

        String saved = getSharedPreferences("kiosk", 0).getString("url", null); // MODE_PRIVATE
        if (isWebUrl(saved)) {
            url = saved;
        }
        saveRequestedUrl(getIntent());

        WebView.setWebContentsDebuggingEnabled(true); // reachable only over ADB
        web = new WebView(this);
        web.setBackgroundColor(0xFF000000);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setTextZoom(100);
        settings.setUserAgentString(settings.getUserAgentString() + " HomeHubKiosk/0.6");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String target) {
                String trusted = BrowserPolicy.origin(url);
                boolean fromHub = trusted.length() > 0 && trusted.equals(BrowserPolicy.origin(view.getUrl()));
                if (target != null && target.startsWith("homehub:")) {
                    if (fromHub) {
                        try {
                            URI action = new URI(target);
                            String query = action.getRawQuery();
                            if ("browser-close".equals(action.getHost())) closeBrowser();
                            if ("brightness".equals(action.getHost()) && query != null && query.matches("value=[0-9]{2,3}")) {
                                brightness=PanelBounds.brightness(query.substring(6));
                                getSharedPreferences("kiosk",0).edit().putInt("brightness",brightness).apply();
                                applyBrightness();
                            }
                            if ("browse".equals(action.getHost()) && query != null && query.startsWith("query=")
                                    && query.indexOf('&') == -1 && query.length() <= 6500) {
                                String input = URLDecoder.decode(query.substring(6), "UTF-8");
                                if (input.length() <= 2048) {
                                    handler.removeCallbacks(retry);retryPending=false;
                                    openBrowser(input);
                                }
                            }
                        } catch (Exception ignored) { /* malformed action: no navigation */ }
                    }
                    return true;
                }
                if (trusted.length() > 0 && trusted.equals(BrowserPolicy.origin(target))) return false;
                if (fromHub && BrowserPolicy.isPublicHttps(target)) {
                    openBrowser(target);
                }
                return true;
            }

            @Override public void onPageFinished(WebView view,String target) {
                if (BrowserPolicy.origin(url).equals(BrowserPolicy.origin(target))) deviceState();
            }
            @Override
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                view.loadData("<body style=\"background:#000;color:#999;font:28px sans-serif;"
                        + "display:flex;align-items:center;justify-content:center;height:100vh;margin:0\">"
                        + "Waiting for Home Hub…</body>", "text/html", "utf-8");
                if (!retryPending) {
                    retryPending = true;
                    handler.postDelayed(retry, RETRY_MS);
                }
            }
        });
        root=new android.widget.FrameLayout(this) {
            @Override protected void onSizeChanged(int w,int h,int oldw,int oldh) {
                super.onSizeChanged(w,h,oldw,oldh); layoutBrowser();
            }
        };
        root.addView(web,new android.widget.FrameLayout.LayoutParams(-1,-1));
        setContentView(root);
        brightness=getSharedPreferences("kiosk",0).getInt("brightness",70);
        brightness=Math.max(10,Math.min(100,brightness));applyBrightness();
        web.loadUrl(url);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        // As the Home app the kiosk is usually already running; a new URL arrives here.
        super.onNewIntent(intent);
        if (saveRequestedUrl(intent)) {
            web.loadUrl(url);
        }
    }

    private void applyBrightness() {
        android.view.WindowManager.LayoutParams params=getWindow().getAttributes();
        params.screenBrightness=brightness/100f;getWindow().setAttributes(params);
    }
    private void deviceState() {
        web.evaluateJavascript("window.dispatchEvent(new CustomEvent('homehub:device',{detail:{brightness:"+brightness+",browserEmbedded:true}}))",null);
    }
    private void layoutBrowser() {
        if(browser==null)return;
        int[] b=PanelBounds.at(root.getWidth(),root.getHeight());
        android.widget.FrameLayout.LayoutParams params=new android.widget.FrameLayout.LayoutParams(b[2],b[3]);
        params.leftMargin=b[0];params.topMargin=b[1];browser.setLayoutParams(params);
    }
    private void openBrowser(String query) {
        closeBrowser();
        browser=new BrowserPanel(this,query,new BrowserPanel.Listener() {
            public void close(){closeBrowser();}
            public void recipe(String source){
                if(!BrowserPolicy.isPublicHttps(source))return;
                closeBrowser();web.loadUrl(BrowserPolicy.origin(url)+"/?recipe="+BrowserPolicy.encode(source));
            }
        });
        root.addView(browser,new android.widget.FrameLayout.LayoutParams(-1,-1));layoutBrowser();
        web.evaluateJavascript("window.dispatchEvent(new CustomEvent('homehub:browser',{detail:true}))",null);
    }
    private void closeBrowser() {
        if(browser!=null){root.removeView(browser);browser.dispose();browser=null;}
        if(web!=null)web.evaluateJavascript("window.dispatchEvent(new CustomEvent('homehub:browser',{detail:false}))",null);
    }

    private boolean saveRequestedUrl(Intent intent) {
        String requested = intent.getStringExtra("url");
        if (!isWebUrl(requested)) {
            return false;
        }
        getSharedPreferences("kiosk", 0).edit().putString("url", requested).apply();
        url = requested;
        return true;
    }

    @Override
    protected void onResume() {
        super.onResume();
        web.onResume();
        if(browser!=null)browser.resume();
        hideSystemBars();
    }

    @Override
    protected void onPause() {
        if(browser!=null)browser.pause();
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(retry);
        handler.removeCallbacks(exit);
        closeBrowser();
        web.destroy();
        super.onDestroy();
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemBars();
        }
    }

    @Override
    public boolean dispatchTouchEvent(MotionEvent event) {
        int action = event.getActionMasked();
        if (action == ACTION_POINTER_DOWN && event.getPointerCount() == 3) {
            handler.postDelayed(exit, EXIT_HOLD_MS);
        } else if (action == ACTION_POINTER_DOWN || action == ACTION_POINTER_UP
                || action == ACTION_UP || action == ACTION_CANCEL) {
            handler.removeCallbacks(exit);
        }
        return super.dispatchTouchEvent(event);
    }

    @Override
    public void onBackPressed() {
        if(browser!=null){browser.back();return;}
        if (web.canGoBack()) {
            web.goBack();
        }
    }

    private static boolean isWebUrl(String value) {
        return value != null && (value.startsWith("http://") || value.startsWith("https://"));
    }

    private void hideSystemBars() {
        getWindow().getDecorView().setSystemUiVisibility(IMMERSIVE_FLAGS);
    }
}
