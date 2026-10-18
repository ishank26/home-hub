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
        settings.setUserAgentString(settings.getUserAgentString() + " HomeHubKiosk/0.5");
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
                            if ("browse".equals(action.getHost()) && query != null && query.startsWith("query=")
                                    && query.indexOf('&') == -1 && query.length() <= 6500) {
                                String input = URLDecoder.decode(query.substring(6), "UTF-8");
                                if (input.length() <= 2048) {
                                    handler.removeCallbacks(retry);retryPending=false;
                                    startActivityForResult(new Intent(MainActivity.this, BrowserActivity.class).putExtra("query", input), 42);
                                }
                            }
                        } catch (Exception ignored) { /* malformed action: no navigation */ }
                    }
                    return true;
                }
                if (trusted.length() > 0 && trusted.equals(BrowserPolicy.origin(target))) return false;
                if (fromHub && BrowserPolicy.isPublicHttps(target)) {
                    startActivityForResult(new Intent(MainActivity.this, BrowserActivity.class).putExtra("query", target),42);
                }
                return true;
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
        setContentView(web);
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

    @Override
    protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request,result,data);
        if (request != 42 || result != -1 || data == null) return;
        String source=data.getStringExtra("recipe");
        String hub=BrowserPolicy.origin(url);
        if (hub.length() > 0 && BrowserPolicy.isPublicHttps(source)) {
            // Keep the saved boot/pair URL untouched. The publisher never sees it.
            handler.removeCallbacks(retry);retryPending=false;
            web.loadUrl(hub + "/?recipe=" + BrowserPolicy.encode(source));
        }
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
        hideSystemBars();
    }

    @Override
    protected void onPause() {
        web.onPause();
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(retry);
        handler.removeCallbacks(exit);
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
